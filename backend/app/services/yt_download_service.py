"""
yt_download_service.py
======================
Pluggable YouTube download service for CaptionForge.

Architecture
------------
  download_youtube_video(url, task_id)   ← single public entry point
        │
        ├─ [provider = "rapidapi"]  → _provider_rapidapi()
        ├─ [provider = "ytdlp"]     → _provider_ytdlp()        (yt-dlp direct, legacy)
        └─ [provider = "auto"]      → rapidapi first, yt-dlp on failure  ← default

Adding a second provider
------------------------
  1. Write  def _provider_<name>(url, task_id) -> Path
  2. Register it in PROVIDERS dict at the bottom of this file
  3. Set  YT_DOWNLOAD_PROVIDER=<name>  in HF Secrets (or "auto" to chain it)

Environment variables
---------------------
  YT_DOWNLOAD_PROVIDER   "auto" | "rapidapi" | "ytdlp"   (default: "auto")
  RAPIDAPI_KEY           Your RapidAPI key
  RAPIDAPI_HOST          RapidAPI host header for the chosen service
                           e.g. "youtube-media-downloader.p.rapidapi.com"
  YTDLP_PROXY            Optional proxy URL for the yt-dlp fallback path
  YTDLP_COOKIES_FILE     Optional path to a Netscape cookies file
  YOUTUBE_COOKIES        Optional raw Netscape cookie text (HF Secrets friendly)
"""

from __future__ import annotations

import os
import ssl
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable

import requests                     # already in requirements (via fastapi/httpx chain)
import yt_dlp

from app.core.config import settings
from app.core.logging import logger
from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
_DOWNLOAD_TIMEOUT   = 120           # seconds to wait for the actual file download
_API_TIMEOUT        = 20            # seconds to wait for the third-party API call
_MAX_RETRIES        = 3
_BACKOFF_BASE       = 2             # retry wait = BACKOFF_BASE ** attempt  (2s, 4s)

# yt-dlp player client fallback ladder (most reliable → least)
_PLAYER_CLIENTS = [
    ['android'],
    ['ios'],
    ['android', 'web'],
]

_NON_RETRYABLE = (
    'video unavailable', 'private video', 'age-restricted',
    'geo-restricted', 'not available', 'members only',
    'this video has been removed', 'sign in to confirm',
)

