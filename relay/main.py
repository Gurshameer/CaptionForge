"""
relay/main.py
=============
CaptionForge Relay — YouTube audio download service.

Endpoints:
  GET  /health   → liveness check
  POST /extract  → download YouTube audio, stream it back

Auth: X-Relay-Key header must match RELAY_SECRET_KEY env var.

Download strategies (tried in order):
─────────────────────────────────────
  1. RapidAPI — youtube-mp36.p.rapidapi.com   [PRIMARY — recommended]
     Set RAPIDAPI_KEY in Render → Environment.
     Free tier: ~500 requests/day. No bot issues.

  2. yt-dlp fallback                          [FALLBACK — often blocked on Render]
     Used automatically if RAPIDAPI_KEY is not set.
     Supports YOUTUBE_COOKIES / YTDLP_COOKIES_FILE env vars.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests as http_requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [relay] %(levelname)s - %(message)s",
)
logger = logging.getLogger("relay")

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CaptionForge Relay",
    description="YouTube audio download relay for CaptionForge.",
    version="2.0.0",
)

# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    url: str


# ─────────────────────────────────────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────────────────────────────────────
def _verify_key(provided: str | None) -> None:
    """Raise 401 if the X-Relay-Key header is missing or doesn't match RELAY_SECRET_KEY."""
    expected = os.environ.get("RELAY_SECRET_KEY", "").strip()
    if not expected:
        logger.warning("[auth] RELAY_SECRET_KEY not set — rejecting all requests")
        raise HTTPException(status_code=401, detail="Relay is not configured (no secret set).")
    if not provided or provided.strip() != expected:
        logger.warning(f"[auth] Invalid X-Relay-Key: {provided!r}")
        raise HTTPException(status_code=401, detail="Invalid or missing X-Relay-Key header.")


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────
_YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")


def _validate_youtube_url(url: str) -> None:
    """Reject non-YouTube URLs early."""
    try:
        parsed = urlparse(url.strip())
        if parsed.netloc not in _YOUTUBE_DOMAINS:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid or non-YouTube URL: {url!r}")


