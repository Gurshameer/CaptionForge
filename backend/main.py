from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import logger
from app.utils.file_utils import initialize_directories
from app.api.routes import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run directory initialization
    logger.info("Initializing CaptionForge storage directories...")
    initialize_directories()
    logger.info("CaptionForge application successfully started.")
    yield
    logger.info("CaptionForge application shutting down.")

app = FastAPI(
    title="CaptionForge API",
    description="AI Subtitle Generator API using Faster-Whisper and Gemma 3:12B",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register subtitle router
app.include_router(api_router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to CaptionForge API",
        "status": "running",
        "environment": settings.ENV
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