_FRIENDLY_ERROR = (
    "We couldn't download this YouTube video right now. "
    "This can happen due to YouTube rate-limiting or a temporary issue with "
    "our download service. Please try again in a moment, or upload the "
    "video file directly instead."
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_upload_dir() -> None:
    settings.upload_path.mkdir(parents=True, exist_ok=True)


def _fetch_file_from_url(direct_url: str, dest_path: Path) -> Path:
    """
    Download a raw file from *direct_url* to *dest_path*.
    These URLs are typically short-lived signed links, so we fetch immediately.
    """
    logger.info(f"[YT-DL] Fetching file from direct URL → {dest_path.name}")
    try:
        resp = requests.get(direct_url, stream=True, timeout=_DOWNLOAD_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):   # 1 MB chunks
                fh.write(chunk)
        if not dest_path.exists() or dest_path.stat().st_size == 0:
            raise OSError(f"File written but appears empty: {dest_path}")
        logger.info(f"[YT-DL] File download complete: {dest_path} "
                    f"({dest_path.stat().st_size // 1024} KB)")
        return dest_path
    except requests.RequestException as exc:
        raise RuntimeError(f"File download from direct URL failed: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Provider A — RapidAPI YouTube downloader
# ─────────────────────────────────────────────────────────────────────────────
#
# Default target API:  "YouTube Media Downloader"
#   RapidAPI page:     https://rapidapi.com/ytjar/api/youtube-media-downloader
#   Host header:       youtube-media-downloader.p.rapidapi.com
#   Endpoint:          GET /v2/video/details?videoLink=<url>
#   Response shape:
#     {
#       "status": true,
#       "videos": [
#         { "quality": "720p", "url": "<signed-download-url>", ... },
#         { "quality": "360p", "url": "...", ... }
#       ],
#       "audios": [
#         { "quality": "128kbps", "url": "...", ... }
#       ]
#     }
#
# If you subscribe to a different RapidAPI service, update:
#   _rapidapi_get_stream_url()  ← parse *their* JSON shape here
#   Set RAPIDAPI_HOST to their host header value.
#
def _rapidapi_get_stream_url(video_url: str) -> tuple[str, str]:
    """
    Call the RapidAPI YouTube downloader and return (direct_stream_url, ext).
    Raises RuntimeError with a descriptive message on any failure.
    """
    api_key  = os.environ.get("RAPIDAPI_KEY", "").strip()
    api_host = os.environ.get(
        "RAPIDAPI_HOST",
        "youtube-media-downloader.p.rapidapi.com"   # ← default host; override via env
    ).strip()

    if not api_key:
        raise RuntimeError(
            "RAPIDAPI_KEY environment variable is not set. "
            "Add it to your HF Space secrets."
        )

    endpoint = f"https://{api_host}/v2/video/details"
    headers  = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": api_host,
    }
    params   = {"videoLink": video_url}

    logger.info(f"[RapidAPI] Calling {endpoint} for URL: {video_url}")

    try:
        resp = requests.get(endpoint, headers=headers, params=params,
                            timeout=_API_TIMEOUT)
    except requests.Timeout:
        raise RuntimeError("RapidAPI call timed out — service may be slow or down.")
    except requests.ConnectionError as exc:
        raise RuntimeError(f"Could not reach RapidAPI: {exc}") from exc

    if resp.status_code == 401:
        raise RuntimeError("RapidAPI key is invalid or expired (HTTP 401).")
    if resp.status_code == 429:
        raise RuntimeError("RapidAPI rate limit hit (HTTP 429). "
                           "Check your plan quota on rapidapi.com.")
    if not resp.ok:
        raise RuntimeError(
            f"RapidAPI returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    # ── Parse response ────────────────────────────────────────────────────────
    # IMPORTANT: If you switch to a different RapidAPI service, update the
    # JSON parsing below to match that service's response structure.
    # ─────────────────────────────────────────────────────────────────────────
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("RapidAPI returned non-JSON response.")

    if not data.get("status"):
        raise RuntimeError(f"RapidAPI reported failure: {data}")

    # Prefer audio-only (smaller, faster, enough for transcription)
    # Fall back to lowest-quality video if no audio stream available.
    audios = data.get("audios", [])
    videos = data.get("videos", [])

    stream_url: str | None = None
    ext = "mp3"

    if audios:
        # Pick highest-bitrate audio stream
        best_audio = sorted(
            [a for a in audios if a.get("url")],
            key=lambda a: int(''.join(filter(str.isdigit, a.get("quality","0")))),
            reverse=True
        )
        if best_audio:
            stream_url = best_audio[0]["url"]
            ext = "mp3"
            logger.info(f"[RapidAPI] Selected audio stream: "
                        f"quality={best_audio[0].get('quality')}")

    if not stream_url and videos:
        # Pick lowest-quality video (saves bandwidth; we only need audio anyway)
        best_video = sorted(
            [v for v in videos if v.get("url")],
            key=lambda v: int(''.join(filter(str.isdigit, v.get("quality","9999")))),
        )
        if best_video:
            stream_url = best_video[0]["url"]
            ext = "mp4"
            logger.info(f"[RapidAPI] No audio stream; using video stream: "
                        f"quality={best_video[0].get('quality')}")

    if not stream_url:
        raise RuntimeError(
            "RapidAPI response contained no usable stream URLs. "
            f"Raw keys returned: {list(data.keys())}"
        )

    return stream_url, ext


def _provider_rapidapi(url: str, task_id: str) -> Path:
    """Download via RapidAPI YouTube downloader service."""
    logger.info(f"[RapidAPI] Provider selected for task {task_id}")

    try:
        stream_url, ext = _rapidapi_get_stream_url(url)
    except RuntimeError as exc:
        # API-level failure — log details, surface friendly message
        logger.error(f"[RapidAPI] API call failed: {exc}")
        raise  # re-raise as RuntimeError so the caller can chain/fallback

    dest = settings.upload_path / f"{task_id}.{ext}"
    try:
        return _fetch_file_from_url(stream_url, dest)
    except RuntimeError as exc:
        logger.error(f"[RapidAPI] File download failed: {exc}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Provider B — yt-dlp direct (legacy / fallback)
# ─────────────────────────────────────────────────────────────────────────────
def _build_ytdlp_opts(task_id: str, player_clients: list[str]) -> dict:
    outtmpl = str(settings.upload_path / f"{task_id}.%(ext)s")
    opts: dict = {
        "format":          "bestaudio/best",
        "outtmpl":         outtmpl,
        "noplaylist":      True,
        "quiet":           False,
        "no_warnings":     True,
        "extractor_args":  {"youtube": {"player_client": player_clients}},
        "legacyserverconnect": True,
        "nocheckcertificate":  True,
        "socket_timeout":  30,
        "retries":         1,
    }

    proxy = os.environ.get("YTDLP_PROXY", "").strip()
    if proxy:
        opts["proxy"] = proxy
        logger.info("[yt-dlp] Using proxy from YTDLP_PROXY")

    cookie_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file
        logger.info(f"[yt-dlp] Using cookies file: {cookie_file}")
    else:
        cookie_text = os.environ.get("YOUTUBE_COOKIES", "").strip()
        if cookie_text:
            tmp = "/tmp/youtube_cookies.txt"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(cookie_text)
                opts["cookiefile"] = tmp
                logger.info("[yt-dlp] Using cookies from YOUTUBE_COOKIES env var")
            except OSError as exc:
                logger.warning(f"[yt-dlp] Could not write cookie file: {exc}")

    return opts


def _provider_ytdlp(url: str, task_id: str) -> Path:
    """Download via yt-dlp directly (may fail on datacenter IPs)."""
    logger.info(f"[yt-dlp] Provider selected for task {task_id}")

    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        clients = _PLAYER_CLIENTS[attempt - 1]
        logger.info(f"[yt-dlp] Attempt {attempt}/{_MAX_RETRIES} "
                    f"player_clients={clients}")

        opts = _build_ytdlp_opts(task_id, clients)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                ext  = info.get("ext", "mp4")
                dest = settings.upload_path / f"{task_id}.{ext}"
                if not dest.exists():
                    raise FileNotFoundError(f"Expected file missing: {dest}")
                logger.info(f"[yt-dlp] Attempt {attempt} succeeded → {dest}")
                return dest

        except Exception as exc:
            last_exc = exc
            err = str(exc)
            logger.warning(f"[yt-dlp] Attempt {attempt} failed: {err[:200]}")

            if any(kw in err.lower() for kw in _NON_RETRYABLE):
                raise RuntimeError(
                    "This video is unavailable, private, age-restricted, "
                    "or geo-blocked."
                ) from exc

            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** attempt
                logger.info(f"[yt-dlp] Retrying in {wait}s...")
                time.sleep(wait)

    raise RuntimeError(
        f"yt-dlp failed after {_MAX_RETRIES} attempts. "
        f"Last error: {str(last_exc)[:200]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Provider registry
# Add new providers here — no other file needs to change.
# ─────────────────────────────────────────────────────────────────────────────
ProviderFn = Callable[[str, str], Path]

PROVIDERS: dict[str, ProviderFn] = {
    "rapidapi": _provider_rapidapi,
    "ytdlp":    _provider_ytdlp,
    # "cobalt":  _provider_cobalt,    ← future: cobalt.tools open-source API
    # "yt1s":    _provider_yt1s,      ← future: another RapidAPI service
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Download a YouTube video/audio to local storage and return the file path.

    Provider is controlled by the YT_DOWNLOAD_PROVIDER env var:
      "auto"     — try rapidapi first, fall back to ytdlp  (default)
      "rapidapi" — RapidAPI only
      "ytdlp"    — yt-dlp direct only

    Raises HTTPException(400) with a clean user-facing message on failure.
    """
    _ensure_upload_dir()

    provider_name = os.environ.get("YT_DOWNLOAD_PROVIDER", "auto").strip().lower()
    logger.info(f"[YT-DL] download_youtube_video called | "
                f"provider={provider_name} | task={task_id} | url={url}")

    # ── Single-provider mode ─────────────────────────────────────────────────
    if provider_name in PROVIDERS:
        try:
            return PROVIDERS[provider_name](url, task_id)
        except RuntimeError as exc:
            logger.error(f"[YT-DL] Provider '{provider_name}' failed: {exc}")
            raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)

    # ── Auto mode: chain providers in priority order ─────────────────────────
    if provider_name == "auto":
        # Priority order: rapidapi → ytdlp
        # To add a third provider, append it to this list.
        chain = ["rapidapi", "ytdlp"]

        # If RAPIDAPI_KEY is not set, skip the rapidapi provider silently
        if not os.environ.get("RAPIDAPI_KEY", "").strip():
            logger.info("[YT-DL] RAPIDAPI_KEY not set — skipping rapidapi provider")
            chain = ["ytdlp"]

        for name in chain:
            logger.info(f"[YT-DL] Trying provider: {name}")
            try:
                result = PROVIDERS[name](url, task_id)
                logger.info(f"[YT-DL] Provider '{name}' succeeded.")
                return result
            except RuntimeError as exc:
                logger.warning(
                    f"[YT-DL] Provider '{name}' failed, "
                    f"{'trying next provider' if name != chain[-1] else 'no more providers'}. "
                    f"Reason: {str(exc)[:200]}"
                )
                continue

        # All providers in the chain failed
        logger.error(f"[YT-DL] All providers exhausted for task {task_id}.")
        raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)

    # ── Unknown provider ─────────────────────────────────────────────────────
    known = ", ".join(PROVIDERS.keys()) + ", auto"
    logger.error(f"[YT-DL] Unknown provider '{provider_name}'. Known: {known}")
    raise HTTPException(
        status_code=500,
        detail=(
            f"Server misconfiguration: unknown YT_DOWNLOAD_PROVIDER "
            f"'{provider_name}'. Valid values: {known}"
        )
    )
