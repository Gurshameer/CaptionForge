from pydantic import BaseModel, Field
from typing import Optional

class TaskStatusResponse(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the subtitle generation task")
    status: str = Field(..., description="Current status of the task: 'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'")
    progress: Optional[float] = Field(None, description="Percentage progress (0.0 to 100.0)")
    current_step: Optional[str] = Field(None, description="The step currently being executed")
    detected_language: Optional[str] = Field(None, description="Detected language code, if completed ASR")
    error: Optional[str] = Field(None, description="Error message, if task failed")
    download_url: Optional[str] = Field(None, description="URL to download the completed SRT file")

class TaskCreatedResponse(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the created task")
    status: str = Field(..., description="Initial status of the task")
    message: str = Field(..., description="Confirmation message")
