import os
import uuid
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.api.schemas import TaskCreatedResponse, TaskStatusResponse
from app.utils.file_utils import validate_uploaded_file, save_upload_file, cleanup_task_files
from app.core.config import settings
from app.core.logging import logger
from app.services.audio_extractor import extract_audio
from app.services.whisper_service import WhisperService
from app.services.gemma_service import GemmaService
from app.services.subtitle_service import generate_srt, generate_vtt

router = APIRouter(prefix="/api/v1/subtitles", tags=["Subtitles"])

# Thread-safe-ish in-memory task database
# In-memory dictionary matches V1 requirements.
tasks_db: Dict[str, Dict[str, Any]] = {}


def process_subtitle_generation(task_id: str, video_path: str, language_hint: str = "auto"):
    """
    Background worker function that performs audio extraction, language detection,
    ASR, transcript enhancement, and SRT compilation.

    Args:
        task_id (str): Unique task identifier.
        video_path (str): Path to the uploaded video file.
        language_hint (str): ISO 639-1 language code (e.g. 'hi') or 'auto'.
    """
    logger.info(f"Started background processing for task {task_id} (language_hint='{language_hint}')")

    video_path_obj = Path(video_path)
    audio_path = settings.upload_path / f"{task_id}.wav"
    srt_path = settings.output_path / f"{task_id}.srt"
    vtt_path = settings.output_path / f"{task_id}.vtt"

    try:
        # 1. Audio Extraction
        tasks_db[task_id]["status"] = "PROCESSING"
        tasks_db[task_id]["current_step"] = "audio_extraction"
        tasks_db[task_id]["progress"] = 15.0
        logger.info(f"Task {task_id}: Extracting audio stream...")
        extract_audio(video_path_obj, audio_path)

        # 2. Speech Recognition (ASR)
        tasks_db[task_id]["current_step"] = "speech_recognition"
        tasks_db[task_id]["progress"] = 40.0
        logger.info(f"Task {task_id}: Transcribing audio...")

        whisper_service = WhisperService()
        raw_segments, detected_lang = whisper_service.transcribe(
            audio_path,
            language_hint=language_hint if language_hint != "auto" else None
        )

        tasks_db[task_id]["detected_language"] = detected_lang

        # 3. Transcript Enhancement
        tasks_db[task_id]["current_step"] = "transcript_enhancement"
        tasks_db[task_id]["progress"] = 70.0
        logger.info(f"Task {task_id}: Enhancing transcript text with Gemma (language: {detected_lang})...")

        gemma_service = GemmaService()
        enhanced_segments = gemma_service.enhance_transcript(raw_segments, detected_lang)

        # 4. SRT Compilation
        tasks_db[task_id]["current_step"] = "subtitle_generation"
        tasks_db[task_id]["progress"] = 90.0
        logger.info(f"Task {task_id}: Writing subtitle files...")

        generate_srt(enhanced_segments, srt_path)
        generate_vtt(enhanced_segments, vtt_path)

        # Mark Task as Complete
        tasks_db[task_id]["status"] = "COMPLETED"
        tasks_db[task_id]["current_step"] = "completed"
        tasks_db[task_id]["progress"] = 100.0
        tasks_db[task_id]["srt_path"] = str(srt_path)
        tasks_db[task_id]["vtt_path"] = str(vtt_path)
        logger.info(f"Task {task_id} completed successfully. Subtitle output: {srt_path}")

    except Exception as e:
        logger.error(f"Failed to process subtitle generation for task {task_id}: {e}", exc_info=True)
        tasks_db[task_id]["status"] = "FAILED"
        tasks_db[task_id]["error"] = str(e)
    finally:
        # Cleanup temporary files (uploaded video and extracted audio WAV)
        cleanup_task_files(task_id)


@router.post("/upload", response_model=TaskCreatedResponse, status_code=202)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Video file to generate subtitles for"),
    language: str = Form(
        default="auto",
        description="ISO 639-1 language code (e.g. 'hi', 'fr') or 'auto' for auto-detection"
    )
):
    """
    Upload a video file to start the subtitle generation task.

    Optionally specify a language to improve transcription accuracy.
    Supported: en, hi, fr, de, es, it, pt, ru, ja, ko, zh, ar.
    """
    # 1. Validate file (extension and size)
    validate_uploaded_file(file)

    # 2. Generate task ID
    task_id = str(uuid.uuid4())
    logger.info(f"Received upload request. Generated Task ID: {task_id}, language: '{language}'")

    # 3. Save file asynchronously
    video_path = save_upload_file(file, task_id)

    # 4. Initialize task DB entry
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "PENDING",
        "progress": 0.0,
        "current_step": "upload_complete",
        "selected_language": language,
        "detected_language": None,
        "error": None,
        "video_path": str(video_path),
        "srt_path": None,
        "original_filename": file.filename
    }

    # 5. Dispatch task to FastAPI BackgroundTasks
    background_tasks.add_task(
        process_subtitle_generation,
        task_id,
        str(video_path),
        language
    )

    return TaskCreatedResponse(
        task_id=task_id,
        status="PENDING",
        message="Video uploaded successfully. Subtitle generation queued."
    )

from pydantic import BaseModel
from app.services.yt_download_service import download_youtube_video

class UrlUploadRequest(BaseModel):
    url: str
    language: str = "auto"

