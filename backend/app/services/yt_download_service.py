"""
yt_download_service.py
======================
Pluggable YouTube download service for CaptionForge.

Architecture
------------
  download_youtube_video(url, task_id)   ← single public entry point
        │
        ├─ [provider = "ytmp3"]    → _provider_ytmp3()       ← DEFAULT (CDN URLs, no IP lock)
        ├─ [provider = "ytapi"]    → _provider_ytapi()       ← returns IP-locked googlevideo URLs
        ├─ [provider = "ytdlp"]    → _provider_ytdlp()       ← yt-dlp direct (fails on HF IPs)
        └─ [provider = "auto"]     → ytmp3 → ytdlp           ← default chain

WHY ytmp3 instead of ytapi
--------------------------
The yt-api (ytjar) /dl endpoint returns raw signed googlevideo.com URLs.
These URLs are IP-locked to the RapidAPI server IP that fetched them.
When HF Spaces (a different IP) tries to download, YouTube returns 403 Forbidden.

youtube-mp36 (also ytjar) returns URLs served from their own CDN:
  https://media.ytmp3.io/...
These are NOT IP-locked and can be downloaded from HF Spaces without 403.

API used (PRIMARY)
------------------
  youtube-mp36 by ytjar  →  https://rapidapi.com/ytjar/api/youtube-mp36
  Same RAPIDAPI_KEY — just subscribe to this API too (free tier available)
  Host:      youtube-mp36.p.rapidapi.com
  Endpoint:  GET /dl?id=<VIDEO_ID>
  Response:  { "status": "ok", "link": "<CDN_URL>", "title": "...", "duration": "..." }

Environment variables
---------------------
  YT_DOWNLOAD_PROVIDER   "auto" | "ytmp3" | "ytapi" | "ytdlp"  (default: "auto")
  RAPIDAPI_KEY           Your RapidAPI key (works for both ytmp3 and ytapi)
  YTDLP_PROXY            Optional proxy URL for the yt-dlp fallback path
  YTDLP_COOKIES_FILE     Optional path to a Netscape cookies file
  YOUTUBE_COOKIES        Optional raw Netscape cookie text (HF Secrets friendly)
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
_DOWNLOAD_TIMEOUT = 120
_API_TIMEOUT      = 20
_MAX_RETRIES      = 3
_BACKOFF_BASE     = 2

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
    """Extract the YouTube video ID from any common URL format."""
    parsed = urlparse(url.strip())
    if parsed.netloc in ('youtu.be', 'www.youtu.be'):
        return parsed.path.lstrip('/').split('?')[0]
    qs = parse_qs(parsed.query)
    if 'v' in qs:
        return qs['v'][0]
    match = re.search(r'/(?:shorts|embed|v)/([a-zA-Z0-9_-]{11})', parsed.path)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url!r}")


def _fetch_file_from_url(direct_url: str, dest_path: Path) -> Path:
    """Stream-download *direct_url* to *dest_path*."""
    logger.info(f"[YT-DL] Downloading stream → {dest_path.name}")
    try:
        resp = requests.get(
            direct_url, stream=True, timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CaptionForge/1.0)"}
        )
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
        size_kb = dest_path.stat().st_size // 1024 if dest_path.exists() else 0
        if size_kb == 0:
            raise OSError(f"Downloaded file is empty: {dest_path}")
        logger.info(f"[YT-DL] Download complete: {dest_path.name} ({size_kb} KB)")
        return dest_path
    except requests.RequestException as exc:
        raise RuntimeError(f"Stream download failed: {exc}") from exc


def _rapidapi_headers(host: str) -> dict:
    api_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY is not set. Add it to your HF Space secrets.")
    return {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": host}


def _check_rapidapi_response(resp: requests.Response, host: str) -> dict:
    """Raise RuntimeError with a clear message for common HTTP error codes."""
    if resp.status_code == 401:
        raise RuntimeError(f"RapidAPI key invalid or expired (HTTP 401) for host {host}.")
    if resp.status_code == 403:
        raise RuntimeError(
            f"RapidAPI access forbidden (HTTP 403) for {host}. "
            "Make sure you've subscribed to this API at rapidapi.com."
        )
    if resp.status_code == 429:
        raise RuntimeError(
            f"RapidAPI rate limit hit (HTTP 429) for {host}. Check your monthly quota."
        )
    if not resp.ok:
        raise RuntimeError(f"RapidAPI HTTP {resp.status_code} from {host}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"RapidAPI non-JSON response from {host}.")


# ─────────────────────────────────────────────────────────────────────────────
# Provider A — youtube-mp36 (ytjar) ← RECOMMENDED / DEFAULT
# ─────────────────────────────────────────────────────────────────────────────
# Subscribe: https://rapidapi.com/ytjar/api/youtube-mp36  (free tier, same key)
# Returns a CDN URL (NOT IP-locked googlevideo.com) → works from HF Spaces ✅
#
# Response shape:
#   { "status": "ok", "link": "https://media.ytmp3.io/...", "title": "...", "duration": "..." }
#
_YTMP3_HOST = "youtube-mp36.p.rapidapi.com"

def _provider_ytmp3(url: str, task_id: str) -> Path:
    """
    Download audio via youtube-mp36 API.
    Returns CDN-hosted MP3 URL — not IP-locked, works from any server.
    """
    logger.info(f"[ytmp3] Provider starting for task {task_id}")

    try:
        video_id = _extract_video_id(url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    endpoint = f"https://{_YTMP3_HOST}/dl"
    logger.info(f"[ytmp3] GET {endpoint}?id={video_id}")

    try:
        resp = requests.get(
            endpoint,
            headers=_rapidapi_headers(_YTMP3_HOST),
            params={"id": video_id},
            timeout=_API_TIMEOUT
        )
    except requests.Timeout:
        raise RuntimeError(f"[ytmp3] API call timed out after {_API_TIMEOUT}s.")
    except requests.ConnectionError as exc:
        raise RuntimeError(f"[ytmp3] Could not reach {_YTMP3_HOST}: {exc}") from exc

    data = _check_rapidapi_response(resp, _YTMP3_HOST)

    status = data.get("status", "")
    if status not in ("ok", "processing"):
        raise RuntimeError(
            f"[ytmp3] API returned status={status!r}. "
            f"Keys: {list(data.keys())}"
        )

    # The API sometimes needs a short wait when status="processing"
    if status == "processing":
        logger.info("[ytmp3] Status=processing, waiting 3s then retrying once...")
        time.sleep(3)
        resp2 = requests.get(
            endpoint,
            headers=_rapidapi_headers(_YTMP3_HOST),
            params={"id": video_id},
            timeout=_API_TIMEOUT
        )
        data = _check_rapidapi_response(resp2, _YTMP3_HOST)
        if data.get("status") != "ok" or not data.get("link"):
            raise RuntimeError(f"[ytmp3] Still processing after retry. data={data}")

    cdn_url = data.get("link", "").strip()
    if not cdn_url:
        raise RuntimeError(
            f"[ytmp3] No 'link' in response. Keys: {list(data.keys())}"
        )

    title = data.get("title", "unknown")
    logger.info(f"[ytmp3] Got CDN link for: {title!r}")

    dest = settings.upload_path / f"{task_id}.mp3"
    return _fetch_file_from_url(cdn_url, dest)


# ─────────────────────────────────────────────────────────────────────────────
# Provider B — yt-api (ytjar) — kept for reference, AVOID on HF Spaces
# ─────────────────────────────────────────────────────────────────────────────
# Returns raw googlevideo.com signed URLs that are IP-locked to RapidAPI's
# servers → 403 Forbidden when downloaded from HF Spaces (different IP).
# Only use this if you're running on the SAME machine as the API call.
#
_YTAPI_HOST = "yt-api.p.rapidapi.com"

def _provider_ytapi(url: str, task_id: str) -> Path:
    """
    Download via yt-api (raw googlevideo.com URLs).
    WARNING: Will get 403 on HF Spaces because URLs are IP-locked.
    """
    logger.warning(
        "[ytapi] WARNING: yt-api returns IP-locked googlevideo.com URLs. "
        "This will likely 403 on HF Spaces. Use 'ytmp3' provider instead."
    )

    try:
        video_id = _extract_video_id(url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    endpoint = f"https://{_YTAPI_HOST}/dl"
    logger.info(f"[ytapi] GET {endpoint}?id={video_id}")

    try:
        resp = requests.get(
            endpoint,
            headers=_rapidapi_headers(_YTAPI_HOST),
            params={"id": video_id},
            timeout=_API_TIMEOUT
        )
    except requests.Timeout:
        raise RuntimeError(f"[ytapi] API call timed out.")
    except requests.ConnectionError as exc:
        raise RuntimeError(f"[ytapi] Connection error: {exc}") from exc

    data = _check_rapidapi_response(resp, _YTAPI_HOST)

    if data.get("status") != "OK":
        raise RuntimeError(f"[ytapi] status={data.get('status')!r}")

    # Try audio-only first, then muxed
    adaptive = data.get("adaptiveFormats", [])
    muxed    = data.get("formats", [])

    audio = [f for f in adaptive if f.get("url") and "audio/" in f.get("mimeType","")]
    if audio:
        mp4_audio = [f for f in audio if "audio/mp4" in f.get("mimeType","")]
        chosen = mp4_audio[0] if mp4_audio else audio[0]
        ext = "m4a" if "mp4" in chosen.get("mimeType","") else "webm"
        logger.info(f"[ytapi] Audio stream itag={chosen.get('itag')}")
        dest = settings.upload_path / f"{task_id}.{ext}"
        return _fetch_file_from_url(chosen["url"], dest)

    muxed_valid = [f for f in muxed if f.get("url")]
    if muxed_valid:
        chosen = next((f for f in muxed_valid if f.get("itag") == 18), muxed_valid[0])
        logger.info(f"[ytapi] Muxed stream itag={chosen.get('itag')}")
        dest = settings.upload_path / f"{task_id}.mp4"
        return _fetch_file_from_url(chosen["url"], dest)

    raise RuntimeError("[ytapi] No usable stream URLs in response.")


# ─────────────────────────────────────────────────────────────────────────────
# Provider C — yt-dlp direct (legacy)
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
    """Download via yt-dlp directly (usually fails on HF datacenter IPs)."""
    logger.info(f"[yt-dlp] Provider starting for task {task_id}")
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        clients = _PLAYER_CLIENTS[attempt - 1]
        logger.info(f"[yt-dlp] Attempt {attempt}/{_MAX_RETRIES} player_clients={clients}")
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
                raise RuntimeError("Video is unavailable, private, age-restricted, or geo-blocked.") from exc
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** attempt
                logger.info(f"[yt-dlp] Retrying in {wait}s...")
                time.sleep(wait)

    raise RuntimeError(f"yt-dlp failed after {_MAX_RETRIES} attempts. Last: {str(last_exc)[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# Provider registry
# ─────────────────────────────────────────────────────────────────────────────
ProviderFn = Callable[[str, str], Path]

PROVIDERS: dict[str, ProviderFn] = {
    "ytmp3":   _provider_ytmp3,   # ← RECOMMENDED: CDN URLs, no IP lock
    "ytapi":   _provider_ytapi,   # ← NOT recommended on HF: IP-locked URLs
    "ytdlp":   _provider_ytdlp,   # ← legacy: usually fails on HF datacenter IPs
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Download a YouTube audio file to local storage and return the file path.

    YT_DOWNLOAD_PROVIDER values:
      "auto"   → try ytmp3 first, fall back to ytdlp  (default)
      "ytmp3"  → youtube-mp36 API only (CDN URLs, recommended)
      "ytapi"  → yt-api only (IP-locked, NOT recommended on HF)
      "ytdlp"  → yt-dlp direct only (usually fails on HF)
    """
    _ensure_upload_dir()

    provider_name = os.environ.get("YT_DOWNLOAD_PROVIDER", "auto").strip().lower()
    logger.info(f"[YT-DL] Starting | provider={provider_name} | task={task_id} | url={url}")

    # Single provider
    if provider_name in PROVIDERS:
        try:
            return PROVIDERS[provider_name](url, task_id)
        except RuntimeError as exc:
            logger.error(f"[YT-DL] Provider '{provider_name}' failed: {exc}")
            raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)

    # Auto chain
    if provider_name == "auto":
        chain = ["ytmp3", "ytdlp"]
        if not os.environ.get("RAPIDAPI_KEY", "").strip():
            logger.info("[YT-DL] RAPIDAPI_KEY not set — skipping ytmp3, using ytdlp only")
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

    # Unknown
    known = ", ".join(PROVIDERS.keys()) + ", auto"
    raise HTTPException(status_code=500, detail=f"Unknown YT_DOWNLOAD_PROVIDER='{provider_name}'. Valid: {known}")
