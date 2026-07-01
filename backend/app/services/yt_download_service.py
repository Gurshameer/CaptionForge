"""
yt_download_service.py
======================
YouTube audio download for CaptionForge.

Strategy (controlled by RELAY_URL env var):
  - RELAY_URL set   → POST to the Fly.io relay service, stream audio back.
                      The relay runs yt-dlp on its own clean IP, avoiding
                      YouTube's datacenter IP blocks on HF Spaces.
  - RELAY_URL unset → Run yt-dlp directly on this machine (local dev only).

Environment variables
---------------------
  RELAY_URL           Full base URL of the relay service, e.g.
                      https://captionforge-relay.fly.dev
                      Set this on HF Spaces Settings → Variables.
  RELAY_SECRET_KEY    Shared secret sent as X-Relay-Key header.
                      Must match the relay's RELAY_SECRET_KEY secret.
  YTDLP_COOKIES_FILE  Optional path to a Netscape cookies file for yt-dlp
                      (local fallback only).
  YOUTUBE_COOKIES     Optional raw Netscape cookie text for yt-dlp
                      (local fallback only).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import requests
from fastapi import HTTPException

from app.core.config import settings
from app.core.logging import logger

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
_RELAY_TIMEOUT = 180  # seconds — long videos need time
_LOCAL_TIMEOUT = 120  # seconds — socket timeout for yt-dlp subprocess

_USER_FRIENDLY_ERROR = (
    "YouTube download is temporarily unavailable. "
    "Please upload the video file directly instead."
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_upload_dir() -> None:
    settings.upload_path.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy A — Fly.io relay (production / HF Spaces)
# ─────────────────────────────────────────────────────────────────────────────
def _download_via_relay(url: str, task_id: str, relay_base_url: str) -> Path:
    """
    POST the YouTube URL to the Fly.io relay service.
    The relay runs yt-dlp on its own clean IP and streams the audio back.
    We save the streamed bytes to disk and return the path.
    """
    secret = os.environ.get("RELAY_SECRET_KEY", "").strip()
    endpoint = f"{relay_base_url.rstrip('/')}/extract"

    logger.info(f"[relay] POST {endpoint} | task={task_id}")

    try:
        response = requests.post(
            endpoint,
            json={"url": url},
            headers={"X-Relay-Key": secret},
            stream=True,
            timeout=_RELAY_TIMEOUT,
        )
    except requests.Timeout:
        logger.error(f"[relay] Request timed out after {_RELAY_TIMEOUT}s")
        raise RuntimeError("Relay timed out.")
    except requests.ConnectionError as exc:
        logger.error(f"[relay] Cannot reach relay at {relay_base_url}: {exc}")
        raise RuntimeError(f"Cannot reach relay: {exc}")

    if response.status_code == 401:
        logger.error("[relay] Auth failed — check RELAY_SECRET_KEY on both ends")
        raise RuntimeError("Relay authentication failed (401).")

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text[:200])
        except Exception:
            detail = response.text[:200]
        logger.error(f"[relay] Non-200 response: HTTP {response.status_code} — {detail}")
        raise RuntimeError(f"Relay returned HTTP {response.status_code}: {detail}")

    # Stream response body into the destination file
    dest = settings.upload_path / f"{task_id}.mp3"
    try:
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                fh.write(chunk)
    except OSError as exc:
        logger.error(f"[relay] Failed to write audio file: {exc}")
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to save audio from relay: {exc}")

    size_kb = dest.stat().st_size // 1024
    if size_kb == 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError("Relay returned an empty audio file.")

    logger.info(f"[relay] Download complete: {dest.name} ({size_kb} KB) ✓")
    return dest


# ─────────────────────────────────────────────────────────────────────────────
# Strategy B — yt-dlp direct (local development only)
# ─────────────────────────────────────────────────────────────────────────────
def _download_via_ytdlp(url: str, task_id: str) -> Path:
    """
    Run yt-dlp directly on this machine.
    Only intended for local development — will fail on HF Spaces (blocked IPs).
    """
    import yt_dlp  # imported lazily so the relay path has no yt-dlp dependency at call time

    outtmpl = str(settings.upload_path / f"{task_id}.%(ext)s")
    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": True,
        "socket_timeout": _LOCAL_TIMEOUT,
        "retries": 2,
    }

    # Optional cookies for authenticated / age-gated videos
    cookie_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file
    else:
        cookie_text = os.environ.get("YOUTUBE_COOKIES", "").strip()
        if cookie_text:
            tmp = os.path.join(tempfile.gettempdir(), "youtube_cookies.txt")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(cookie_text)
                opts["cookiefile"] = tmp
                logger.info("[yt-dlp] Using cookies from YOUTUBE_COOKIES env var")
            except OSError as exc:
                logger.warning(f"[yt-dlp] Could not write cookie file: {exc}")

    logger.info(f"[yt-dlp] Downloading directly | task={task_id} | url={url}")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get("ext", "mp4")
            dest = settings.upload_path / f"{task_id}.{ext}"
            if not dest.exists():
                raise FileNotFoundError(f"Expected output file missing: {dest}")
            logger.info(f"[yt-dlp] Download complete: {dest.name} ✓")
            return dest
    except Exception as exc:
        logger.error(f"[yt-dlp] Download failed: {exc}")
        raise RuntimeError(str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point (called by routes.py — signature must not change)
# ─────────────────────────────────────────────────────────────────────────────
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Download YouTube audio to local storage. Returns the file path.

    Uses the Fly.io relay when RELAY_URL is set (production/HF Spaces).
    Falls back to local yt-dlp when RELAY_URL is unset (local dev).

    Raises HTTPException(400) with a user-friendly message on any failure.
    """
    _ensure_upload_dir()

    relay_url = os.environ.get("RELAY_URL", "").strip()

    try:
        if relay_url:
            logger.info(f"[YT-DL] Mode=relay | relay={relay_url} | task={task_id}")
            return _download_via_relay(url, task_id, relay_url)
        else:
            logger.warning(
                "[YT-DL] RELAY_URL not set — falling back to local yt-dlp. "
                "This will fail on HF Spaces due to YouTube IP blocks."
            )
            return _download_via_ytdlp(url, task_id)

    except RuntimeError as exc:
        logger.error(f"[YT-DL] Download failed for task {task_id}: {exc}")
        raise HTTPException(status_code=400, detail=_USER_FRIENDLY_ERROR)
