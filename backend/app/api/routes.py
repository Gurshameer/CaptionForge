import os
import uuid
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.api.schemas import TaskCreatedResponse, TaskStatusResponse
from app.utils.file_utils import validate_uploaded_file, save_upload_file, cleanup_task_files
from app.core.config import settings
from app.core.logging import logger
from app.services.audio_extractor import extract_audio
from app.services.whisper_service import WhisperService
from app.services.gemma_service import GemmaService
from app.services.subtitle_service import generate_srt

router = APIRouter(prefix="/api/v1/subtitles", tags=["Subtitles"])

# Thread-safe-ish in-memory task database
# In-memory dictionary matches V1 requirements.
tasks_db: Dict[str, Dict[str, Any]] = {}

def process_subtitle_generation(task_id: str, video_path: str):
    """
    Background worker function that performs audio extraction, language detection,
    ASR, transcript enhancement, and SRT compilation.
    """
    logger.info(f"Started background processing for task {task_id}")
    
    video_path_obj = Path(video_path)
    audio_path = settings.upload_path / f"{task_id}.wav"
    srt_path = settings.output_path / f"{task_id}.srt"
    
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
        raw_segments, detected_lang = whisper_service.transcribe(audio_path)
        
        tasks_db[task_id]["detected_language"] = detected_lang
        
        # 3. Transcript Enhancement
        tasks_db[task_id]["current_step"] = "transcript_enhancement"
        tasks_db[task_id]["progress"] = 70.0
        logger.info(f"Task {task_id}: Enhancing transcript text with Gemma...")
        
        gemma_service = GemmaService()
        enhanced_segments = gemma_service.enhance_transcript(raw_segments, detected_lang)
        
        # 4. SRT Compilation
        tasks_db[task_id]["current_step"] = "subtitle_generation"
        tasks_db[task_id]["progress"] = 90.0
        logger.info(f"Task {task_id}: Writing subtitle file...")
        
        generate_srt(enhanced_segments, srt_path)
        
        # Mark Task as Complete
        tasks_db[task_id]["status"] = "COMPLETED"
        tasks_db[task_id]["current_step"] = "completed"
        tasks_db[task_id]["progress"] = 100.0
        tasks_db[task_id]["srt_path"] = str(srt_path)
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
    file: UploadFile = File(..., description="Video file to generate subtitles for")
):
    """
    Upload a video file to start the subtitle generation task.
    """
    # 1. Validate file (extension and size)
    validate_uploaded_file(file)

    # 2. Generate task ID
    task_id = str(uuid.uuid4())
    logger.info(f"Received upload request. Generated Task ID: {task_id}")

    # 3. Save file asynchronously
    video_path = save_upload_file(file, task_id)

    # 4. Initialize task DB entry
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "PENDING",
        "progress": 0.0,
        "current_step": "upload_complete",
        "detected_language": None,
        "error": None,
        "video_path": str(video_path),
        "srt_path": None,
        "original_filename": file.filename
    }

    # 5. Dispatch task to FastAPI BackgroundTasks
    background_tasks.add_task(process_subtitle_generation, task_id, str(video_path))

    return TaskCreatedResponse(
        task_id=task_id,
        status="PENDING",
        message="Video uploaded successfully. Subtitle generation queued."
    )

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
