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
  RAPIDAPI_KEY           Your RapidAPI key from rapidapi.com dashboard
  RAPIDAPI_HOST          API host header (default: "yt-api.p.rapidapi.com")
  YTDLP_PROXY            Optional proxy URL for the yt-dlp fallback path
  YTDLP_COOKIES_FILE     Optional path to a Netscape cookies file
  YOUTUBE_COOKIES        Optional raw Netscape cookie text (HF Secrets friendly)

API used
--------
  YT-API by ytjar  →  https://rapidapi.com/ytjar/api/yt-api
  Endpoint:  GET https://yt-api.p.rapidapi.com/dl?id=<VIDEO_ID>

  Response shape (confirmed from live response):
    {
      "status": "OK",
      "id": "arj7oStGLkU",
      "formats": [                     ← muxed video+audio (easiest: itag 18 = 360p)
        { "itag": 18, "url": "https://redirector.googlevideo.com/...",
          "mimeType": "video/mp4; codecs=...", "quality": "medium",
          "audioQuality": "AUDIO_QUALITY_LOW", ... }
      ],
      "adaptiveFormats": [             ← separate video-only & audio-only streams
        { "itag": 140, "url": "...", "mimeType": "audio/mp4; codecs=...", ... },
        { "itag": 251, "url": "...", "mimeType": "audio/webm; codecs=...", ... },
        ...
      ]
    }
