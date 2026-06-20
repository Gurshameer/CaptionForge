import os
from pathlib import Path
from fastapi import HTTPException, UploadFile
from app.core.config import settings
from app.core.logging import logger

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".mpeg", ".wmv"}

def initialize_directories():
    """Ensure upload, output and log directories exist."""
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.output_path.mkdir(parents=True, exist_ok=True)
    settings.log_path.mkdir(parents=True, exist_ok=True)
    logger.info("Application storage directories verified/created.")

def validate_uploaded_file(file: UploadFile):
    """
    Validate uploaded file extension and sizes before saving.
    Raises HTTPException if file is invalid.
    """
    filename = file.filename or ""
    file_ext = Path(filename).suffix.lower()
    
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        logger.warning(f"File validation failed: Unsupported extension {file_ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Supported extensions: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}"
        )

    file_size = getattr(file, "size", None)
    if file_size is not None and file_size > settings.MAX_UPLOAD_SIZE:
        logger.warning(f"File validation failed: File too large ({file_size} bytes)")
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. Maximum allowed size is {settings.MAX_UPLOAD_SIZE / (1024 * 1024):.1f} MB."
        )

def save_upload_file(file: UploadFile, task_id: str) -> Path:
    """Save an uploaded file to the uploads directory with a task prefix."""
    ext = Path(file.filename or "").suffix.lower()
    dest_path = settings.upload_path / f"{task_id}{ext}"
    
    # Double-check uploads directory exists
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    try:
        # Open file in binary write mode
        with open(dest_path, "wb") as buffer:
            total_bytes = 0
            # Read in 80KB chunks
            while chunk := file.file.read(81920):
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE:
                    buffer.close()
                    dest_path.unlink(missing_ok=True)
                    logger.warning(f"Upload aborted: File size exceeded limit during streaming.")
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE / (1024 * 1024):.1f} MB."
                    )
                buffer.write(chunk)
        logger.info(f"Successfully saved uploaded file: {dest_path}")
        return dest_path
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}", exc_info=True)
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

def cleanup_task_files(task_id: str):
    """Clean up uploaded video and temporary files associated with a task_id."""
    try:
        # Clean up files matching task_id in uploads folder (e.g. video and extracted audio wav)
        for file_path in settings.upload_path.glob(f"{task_id}.*"):
            file_path.unlink(missing_ok=True)
            logger.info(f"Cleaned up temporary upload file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to clean up uploads for task {task_id}: {e}")