def _extract_video_id(url: str) -> str:
    """
    Extract the YouTube video ID from a URL.
    Handles:
      https://www.youtube.com/watch?v=VIDEO_ID
      https://youtu.be/VIDEO_ID
      https://www.youtube.com/watch?v=VIDEO_ID&t=2s
    """
    parsed = urlparse(url.strip())

    # youtu.be/VIDEO_ID
    if parsed.netloc in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        if vid:
            return vid

    # youtube.com/watch?v=VIDEO_ID
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]

    # Fallback: look for 11-char alphanumeric ID anywhere in the URL
    match = re.search(r"[?&/]([a-zA-Z0-9_-]{11})(?:[?&]|$)", url)
    if match:
        return match.group(1)

    raise HTTPException(status_code=400, detail=f"Could not extract video ID from URL: {url!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Strategy A — RapidAPI youtube-mp36  (PRIMARY)
# ─────────────────────────────────────────────────────────────────────────────
_RAPIDAPI_HOST        = "youtube-mp36.p.rapidapi.com"
_RAPIDAPI_TIMEOUT     = 60   # seconds to wait for API to respond
_RAPIDAPI_MAX_RETRIES = 10   # max polling + CDN retry attempts
_RAPIDAPI_RETRY_DELAY = 3    # seconds between retries
_DOWNLOAD_TIMEOUT     = 120  # seconds to download the returned MP3 link



def _download_via_rapidapi(video_id: str, dest: Path, api_key: str) -> None:
    """
    Call youtube-mp36.p.rapidapi.com to get a direct MP3 link,
    then stream-download that link to `dest`.

    The API converts asynchronously — the CDN link can return 404 for several
    seconds while conversion is still running.  We poll the API and retry the
    download up to _RAPIDAPI_MAX_RETRIES times with _RAPIDAPI_RETRY_DELAY
    seconds between attempts.

    API: GET https://youtube-mp36.p.rapidapi.com/dl?id=VIDEO_ID
    Response: { "status": "ok", "link": "https://...", "title": "...", ... }
              { "status": "processing", "progress": 50, ... }  ← retry needed
    """
    import time

    _headers = {
        "x-rapidapi-host": _RAPIDAPI_HOST,
        "x-rapidapi-key": api_key,
    }

    # ── Step 1: Poll the API until status == "ok" ────────────────────────────
    mp3_url: str = ""
    title: str = "unknown"

    for attempt in range(1, _RAPIDAPI_MAX_RETRIES + 1):
        logger.info(f"[rapidapi] Polling API for video_id={video_id} (attempt {attempt}/{_RAPIDAPI_MAX_RETRIES})")
        try:
            resp = http_requests.get(
                f"https://{_RAPIDAPI_HOST}/dl",
                params={"id": video_id},
                headers=_headers,
                timeout=_RAPIDAPI_TIMEOUT,
            )
        except http_requests.Timeout:
            raise RuntimeError(f"RapidAPI timed out after {_RAPIDAPI_TIMEOUT}s")
        except http_requests.ConnectionError as exc:
            raise RuntimeError(f"Cannot reach RapidAPI: {exc}")

        if resp.status_code == 429:
            raise RuntimeError("RapidAPI rate limit hit. Free tier quota exhausted for today.")
        if resp.status_code == 403:
            raise RuntimeError("RapidAPI key invalid or subscription expired.")
        if not resp.ok:
            raise RuntimeError(f"RapidAPI returned HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"RapidAPI returned non-JSON: {resp.text[:200]}")

        status = data.get("status", "")
        if status == "ok":
            mp3_url = data.get("link", "")
            title = data.get("title", "unknown")
            if mp3_url:
                logger.info(f"[rapidapi] Link ready for '{title}' on attempt {attempt}")
                break
            raise RuntimeError("RapidAPI returned status=ok but no 'link' field.")

        if status in ("processing", "running", "pending", "waiting"):
            progress = data.get("progress", "?")
            logger.info(f"[rapidapi] Conversion in progress ({progress}%) — waiting {_RAPIDAPI_RETRY_DELAY}s...")
            time.sleep(_RAPIDAPI_RETRY_DELAY)
            continue

        # Unknown / error status
        msg = data.get("msg", data.get("error", str(data)))
        raise RuntimeError(f"RapidAPI error: {msg}")
    else:
        raise RuntimeError(
            f"RapidAPI conversion did not complete after {_RAPIDAPI_MAX_RETRIES} attempts. "
            "The video may be too long or the service is busy."
        )

    # ── Step 2: Download the MP3 — retry on 404 (CDN may lag behind) ────────
    _cdn_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://{_RAPIDAPI_HOST}/",
        "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
    }

    for dl_attempt in range(1, _RAPIDAPI_MAX_RETRIES + 1):
        logger.info(f"[rapidapi] Downloading MP3 (attempt {dl_attempt}/{_RAPIDAPI_MAX_RETRIES}): {mp3_url[:80]}...")
        try:
            with http_requests.get(
                mp3_url,
                headers=_cdn_headers,
                stream=True,
                timeout=_DOWNLOAD_TIMEOUT,
            ) as dl:
                if dl.status_code == 404:
                    logger.warning(f"[rapidapi] CDN returned 404 — conversion not ready yet, waiting {_RAPIDAPI_RETRY_DELAY}s...")
                    import time as _time
                    _time.sleep(_RAPIDAPI_RETRY_DELAY)
                    continue
                dl.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in dl.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                        fh.write(chunk)
                break  # success
        except http_requests.Timeout:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Timed out downloading MP3 from RapidAPI CDN link.")
        except http_requests.HTTPError as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download MP3 from CDN: {exc}")
    else:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"CDN link returned 404 after {_RAPIDAPI_MAX_RETRIES} retries. "
            "The RapidAPI conversion may have failed silently."
        )

    size_kb = dest.stat().st_size // 1024
    if size_kb == 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError("Downloaded MP3 file is empty.")

    logger.info(f"[rapidapi] Download complete: {dest.name} ({size_kb} KB) ✓")


# ─────────────────────────────────────────────────────────────────────────────
# Strategy B — yt-dlp  (FALLBACK)
# ─────────────────────────────────────────────────────────────────────────────
_YTDLP_TIMEOUT = 150  # seconds