"""

from __future__ import annotations

import os
import re
import ssl
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse, parse_qs

import requests
import yt_dlp

from app.core.config import settings
from app.core.logging import logger
from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
_DOWNLOAD_TIMEOUT = 120   # seconds for the actual file download
_API_TIMEOUT      = 20    # seconds for the RapidAPI metadata call
_MAX_RETRIES      = 3
_BACKOFF_BASE     = 2     # wait = BACKOFF_BASE ** attempt  → 2s, 4s

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


def _extract_video_id(url: str) -> str:
    """Extract the 11-char YouTube video ID from any common URL format."""
    parsed = urlparse(url.strip())

    # youtu.be/<ID>
    if parsed.netloc in ('youtu.be', 'www.youtu.be'):
        vid = parsed.path.lstrip('/')
        if vid:
            return vid.split('?')[0]

    # youtube.com/watch?v=<ID>
    qs = parse_qs(parsed.query)
    if 'v' in qs:
        return qs['v'][0]

    # youtube.com/shorts/<ID>  or  /embed/<ID>  or  /v/<ID>
    match = re.search(r'/(?:shorts|embed|v)/([a-zA-Z0-9_-]{11})', parsed.path)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract video ID from URL: {url!r}")


def _fetch_file_from_url(direct_url: str, dest_path: Path) -> Path:
    """
    Stream-download *direct_url* to *dest_path*.
    These are short-lived signed googlevideo.com URLs — fetch immediately.
    """
    logger.info(f"[YT-DL] Downloading stream → {dest_path.name}")
    try:
        resp = requests.get(
            direct_url, stream=True, timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CaptionForge/1.0)"}
        )
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                fh.write(chunk)

        size_kb = dest_path.stat().st_size // 1024 if dest_path.exists() else 0
        if size_kb == 0:
            raise OSError(f"Downloaded file is empty: {dest_path}")

        logger.info(f"[YT-DL] Stream download complete: {dest_path.name} ({size_kb} KB)")
        return dest_path

    except requests.RequestException as exc:
        raise RuntimeError(f"Stream download failed: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Provider A — YT-API (ytjar) via RapidAPI
# ─────────────────────────────────────────────────────────────────────────────
#
# API:  https://rapidapi.com/ytjar/api/yt-api
# Host: yt-api.p.rapidapi.com
# Endpoint: GET /dl?id=<VIDEO_ID>
#
# To switch to a different RapidAPI service later:
#   1. Change RAPIDAPI_HOST env var to the new host
#   2. Update _rapidapi_get_stream_url() to match the new response JSON shape
#   Everything else (retry, file download, error handling) stays the same.
#
def _rapidapi_get_stream_url(video_url: str) -> tuple[str, str]:
    """
    Call YT-API, pick the best audio (or muxed) stream, return (url, ext).
    Raises RuntimeError with a clear message on any failure.
    """
    api_key  = os.environ.get("RAPIDAPI_KEY", "").strip()
    api_host = os.environ.get("RAPIDAPI_HOST", "yt-api.p.rapidapi.com").strip()

    if not api_key:
        raise RuntimeError(
            "RAPIDAPI_KEY is not set. Add it to your HF Space secrets."
        )

    # Extract video ID from the YouTube URL
    try:
        video_id = _extract_video_id(video_url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    endpoint = f"https://{api_host}/dl"
    headers  = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": api_host,
    }
    params = {"id": video_id}

    logger.info(f"[RapidAPI] GET {endpoint}?id={video_id}")

    try:
        resp = requests.get(endpoint, headers=headers, params=params,
                            timeout=_API_TIMEOUT)
    except requests.Timeout:
        raise RuntimeError(
            f"RapidAPI call timed out after {_API_TIMEOUT}s — service may be slow or down."
        )
    except requests.ConnectionError as exc:
        raise RuntimeError(f"Could not reach RapidAPI host '{api_host}': {exc}") from exc

    # ── HTTP-level errors ────────────────────────────────────────────────────
    if resp.status_code == 401:
        raise RuntimeError("RapidAPI key is invalid or expired (HTTP 401).")
    if resp.status_code == 403:
        raise RuntimeError("RapidAPI access forbidden — check your subscription plan (HTTP 403).")
    if resp.status_code == 429:
        raise RuntimeError(
            "RapidAPI rate limit hit (HTTP 429). "
            "Check your monthly quota at rapidapi.com/ytjar/api/yt-api."
        )
    if not resp.ok:
        raise RuntimeError(
            f"RapidAPI returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    # ── Parse JSON ───────────────────────────────────────────────────────────
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(
            f"RapidAPI returned non-JSON content-type={resp.headers.get('content-type')}."
        )

    if data.get("status") != "OK":
        raise RuntimeError(
            f"RapidAPI reported failure: status={data.get('status')!r}, "
            f"keys={list(data.keys())}"
        )

    logger.info(f"[RapidAPI] Got response for video id={data.get('id')!r} "
                f"title={data.get('title','?')!r}")

    # ── Stream selection strategy ─────────────────────────────────────────────
    # Priority:
    #   1. Audio-only streams from adaptiveFormats  (smallest, fastest download)
    #   2. Muxed (video+audio) from formats         (itag 18 = 360p, always has audio)
    #   3. Any adaptiveFormat with a URL            (last resort)
    # ─────────────────────────────────────────────────────────────────────────

    adaptive = data.get("adaptiveFormats", [])
    muxed    = data.get("formats", [])

    # 1 — Audio-only adaptive streams
    audio_streams = [
        f for f in adaptive
        if f.get("url") and f.get("mimeType", "").startswith("audio/")
    ]
    if audio_streams:
        # Prefer mp4 audio (widely compatible), then webm/opus
        mp4_audio = [f for f in audio_streams if "audio/mp4" in f.get("mimeType", "")]
        chosen    = mp4_audio[0] if mp4_audio else audio_streams[0]
        mime      = chosen.get("mimeType", "audio/mp4")
        ext       = "m4a" if "mp4" in mime else "webm"
        itag      = chosen.get("itag", "?")
        logger.info(f"[RapidAPI] Selected audio-only stream: "
                    f"itag={itag} mime={mime!r}")
        return chosen["url"], ext

    # 2 — Muxed formats (video+audio in one file, easiest to work with)
    muxed_valid = [f for f in muxed if f.get("url")]
    if muxed_valid:
        # itag 18 = 360p mp4 (always present, smallest muxed)
        itag18 = next((f for f in muxed_valid if f.get("itag") == 18), None)
        chosen = itag18 or muxed_valid[0]
        itag   = chosen.get("itag", "?")
        label  = chosen.get("qualityLabel", "?")
        logger.info(f"[RapidAPI] No audio-only stream; using muxed: "
                    f"itag={itag} quality={label!r}")
        return chosen["url"], "mp4"

    # 3 — Any adaptive format with a URL (video-only, but better than nothing)
    any_valid = [f for f in adaptive if f.get("url")]
    if any_valid:
        chosen = any_valid[0]
        mime   = chosen.get("mimeType", "video/mp4")
        ext    = "mp4" if "mp4" in mime else "webm"
        logger.warning(f"[RapidAPI] Falling back to first available adaptive format "
                       f"(may be video-only): itag={chosen.get('itag','?')}")
        return chosen["url"], ext

    raise RuntimeError(
        f"RapidAPI response contained no usable stream URLs for video id={video_id!r}. "
        f"Top-level keys: {list(data.keys())}"
    )


def _provider_rapidapi(url: str, task_id: str) -> Path:
    """Download via YT-API (ytjar) on RapidAPI."""
    logger.info(f"[RapidAPI] Provider starting for task {task_id}")

    try:
        stream_url, ext = _rapidapi_get_stream_url(url)
    except RuntimeError as exc:
        logger.error(f"[RapidAPI] API stage failed: {exc}")
        raise  # re-raise so auto-chain can try next provider

    dest = settings.upload_path / f"{task_id}.{ext}"
    try:
        return _fetch_file_from_url(stream_url, dest)
    except RuntimeError as exc:
        logger.error(f"[RapidAPI] File download stage failed: {exc}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Provider B — yt-dlp direct (legacy / fallback)
# ─────────────────────────────────────────────────────────────────────────────
def _build_ytdlp_opts(task_id: str, player_clients: list[str]) -> dict:
    outtmpl = str(settings.upload_path / f"{task_id}.%(ext)s")
    opts: dict = {
        "format":              "bestaudio/best",
        "outtmpl":             outtmpl,
        "noplaylist":          True,
        "quiet":               False,
        "no_warnings":         True,
        "extractor_args":      {"youtube": {"player_client": player_clients}},
        "legacyserverconnect": True,
        "nocheckcertificate":  True,
        "socket_timeout":      30,
        "retries":             1,
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
    """Download via yt-dlp directly (may fail on HF datacenter IPs)."""
    logger.info(f"[yt-dlp] Provider starting for task {task_id}")

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
# To add a new provider: implement _provider_<name>() and register it here.
# ─────────────────────────────────────────────────────────────────────────────
ProviderFn = Callable[[str, str], Path]

PROVIDERS: dict[str, ProviderFn] = {
    "rapidapi": _provider_rapidapi,
    "ytdlp":    _provider_ytdlp,
    # "cobalt":  _provider_cobalt,   ← future provider slot
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point — called by routes.py, nothing else changes
# ─────────────────────────────────────────────────────────────────────────────
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Download a YouTube video/audio to local storage and return the file path.

    Provider is controlled by YT_DOWNLOAD_PROVIDER env var:
      "auto"     — try rapidapi first, fall back to ytdlp  (default)
      "rapidapi" — RapidAPI only
      "ytdlp"    — yt-dlp direct only

    Raises HTTPException(400) with a clean user-facing message on all failures.
    """
    _ensure_upload_dir()

    provider_name = os.environ.get("YT_DOWNLOAD_PROVIDER", "auto").strip().lower()
    logger.info(f"[YT-DL] Starting download | provider={provider_name} "
                f"| task={task_id} | url={url}")

    # ── Single-provider mode ─────────────────────────────────────────────────
    if provider_name in PROVIDERS:
        try:
            return PROVIDERS[provider_name](url, task_id)
        except RuntimeError as exc:
            logger.error(f"[YT-DL] Provider '{provider_name}' failed: {exc}")
            raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)

    # ── Auto mode: try providers in order until one succeeds ─────────────────
    if provider_name == "auto":
        chain = ["rapidapi", "ytdlp"]

        # Skip rapidapi silently if the key isn't set yet
        if not os.environ.get("RAPIDAPI_KEY", "").strip():
            logger.info("[YT-DL] RAPIDAPI_KEY not set — skipping rapidapi, using ytdlp")
            chain = ["ytdlp"]

        for name in chain:
            logger.info(f"[YT-DL] Trying provider: {name}")
            try:
                result = PROVIDERS[name](url, task_id)
                logger.info(f"[YT-DL] Provider '{name}' succeeded ✓")
                return result
            except RuntimeError as exc:
                is_last = (name == chain[-1])
                logger.warning(
                    f"[YT-DL] Provider '{name}' failed "
                    f"({'no more providers' if is_last else 'trying next'}). "
                    f"Reason: {str(exc)[:200]}"
                )

        logger.error(f"[YT-DL] All providers exhausted for task {task_id}.")
        raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)

    # ── Unknown provider ─────────────────────────────────────────────────────
    known = ", ".join(PROVIDERS.keys()) + ", auto"
    logger.error(f"[YT-DL] Unknown YT_DOWNLOAD_PROVIDER='{provider_name}'. Valid: {known}")
    raise HTTPException(
        status_code=500,
        detail=(
            f"Server misconfiguration: unknown YT_DOWNLOAD_PROVIDER "
            f"'{provider_name}'. Valid values: {known}"
        )
    )
