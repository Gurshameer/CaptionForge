from unittest.mock import MagicMock, patch

def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"

def test_upload_invalid_extension(client):
    # Test uploading a file with an invalid extension (should return 400)
    response = client.post(
        "/api/v1/subtitles/upload",
        files={"file": ("test.txt", b"dummy content", "text/plain")}
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]

@patch("app.api.routes.WhisperService")
@patch("app.api.routes.GemmaService")
def test_full_subtitle_generation_flow(mock_gemma_class, mock_whisper_class, client):
    """
    Test the full subtitle generation flow: upload -> background tasks -> status -> download.
    Mocks FFmpeg, Whisper ASR, and Gemma enhancement for immediate validation.
    """
    # 1. Setup Whisper Mock
    mock_whisper = MagicMock()
    mock_whisper_class.return_value = mock_whisper
    mock_whisper.transcribe.return_value = (
        [{"start": 0.0, "end": 2.5, "text": "hello world"}],
        "en"
    )
    
    # 2. Setup Gemma Mock
    mock_gemma = MagicMock()
    mock_gemma_class.return_value = mock_gemma
    mock_gemma.enhance_transcript.return_value = [
        {"start": 0.0, "end": 2.5, "text": "Hello World!"}
    ]
    
    # 3. Setup Audio Extractor Mock to bypass local subprocess FFmpeg
    with patch("app.api.routes.extract_audio") as mock_extract:
        response = client.post(
            "/api/v1/subtitles/upload",
            files={"file": ("test.mp4", b"dummy video content", "video/mp4")}
        )
        
        # Request accepted and queued
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        
        mock_extract.assert_called_once()
        mock_whisper.transcribe.assert_called_once()
        mock_gemma.enhance_transcript.assert_called_once()
        
        # 4. Check completed status
        status_resp = client.get(f"/api/v1/subtitles/status/{task_id}")
        assert status_resp.status_code == 200
        
        data = status_resp.json()
        assert data["status"] == "COMPLETED"
        assert data["detected_language"] == "en"
        assert "download" in data["download_url"]
        
        # 5. Retrieve compiled subtitle download file
        download_resp = client.get(f"/api/v1/subtitles/download/{task_id}")
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"] == "application/x-subrip"
        
        content = download_resp.content.decode("utf-8")
        assert "1" in content
        assert "00:00:00,000 --> 00:00:02,500" in content
        assert "Hello World!" in content
