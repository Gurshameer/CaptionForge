"""
yt_download_service.py
======================
Downloads YouTube videos using yt-dlp with:
  - Retry logic with exponential backoff (3 attempts)
  - Fallback player clients: android → ios → web
  - Optional YTDLP_PROXY env var support
  - Optional YTDLP_COOKIES_FILE env var support
  - YOUTUBE_COOKIES env var (raw Netscape cookie text, written to a temp file)
  - Clean, user-facing error messages on final failure

IMPORTANT NOTE
--------------
Even with all of these mitigations, there is NO 100% guaranteed fix when
running on Hugging Face Spaces (or any shared datacenter IP). YouTube
aggressively rate-limits and blocks datacenter IPs at the TLS layer.
The only reliable long-term solution is a working residential/rotating proxy
passed via the YTDLP_PROXY environment variable.
"""

import os
import time
import ssl
import yt_dlp
from pathlib import Path
from app.core.config import settings
from app.core.logging import logger
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_BACKOFF_BASE = 2          # seconds; attempt n waits backoff_base ** n seconds
_PLAYER_CLIENT_LADDER = [
    ['android'],            # attempt 1 — avoids the broken web-client API path
    ['ios'],                # attempt 2 — different API surface
    ['android', 'web'],     # attempt 3 — combined fallback
]

_FRIENDLY_ERROR = (
    "We couldn't fetch this YouTube video right now — this can happen due to "
    "YouTube rate-limiting or blocking our server's IP address. "
    "Please try again in a minute, or upload the video file directly instead."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_ssl_or_network_error(exc: Exception) -> bool:
    """Return True for SSL/network errors that are worth retrying."""
    msg = str(exc).lower()
    ssl_keywords = (
        'ssl', 'eof occurred', 'unexpected_eof', 'tlsv1', 'certificate',
        'connection reset', 'remote end closed', 'broken pipe',
        'network', 'timeout', 'httperror', 'unable to download'
    )
    return any(kw in msg for kw in ssl_keywords)


def _build_ydl_opts(task_id: str, player_clients: list[str]) -> dict:
    """Build a yt-dlp options dict for a given player-client ladder rung."""
    outtmpl = str(settings.upload_path / f"{task_id}.%(ext)s")

    opts: dict = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': player_clients}},
        'legacyserverconnect': True,
        'nocheckcertificate': True,
        # Slightly more lenient socket / read timeouts
        'socket_timeout': 30,
        'retries': 1,              # yt-dlp internal retries (separate from ours)
    }

    # --- Optional proxy (residential/rotating) ---------------------------------
    proxy = os.environ.get('YTDLP_PROXY', '').strip()
    if proxy:
        opts['proxy'] = proxy
        logger.info("yt-dlp: using proxy from YTDLP_PROXY env var")

    # --- Cookie file (Netscape format file path) --------------------------------
    cookie_file = os.environ.get('YTDLP_COOKIES_FILE', '').strip()
    if cookie_file and os.path.isfile(cookie_file):
        opts['cookiefile'] = cookie_file
        logger.info(f"yt-dlp: using cookies file from YTDLP_COOKIES_FILE: {cookie_file}")

    # --- Cookie text (raw Netscape text in env var, e.g. HF Secrets) ----------
    if 'cookiefile' not in opts:
        cookie_text = os.environ.get('YOUTUBE_COOKIES', '').strip()
        if cookie_text:
            tmp_cookie_path = '/tmp/youtube_cookies.txt'
            try:
                with open(tmp_cookie_path, 'w', encoding='utf-8') as f:
                    f.write(cookie_text)
                opts['cookiefile'] = tmp_cookie_path
                logger.info("yt-dlp: using cookies from YOUTUBE_COOKIES env var")
            except OSError as e:
                logger.warning(f"yt-dlp: could not write cookie file: {e}")

    return opts


# ---------------------------------------------------------------------------
# Main download function
# ---------------------------------------------------------------------------
def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Downloads a YouTube video to the uploads directory using yt-dlp.
    Returns the path to the downloaded file.

    Raises HTTPException(400) with a user-friendly message on final failure.
    """
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        player_clients = _PLAYER_CLIENT_LADDER[attempt - 1]
        logger.info(
            f"[YT-DLP] Attempt {attempt}/{_MAX_RETRIES} for task {task_id} "
            f"| player_clients={player_clients} | url={url}"
        )

        ydl_opts = _build_ydl_opts(task_id, player_clients)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                ext = info_dict.get('ext', 'mp4')
                downloaded_file = settings.upload_path / f"{task_id}.{ext}"

                if not downloaded_file.exists():
                    raise FileNotFoundError(
                        f"Downloaded file not found at expected path: {downloaded_file}"
                    )

                logger.info(
                    f"[YT-DLP] Attempt {attempt} succeeded → {downloaded_file}"
                )
                return downloaded_file

        except (yt_dlp.utils.DownloadError, ssl.SSLError, OSError, Exception) as exc:
            last_exc = exc
            err_str = str(exc)
            logger.warning(
                f"[YT-DLP] Attempt {attempt}/{_MAX_RETRIES} failed: {err_str}"
            )

            # Only retry on SSL/network errors; give up immediately on clear
            # "video not available" / private / geo-blocked errors.
            non_retryable_keywords = (
                'video unavailable', 'private video', 'age-restricted',
                'geo-restricted', 'not available', 'members only',
                'this video has been removed', 'sign in to confirm',
            )
            if any(kw in err_str.lower() for kw in non_retryable_keywords):
                logger.error(
                    f"[YT-DLP] Non-retryable error detected; aborting retries."
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "This video is unavailable, private, age-restricted, or "
                        "geo-blocked, and cannot be downloaded."
                    )
                )

            if attempt < _MAX_RETRIES:
                sleep_sec = _BACKOFF_BASE ** attempt   # 2s, 4s
                logger.info(f"[YT-DLP] Retrying in {sleep_sec}s...")
                time.sleep(sleep_sec)

    # All attempts exhausted
    logger.error(
        f"[YT-DLP] All {_MAX_RETRIES} attempts failed for task {task_id}. "
        f"Last error: {last_exc}",
        exc_info=True
    )
    raise HTTPException(status_code=400, detail=_FRIENDLY_ERROR)