@router.post("/url", response_model=TaskCreatedResponse, status_code=202)
async def upload_youtube_url(
    request: UrlUploadRequest,
    background_tasks: BackgroundTasks
):
    """
    Provide a YouTube URL to download and start the subtitle generation task.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received URL upload request. URL: {request.url}, Task ID: {task_id}")

    try:
        # Download synchronously or ideally asynchronously? 
        # For simplicity, do it before queuing, or queue it too.
        # Actually yt-dlp can take a while. We should queue it as part of the background task.
        # But for now, we can download it synchronously and return 202, or 
        # we can put yt-dlp in the background task. 
        # Given the architecture, doing yt-dlp synchronously blocks the API response.
        # Let's do it synchronously here for simplicity, or modify process_subtitle_generation.
        # Let's do yt-dlp synchronously as the prompt didn't say otherwise, and it's easier to handle errors.
        video_path = download_youtube_video(request.url, task_id)
        
        # Initialize task DB entry
        tasks_db[task_id] = {
            "task_id": task_id,
            "status": "PENDING",
            "progress": 0.0,
            "current_step": "upload_complete",
            "selected_language": request.language,
            "detected_language": None,
            "error": None,
            "video_path": str(video_path),
            "srt_path": None,
            "vtt_path": None,
            "original_filename": f"youtube_{task_id}.mp4"
        }

        # Dispatch task to FastAPI BackgroundTasks
        background_tasks.add_task(
            process_subtitle_generation,
            task_id,
            str(video_path),
            request.language
        )

        return TaskCreatedResponse(
            task_id=task_id,
            status="PENDING",
            message="YouTube video downloaded successfully. Subtitle generation queued."
        )
    except Exception as e:
        logger.error(f"Failed to process YouTube URL: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to process YouTube URL: {str(e)}")

@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Retrieve the current status of a subtitle generation task.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    download_url = None
    if task["status"] == "COMPLETED":
        download_url = f"/api/v1/subtitles/download/{task_id}"

    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        current_step=task["current_step"],
        selected_language=task["selected_language"],
        detected_language=task["detected_language"],
        error=task["error"],
        download_url=download_url
    )


@router.get("/download/{task_id}")
async def download_srt(task_id: str):
    """
    Download the generated SRT file.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"SRT file not ready. Task status is: {task['status']}")

    srt_path = task.get("srt_path")
    if not srt_path or not os.path.exists(srt_path):
        logger.error(f"Task status is COMPLETED, but SRT file is missing at path: {srt_path}")
        raise HTTPException(status_code=404, detail="Subtitle file not found on disk")

    original_name = task.get("original_filename", f"subtitle_{task_id}")
    base_name = os.path.splitext(original_name)[0]

    return FileResponse(
        path=srt_path,
        media_type="application/x-subrip",
        filename=f"{base_name}.srt"
    )

@router.get("/download-vtt/{task_id}")
async def download_vtt(task_id: str):
    """
    Download the generated VTT file.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"VTT file not ready. Task status is: {task['status']}")

    vtt_path = task.get("vtt_path")
    if not vtt_path or not os.path.exists(vtt_path):
        logger.error(f"Task status is COMPLETED, but VTT file is missing at path: {vtt_path}")
        raise HTTPException(status_code=404, detail="Subtitle file not found on disk")

    original_name = task.get("original_filename", f"subtitle_{task_id}")
    base_name = os.path.splitext(original_name)[0]

    return FileResponse(
        path=vtt_path,
        media_type="text/vtt",
        filename=f"{base_name}.vtt"
    )

import subprocess

@router.post("/burn/{task_id}")
async def burn_subtitles(task_id: str):
    """
    Burn subtitles into the original video and return the URL to download it.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Task not completed yet.")

    video_path = task.get("video_path")
    srt_path = task.get("srt_path")

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Original video not found.")
    
    if not srt_path or not os.path.exists(srt_path):
        raise HTTPException(status_code=404, detail="Subtitle file not found.")

    original_name = task.get("original_filename", f"video_{task_id}")
    base_name = os.path.splitext(original_name)[0]
    output_filename = f"{base_name}_subbed.mp4"
    output_path = settings.output_path / f"burned_{task_id}.mp4"

    # If already burned, just return it
    if output_path.exists():
        task["burned_video_path"] = str(output_path)
        return {"download_url": f"/api/v1/subtitles/download-burned/{task_id}"}

    # Escape path for ffmpeg subtitles filter: windows paths need careful escaping.
    # A simpler way in python is to change cwd, or just use absolute path with forward slashes
    safe_srt_path = str(srt_path).replace('\\', '/')
    # FFmpeg subtitles filter requires escaping colons and backslashes
    safe_srt_path = safe_srt_path.replace(':', '\\:')

    # ffmpeg -i input.mp4 -vf subtitles=sub.srt output.mp4
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{safe_srt_path}'",
        "-c:a", "copy",
        str(output_path)
    ]
    
    try:
        logger.info(f"Running ffmpeg to burn subtitles: {' '.join(cmd)}")
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.returncode != 0:
            logger.error(f"ffmpeg failed: {process.stderr}")
            raise HTTPException(status_code=500, detail="Failed to burn subtitles into video.")
        
        task["burned_video_path"] = str(output_path)
        return {"download_url": f"/api/v1/subtitles/download-burned/{task_id}"}
    except Exception as e:
        logger.error(f"Error burning subtitles: {e}")
        raise HTTPException(status_code=500, detail="Failed to burn subtitles into video.")

@router.get("/download-burned/{task_id}")
async def download_burned_video(task_id: str):
    """
    Download the burned-in video.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    burned_path = task.get("burned_video_path")
    if not burned_path or not os.path.exists(burned_path):
        raise HTTPException(status_code=404, detail="Burned video not found. Generate it first.")

    original_name = task.get("original_filename", f"video_{task_id}")
    base_name = os.path.splitext(original_name)[0]

    return FileResponse(
        path=burned_path,
        media_type="video/mp4",
        filename=f"{base_name}_subbed.mp4"
    )
