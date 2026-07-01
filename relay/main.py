"""
relay/main.py
=============
CaptionForge Fly.io Relay — minimal YouTube audio download service.

Endpoints:
  GET  /health   → liveness check
  POST /extract  → download YouTube audio, stream it back

Auth: X-Relay-Key header must match RELAY_SECRET_KEY env var.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

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
    description="Minimal YouTube audio download relay for CaptionForge.",
    version="1.0.0",
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
        # No secret configured — refuse all requests to avoid an open relay
        logger.warning("[auth] RELAY_SECRET_KEY not set — rejecting all requests")
        raise HTTPException(status_code=401, detail="Relay is not configured (no secret set).")
    if not provided or provided.strip() != expected:
        logger.warning(f"[auth] Invalid X-Relay-Key: {provided!r}")
        raise HTTPException(status_code=401, detail="Invalid or missing X-Relay-Key header.")


# ─────────────────────────────────────────────────────────────────────────────
# URL validation
# ─────────────────────────────────────────────────────────────────────────────
_YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")

def _validate_youtube_url(url: str) -> None:
    """Reject non-YouTube URLs early so yt-dlp doesn't make unexpected outbound calls."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url.strip())
        if parsed.netloc not in _YOUTUBE_DOMAINS:
            raise ValueError(f"Not a YouTube URL: {url!r}")
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid or non-YouTube URL: {url!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Liveness check — Fly.io and the HF backend call this to verify the relay is up."""
    return {"status": "ok"}


@app.post("/extract")
def extract(
    body: ExtractRequest,
    x_relay_key: str | None = Header(default=None),
):
    """
    Download audio from a YouTube URL and return it as an MP3 stream.

    Steps:
      1. Verify X-Relay-Key auth header.
      2. Validate the URL is a YouTube URL.
      3. Run yt-dlp to download best audio, convert to mp3.
      4. Stream the mp3 back as the response body.
      5. Delete the temp file immediately after streaming.
    """
    # 1. Auth
    _verify_key(x_relay_key)

    url = body.url.strip()
    logger.info(f"[extract] Received request | url={url}")

    # 2. URL validation
    _validate_youtube_url(url)

    # 3. Download via yt-dlp into a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = str(Path(tmpdir) / "audio.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "128K",
            "--output", output_template,
            "--no-warnings",
            url,
        ]

        logger.info(f"[extract] Running yt-dlp for: {url}")
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=150,  # give yt-dlp 2.5 min max
            )
        except subprocess.TimeoutExpired:
            logger.error("[extract] yt-dlp timed out")
            raise HTTPException(
                status_code=504,
                detail="yt-dlp timed out while downloading the video."
            )

        if result.returncode != 0:
            stderr_snippet = result.stderr[-500:] if result.stderr else "(no stderr)"
            logger.error(f"[extract] yt-dlp failed (rc={result.returncode}): {stderr_snippet}")

            # Detect common non-retryable errors and give a helpful message
            lower = stderr_snippet.lower()
            if any(kw in lower for kw in ("private video", "video unavailable", "age-restricted",
                                           "geo-restricted", "members only", "sign in")):
                raise HTTPException(
                    status_code=422,
                    detail="Video is unavailable, private, age-restricted, or geo-blocked."
                )
            raise HTTPException(
                status_code=502,
                detail=f"yt-dlp extraction failed. The video may be unavailable. "
                       f"Details: {stderr_snippet[-200:]}"
            )

        # Find the downloaded file
        mp3_files = list(Path(tmpdir).glob("*.mp3"))
        if not mp3_files:
            # yt-dlp may have produced a different extension — grab whatever is there
            all_files = list(Path(tmpdir).iterdir())
            if not all_files:
                logger.error("[extract] yt-dlp produced no output file")
                raise HTTPException(status_code=502, detail="yt-dlp produced no output file.")
            audio_file = all_files[0]
        else:
            audio_file = mp3_files[0]

        size_kb = audio_file.stat().st_size // 1024
        logger.info(f"[extract] Download complete: {audio_file.name} ({size_kb} KB) — streaming back")

        if size_kb == 0:
            raise HTTPException(status_code=502, detail="yt-dlp produced an empty file.")

        # 4. Stream back — FileResponse reads the file before the temp dir is deleted
        # We copy to a second temp file outside the TemporaryDirectory so it persists
        # through the response streaming.
        import shutil
        persistent_tmp = Path(tempfile.mktemp(suffix=".mp3"))
        shutil.copy2(audio_file, persistent_tmp)

    # 5. Return the file; background task cleans it up after streaming
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
