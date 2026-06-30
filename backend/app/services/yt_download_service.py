"""
yt_download_service.py
======================
Pluggable YouTube download service for CaptionForge.

Provider chain (auto mode):
  1. cobalt   — cobalt.tools open API, no key needed, tunneled URLs ✅
  2. ytmp3    — youtube-mp36 RapidAPI, CDN URLs (needs RAPIDAPI_KEY)
  3. ytdlp    — yt-dlp direct (usually fails on HF datacenter IPs)

Environment variables
---------------------
  YT_DOWNLOAD_PROVIDER   "auto" | "cobalt" | "ytmp3" | "ytdlp"  (default: "auto")
  RAPIDAPI_KEY           Required for ytmp3 provider
  YTDLP_PROXY            Optional proxy for yt-dlp fallback
  YTDLP_COOKIES_FILE     Optional Netscape cookies file path
  YOUTUBE_COOKIES        Optional raw Netscape cookie text
"""

from __future__ import annotations

import os
import re
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
_DOWNLOAD_TIMEOUT  = 120
_API_TIMEOUT       = 25
_MAX_RETRIES       = 3
_BACKOFF_BASE      = 2

_PLAYER_CLIENTS = [['android'], ['ios'], ['android', 'web']]

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


def _fetch_file_from_url(direct_url: str, dest_path: Path,
                          retries: int = 3, retry_delay: float = 4.0) -> Path:
    """
    Stream-download *direct_url* to *dest_path* with retry on 404/503.
    Some CDNs need a few seconds to prepare the file — hence the retry.
    """
    logger.info(f"[YT-DL] Downloading stream → {dest_path.name}")
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                direct_url, stream=True, timeout=_DOWNLOAD_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CaptionForge/1.0)"}
            )

            if resp.status_code in (404, 503) and attempt < retries:
                logger.warning(
                    f"[YT-DL] Got HTTP {resp.status_code} on attempt {attempt}, "
                    f"waiting {retry_delay}s for CDN to prepare file..."
                )
                time.sleep(retry_delay)
                continue

            resp.raise_for_status()

            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)

            size_kb = dest_path.stat().st_size // 1024 if dest_path.exists() else 0
            if size_kb == 0:
                raise OSError(f"Downloaded file is empty: {dest_path}")

            logger.info(f"[YT-DL] Download complete: {dest_path.name} ({size_kb} KB)")
            return dest_path

        except requests.HTTPError as exc:
            last_exc = exc
            logger.warning(f"[YT-DL] Download attempt {attempt} HTTP error: {exc}")
            if attempt < retries:
                time.sleep(retry_delay)
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(f"[YT-DL] Download attempt {attempt} error: {exc}")
            if attempt < retries:
                time.sleep(2)

    raise RuntimeError(f"Stream download failed after {retries} attempts: {last_exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Provider A — Cobalt.tools (FREE, no API key, tunneled through their servers)
# ─────────────────────────────────────────────────────────────────────────────
# Cobalt is an open-source downloader with a public API.
# "tunnel" status means the file is served through cobalt's own proxy — ✅
# no IP lock, works from HF Spaces.
# Docs: https://github.com/imputnet/cobalt
#
def _provider_cobalt(url: str, task_id: str) -> Path:
    """Download via cobalt.tools public API — no API key required."""
    logger.info(f"[cobalt] Provider starting for task {task_id}")

    endpoint = "https://api.cobalt.tools/"
    headers  = {
        "Accept":       "application/json",
        "Content-Type": "application/json",
    }
    payload  = {
        "url":          url,
        "downloadMode": "audio",
        "audioFormat":  "mp3",
        "audioBitrate": "128",
    }

    logger.info(f"[cobalt] POST {endpoint} url={url}")

    try:
        resp = requests.post(endpoint, headers=headers, json=payload,
                             timeout=_API_TIMEOUT)
    except requests.Timeout:
        raise RuntimeError(f"[cobalt] API timed out after {_API_TIMEOUT}s.")
    except requests.ConnectionError as exc:
        raise RuntimeError(f"[cobalt] Cannot reach api.cobalt.tools: {exc}") from exc

    if not resp.ok:
        raise RuntimeError(
            f"[cobalt] HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("[cobalt] Non-JSON response from API.")

    status     = data.get("status", "")
    stream_url = data.get("url", "")

    logger.info(f"[cobalt] Response status={status!r}")

    if status == "tunnel" and stream_url:
        # Tunneled through cobalt's servers — safe from any IP ✅
        logger.info("[cobalt] Got tunnel URL (proxied through cobalt) ✅")
        dest = settings.upload_path / f"{task_id}.mp3"
        return _fetch_file_from_url(stream_url, dest, retries=2, retry_delay=3)

    if status == "redirect" and stream_url:
        # Direct CDN/YouTube URL — may or may not be IP-locked, try it anyway
        logger.warning("[cobalt] Got redirect URL (not proxied, may fail on HF)")
        dest = settings.upload_path / f"{task_id}.mp3"
        return _fetch_file_from_url(stream_url, dest, retries=2, retry_delay=3)

    if status == "picker":
        # Multiple streams — pick the first one
        picks = data.get("picker", [])
        if picks and picks[0].get("url"):
            stream_url = picks[0]["url"]
            logger.info(f"[cobalt] Picker mode — using first option: {stream_url[:60]}...")
            dest = settings.upload_path / f"{task_id}.mp3"
            return _fetch_file_from_url(stream_url, dest, retries=2, retry_delay=3)

    if status == "error":
        err_code = data.get("error", {}).get("code", "unknown")
        raise RuntimeError(f"[cobalt] API error code={err_code!r}. Data: {data}")

    raise RuntimeError(
        f"[cobalt] Unexpected response status={status!r}. "
        f"Keys: {list(data.keys())}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Provider B — youtube-mp36 RapidAPI (needs RAPIDAPI_KEY)
# ─────────────────────────────────────────────────────────────────────────────
# Subscribe: https://rapidapi.com/ytjar/api/youtube-mp36
# Returns CDN URLs — sometimes 404 on first try (CDN not ready), so we retry.
#
_YTMP3_HOST = "youtube-mp36.p.rapidapi.com"

def _get_ytmp3_link(video_id: str) -> str:
    """Call youtube-mp36 API and return the CDN download URL."""
    api_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY not set.")

    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": _YTMP3_HOST,
    }
    resp = requests.get(
        f"https://{_YTMP3_HOST}/dl",
        headers=headers,
        params={"id": video_id},
        timeout=_API_TIMEOUT
    )

    if resp.status_code == 401:
        raise RuntimeError("RAPIDAPI_KEY invalid (HTTP 401).")
    if resp.status_code == 403:
        raise RuntimeError(
            "Access forbidden (HTTP 403). Subscribe to youtube-mp36 at rapidapi.com."
        )
    if resp.status_code == 429:
        raise RuntimeError("RapidAPI rate limit hit (HTTP 429). Check your monthly quota.")
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("Non-JSON response from youtube-mp36 API.")

    status = data.get("status", "")
    link   = data.get("link", "").strip()

    if status == "processing" or not link:
        raise RuntimeError(f"ytmp3 status={status!r}, no link yet.")
    if status != "ok":
        raise RuntimeError(f"ytmp3 status={status!r}. data={data}")

    return link


def _provider_ytmp3(url: str, task_id: str) -> Path:
    """Download via youtube-mp36 RapidAPI with retry for CDN 404s."""
    logger.info(f"[ytmp3] Provider starting for task {task_id}")

    try:
        video_id = _extract_video_id(url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    # Retry getting a fresh CDN link if the download 404s
    # (CDN sometimes takes a few seconds to generate the file)
    for api_attempt in range(1, 4):
        logger.info(f"[ytmp3] API attempt {api_attempt}/3 for id={video_id}")
        try:
            cdn_url = _get_ytmp3_link(video_id)
        except RuntimeError as exc:
            if api_attempt < 3:
                logger.warning(f"[ytmp3] API call failed: {exc}. Retrying in 5s...")
                time.sleep(5)
                continue
            raise

        logger.info(f"[ytmp3] Got CDN URL: {cdn_url[:70]}...")
        dest = settings.upload_path / f"{task_id}.mp3"
        try:
            return _fetch_file_from_url(cdn_url, dest, retries=2, retry_delay=5)
        except RuntimeError as exc:
            if "404" in str(exc) and api_attempt < 3:
                logger.warning(
                    f"[ytmp3] CDN 404 — file not ready yet. "
                    f"Requesting fresh link in 6s... (attempt {api_attempt}/3)"
                )
                time.sleep(6)
                continue
            raise

    raise RuntimeError("[ytmp3] Exhausted all API + CDN retry attempts.")


# ─────────────────────────────────────────────────────────────────────────────
# Provider C — yt-dlp direct (legacy, usually fails on HF datacenter IPs)
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
                raise RuntimeError("Video unavailable, private, or geo-blocked.") from exc
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
    "cobalt": _provider_cobalt,   # ✅ Free, no key, tunneled — try first
    "ytmp3":  _provider_ytmp3,    # ✅ Needs RAPIDAPI_KEY, CDN URLs
    "ytdlp":  _provider_ytdlp,    # ⚠️  Usually fails on HF datacenter IPs
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Download YouTube audio to local storage. Returns the file path.

    YT_DOWNLOAD_PROVIDER values:
      "auto"   → cobalt → ytmp3 → ytdlp  (default)
      "cobalt" → cobalt.tools only (free, no key)
      "ytmp3"  → youtube-mp36 RapidAPI only (needs RAPIDAPI_KEY)
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
        chain: list[str] = ["cobalt"]
        if os.environ.get("RAPIDAPI_KEY", "").strip():
            chain.append("ytmp3")
        chain.append("ytdlp")

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
    raise HTTPException(
        status_code=500,
        detail=f"Unknown YT_DOWNLOAD_PROVIDER='{provider_name}'. Valid: {known}"
    )
