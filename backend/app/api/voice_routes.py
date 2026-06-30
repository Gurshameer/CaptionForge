import os
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.api.schemas import VoiceTaskCreatedResponse, VoiceTaskStatusResponse
from app.services.voice_service import VoiceService, AVAILABLE_VOICES
from app.services.clone_service import CloneService
from app.services.gemma_service import GemmaService
from app.core.config import settings
from app.core.logging import logger

router = APIRouter(prefix="/api/v1/voice", tags=["Voice Generation"])

# Isolated in-memory task database for voice generation tasks
voice_tasks_db: Dict[str, Dict[str, Any]] = {}


def process_voice_generation(task_id: str, text: str, voice_id: str, language: str):
    """Background task for Kokoro preset voice generation."""
    logger.info(f"Task {task_id}: Starting preset voice generation (Voice: {voice_id})")
    
    voice_tasks_db[task_id]["status"] = "PROCESSING"
    voice_tasks_db[task_id]["current_step"] = "generating_audio"
    voice_tasks_db[task_id]["progress"] = 50.0

    try:
        # Determine target language from the selected voice
        target_lang = AVAILABLE_VOICES.get(voice_id, {}).get("lang", language)

        # Translation step
        voice_tasks_db[task_id]["status"] = "PROCESSING"
        voice_tasks_db[task_id]["current_step"] = "translating"
        voice_tasks_db[task_id]["progress"] = 25.0
        
        gemma_service = GemmaService()
        translated_text = gemma_service.translate_text_for_tts(text, target_language=target_lang)

        # Audio Generation step
        voice_tasks_db[task_id]["current_step"] = "generating_audio"
        voice_tasks_db[task_id]["progress"] = 50.0

        output_path = settings.audio_output_path / f"{task_id}.wav"
        
        voice_service = VoiceService()
        voice_service.generate(
            text=translated_text,
            voice_id=voice_id,
            output_path=output_path
        )

        voice_tasks_db[task_id]["status"] = "COMPLETED"
        voice_tasks_db[task_id]["current_step"] = "completed"
        voice_tasks_db[task_id]["progress"] = 100.0
        voice_tasks_db[task_id]["audio_path"] = str(output_path)
        logger.info(f"Task {task_id}: Preset voice generation completed successfully.")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        voice_tasks_db[task_id]["status"] = "FAILED"
        voice_tasks_db[task_id]["error"] = str(e)


def process_voice_cloning(task_id: str, text: str, reference_audio_path: str, language: str, exaggeration: float = 0.5, cfg_weight: float = 0.5):
    """Background task for Chatterbox voice cloning."""
    logger.info(f"Task {task_id}: Starting voice cloning (Reference: {reference_audio_path})")
    
    voice_tasks_db[task_id]["status"] = "PROCESSING"
    voice_tasks_db[task_id]["current_step"] = "translating"
    voice_tasks_db[task_id]["progress"] = 25.0

    try:
        # Translation step
        gemma_service = GemmaService()
        translated_text = gemma_service.translate_text_for_tts(text, target_language=language)

        voice_tasks_db[task_id]["current_step"] = "cloning_audio"
        voice_tasks_db[task_id]["progress"] = 50.0

        output_path = settings.audio_output_path / f"{task_id}_cloned.wav"
        
        clone_service = CloneService()
        clone_service.clone(
            text=translated_text,
            reference_audio_path=Path(reference_audio_path),
            output_path=output_path,
            language=language,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight
        )

        voice_tasks_db[task_id]["status"] = "COMPLETED"
        voice_tasks_db[task_id]["current_step"] = "completed"
        voice_tasks_db[task_id]["progress"] = 100.0
        voice_tasks_db[task_id]["audio_path"] = str(output_path)
        logger.info(f"Task {task_id}: Voice cloning completed successfully.")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        voice_tasks_db[task_id]["status"] = "FAILED"
        voice_tasks_db[task_id]["error"] = str(e)
    finally:
        # Cleanup the reference audio file
        try:
            if os.path.exists(reference_audio_path):
                os.remove(reference_audio_path)
                logger.info(f"Cleaned up reference audio: {reference_audio_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up reference audio: {e}")


