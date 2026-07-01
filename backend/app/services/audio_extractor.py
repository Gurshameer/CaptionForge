import subprocess
from pathlib import Path
from app.core.logging import logger


def _get_ffmpeg_binary() -> str:
    """
    Return the path to an ffmpeg executable.

    Priority:
      1. static-ffmpeg Python package (installed via pip — works on Render free
         tier and any environment without system ffmpeg).
      2. System 'ffmpeg' on PATH (works in Docker / local dev where ffmpeg is
         installed via apt-get or homebrew).
    """
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()   # adds the bundled ffmpeg dir to PATH
        import shutil
        path = shutil.which("ffmpeg")
        if path:
            logger.info(f"Using static-ffmpeg binary: {path}")
            return path
    except ImportError:
        pass
    # Fall back to system ffmpeg (Dockerfile / local dev)
    return "ffmpeg"


# Resolved once at import time so every call reuses the same path.
_FFMPEG = _get_ffmpeg_binary()


def extract_audio(video_path: Path, output_audio_path: Path) -> Path:
    """
    Extracts the audio track from a video file using FFmpeg.
    Converts the output to WAV format (16kHz sample rate, mono channel, 16-bit PCM),
    which is optimal for Faster-Whisper ASR.

    Args:
        video_path (Path): Path to the input video file.
        output_audio_path (Path): Path where the extracted audio WAV will be saved.

    Returns:
        Path: Path to the extracted audio file.

    Raises:
        RuntimeError: If FFmpeg fails or is not found.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Input video file does not exist: {video_path}")

    # Build the FFmpeg command
    # -y: Overwrite output file if it exists
    # -i: Input video path
    # -vn: Disable video stream (extract audio only)
    # -acodec pcm_s16le: Set audio codec to PCM 16-bit little-endian
    # -ar 16000: Set audio sample rate to 16 kHz (standard for ASR models)
    # -ac 1: Convert to single audio channel (mono)
    cmd = [
        _FFMPEG,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_audio_path)
    ]

    logger.info(f"Executing FFmpeg command for task extraction: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logger.info(f"Successfully extracted audio to: {output_audio_path}")
        return output_audio_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg extraction failed with exit code {e.returncode}")
        logger.error(f"FFmpeg stderr: {e.stderr}")
        raise RuntimeError(f"FFmpeg extraction failed: {e.stderr}") from e
    except FileNotFoundError as e:
        logger.error("FFmpeg executable not found in system environment PATH.")
        raise RuntimeError("FFmpeg executable was not found in system PATH. Please install FFmpeg.") from e