def _download_via_ytdlp(url: str, dest: Path) -> None:
    """
    Run yt-dlp as a subprocess to download + convert audio to MP3.
    Fallback when RAPIDAPI_KEY is not set.
    Supports YOUTUBE_COOKIES / YTDLP_COOKIES_FILE env vars.
    """
    output_template = str(dest.parent / "audio.%(ext)s")

    # ── Cookie support ────────────────────────────────────────────────────────
    cookie_args: list[str] = []
    _tmp_cookie_path: Path | None = None

    cookie_file_path = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookie_file_path and Path(cookie_file_path).is_file():
        cookie_args = ["--cookies", cookie_file_path]
        logger.info(f"[ytdlp] Using cookie file: {cookie_file_path}")
    else:
        cookie_text = os.environ.get("YOUTUBE_COOKIES", "").strip()
        if cookie_text:
            _tmp_cookie_path = Path(tempfile.mktemp(suffix="_yt_cookies.txt"))
            try:
                _tmp_cookie_path.write_text(cookie_text, encoding="utf-8")
                cookie_args = ["--cookies", str(_tmp_cookie_path)]
                logger.info("[ytdlp] Using cookies from YOUTUBE_COOKIES env var")
            except OSError as exc:
                logger.warning(f"[ytdlp] Could not write temp cookie file: {exc} — proceeding without cookies")
    # ─────────────────────────────────────────────────────────────────────────

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "128K",
        "--output", output_template,
        "--no-warnings",
        "--force-ipv4",
        "--extractor-args", "youtube:player_client=android,web",
        *cookie_args,
        url,
    ]

    logger.info(f"[ytdlp] Running yt-dlp for: {url}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_YTDLP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timed out.")
    finally:
        # Always clean up temp cookie file
        if _tmp_cookie_path and _tmp_cookie_path.exists():
            try:
                _tmp_cookie_path.unlink()
            except OSError:
                pass

    if result.returncode != 0:
        stderr = result.stderr[-500:] if result.stderr else "(no stderr)"
        logger.error(f"[ytdlp] Failed (rc={result.returncode}): {stderr}")
        lower = stderr.lower()
        if "sign in" in lower or "bot" in lower:
            raise RuntimeError("YouTube bot detection triggered. Set RAPIDAPI_KEY to bypass.")
        if any(k in lower for k in ("private video", "video unavailable", "age-restricted",
                                     "geo-restricted", "members only")):
            raise RuntimeError("Video is unavailable, private, age-restricted, or geo-blocked.")
        raise RuntimeError(f"yt-dlp failed: {stderr[-200:]}")

    # yt-dlp writes to audio.<ext> — rename to dest
    tmpdir = dest.parent
    mp3_files = list(tmpdir.glob("*.mp3"))
    if mp3_files:
        mp3_files[0].rename(dest)
    else:
        all_files = [f for f in tmpdir.iterdir() if f.is_file()]
        if not all_files:
            raise RuntimeError("yt-dlp produced no output file.")
        all_files[0].rename(dest)

    size_kb = dest.stat().st_size // 1024
    if size_kb == 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError("yt-dlp produced an empty file.")

    logger.info(f"[ytdlp] Download complete: {dest.name} ({size_kb} KB) ✓")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Liveness check."""
    rapidapi_configured = bool(os.environ.get("RAPIDAPI_KEY", "").strip())
    return {
        "status": "ok",
        "strategy": "rapidapi" if rapidapi_configured else "ytdlp-fallback",
    }


@app.post("/extract")
def extract(
    body: ExtractRequest,
    x_relay_key: str | None = Header(default=None),
):
    """
    Download audio from a YouTube URL and return it as an MP3 stream.

    Strategy:
      - If RAPIDAPI_KEY is set → use RapidAPI youtube-mp36 (reliable, no bot issues)
      - Otherwise             → fall back to yt-dlp (may be blocked on datacenter IPs)
    """
    # 1. Auth
    _verify_key(x_relay_key)

    url = body.url.strip()
    logger.info(f"[extract] Received request | url={url}")

    # 2. URL validation
    _validate_youtube_url(url)

    # 3. Prepare a persistent temp file for the audio output
    persistent_tmp = Path(tempfile.mktemp(suffix=".mp3"))

    try:
        rapidapi_key = os.environ.get("RAPIDAPI_KEY", "").strip()

        if rapidapi_key:
            # ── Strategy A: RapidAPI ──────────────────────────────────────────
            logger.info("[extract] Strategy: RapidAPI youtube-mp36")
            video_id = _extract_video_id(url)
            _download_via_rapidapi(video_id, persistent_tmp, rapidapi_key)

        else:
            # ── Strategy B: yt-dlp fallback ───────────────────────────────────
            logger.warning(
                "[extract] RAPIDAPI_KEY not set — falling back to yt-dlp. "
                "This will likely fail on Render due to YouTube IP blocks."
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = Path(tmpdir) / "audio.mp3"
                _download_via_ytdlp(url, dest)
                # Move out of the temp dir before it's deleted
                import shutil
                shutil.copy2(dest, persistent_tmp)

    except RuntimeError as exc:
        persistent_tmp.unlink(missing_ok=True)
        logger.error(f"[extract] Download failed: {exc}")
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        persistent_tmp.unlink(missing_ok=True)
        logger.error(f"[extract] Unexpected error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal relay error.")

    # 4. Stream the file back, clean up after
    from fastapi.background import BackgroundTasks
    bg = BackgroundTasks()
    bg.add_task(_delete_file, persistent_tmp)

    logger.info(f"[extract] Sending response: {persistent_tmp.name}")
    return FileResponse(
        path=str(persistent_tmp),
        media_type="audio/mpeg",
        filename="audio.mp3",
        background=bg,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup helper
# ─────────────────────────────────────────────────────────────────────────────
def _delete_file(path: Path) -> None:
    """Delete a temp file after the response has been streamed."""
    try:
        path.unlink(missing_ok=True)
        logger.info(f"[cleanup] Deleted temp file: {path.name}")
    except Exception as exc:
        logger.warning(f"[cleanup] Could not delete {path}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Global error handler — never leak raw tracebacks
# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(f"[error] Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal relay error. Please try again."},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (for local testing: python main.py)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