@router.get("/voices")
async def list_voices():
    """List all available preset Kokoro voices."""
    return {"voices": AVAILABLE_VOICES}


@router.post("/generate", response_model=VoiceTaskCreatedResponse, status_code=202)
async def generate_voice(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to synthesize"),
    voice_id: str = Form(..., description="ID of the preset voice"),
    language: str = Form(default="en", description="Language code")
):
    """Generate speech using a preset Kokoro voice."""
    if voice_id not in AVAILABLE_VOICES:
        raise HTTPException(status_code=400, detail=f"Unknown voice ID: {voice_id}")

    task_id = str(uuid.uuid4())
    
    voice_tasks_db[task_id] = {
        "task_id": task_id,
        "mode": "preset",
        "status": "PENDING",
        "progress": 0.0,
        "current_step": "queued",
        "error": None,
        "audio_path": None
    }

    background_tasks.add_task(process_voice_generation, task_id, text, voice_id, language)

    return VoiceTaskCreatedResponse(
        task_id=task_id,
        status="PENDING",
        message="Voice generation queued."
    )


@router.post("/clone", response_model=VoiceTaskCreatedResponse, status_code=202)
async def clone_voice(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to synthesize"),
    reference_audio: UploadFile = File(..., description="Reference audio file (WAV/MP3/OGG/FLAC/M4A/AAC)"),
    language: str = Form(default="en", description="Language code"),
    exaggeration: float = Form(default=0.5, description="Expressiveness exaggeration (0.0 - 1.0)"),
    cfg_weight: float = Form(default=0.5, description="Expressiveness cfg_weight (0.0 - 1.0)")
):
    """Clone a voice from a reference audio file using Chatterbox."""
    if len(text) > settings.VOICE_TEXT_MAX_CHARS:
        raise HTTPException(
            status_code=400, 
            detail=f"Text exceeds the {settings.VOICE_TEXT_MAX_CHARS} character limit for cloning."
        )

    task_id = str(uuid.uuid4())
    
    # Save the reference audio temporarily
    ref_dir = settings.base_dir / settings.VOICE_REFERENCE_DIR
    ref_dir.mkdir(parents=True, exist_ok=True)
    
    ext = os.path.splitext(reference_audio.filename)[1] or ".wav"
    ref_path = ref_dir / f"{task_id}_ref{ext}"
    
    with open(ref_path, "wb") as buffer:
        shutil.copyfileobj(reference_audio.file, buffer)

    voice_tasks_db[task_id] = {
        "task_id": task_id,
        "mode": "clone",
        "status": "PENDING",
        "progress": 0.0,
        "current_step": "queued",
        "error": None,
        "audio_path": None
    }

    background_tasks.add_task(process_voice_cloning, task_id, text, str(ref_path), language, exaggeration, cfg_weight)

    return VoiceTaskCreatedResponse(
        task_id=task_id,
        status="PENDING",
        message="Voice cloning queued. This may take 1-2 minutes."
    )


@router.get("/status/{task_id}", response_model=VoiceTaskStatusResponse)
async def get_voice_task_status(task_id: str):
    """Retrieve the status of a voice generation/cloning task."""
    task = voice_tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    download_url = None
    if task["status"] == "COMPLETED":
        download_url = f"/api/v1/voice/download/{task_id}"

    return VoiceTaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        current_step=task["current_step"],
        error=task["error"],
        download_url=download_url,
        mode=task.get("mode")
    )


@router.get("/download/{task_id}")
async def download_voice_audio(task_id: str):
    """Download the generated audio file."""
    task = voice_tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"Audio file not ready. Status: {task['status']}")

    audio_path = task.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    suffix = "_cloned" if task.get("mode") == "clone" else ""
    
    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=f"voice_{task_id}{suffix}.wav"
    )
