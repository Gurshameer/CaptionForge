import pytest
from fastapi.testclient import TestClient
from main import app
import shutil
from app.core.config import settings

@pytest.fixture
def client():
    # Utilizing 'with TestClient' runs the startup and shutdown lifespan events
    with TestClient(app) as c:
        yield c
    
    # Cleanup uploads and outputs to keep project clean
    if settings.upload_path.exists():
        shutil.rmtree(settings.upload_path)
    if settings.output_path.exists():
        shutil.rmtree(settings.output_path)

