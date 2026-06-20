import pytest
from unittest.mock import MagicMock, patch
from app.services.gemma_service import GemmaService
from app.core.config import settings

def test_gemma_service_no_api_key():
    """
    Test that GemmaService gracefully bypasses correction and returns original segments
    when the API key is not configured.
    """
    settings.OPENROUTER_API_KEY = ""
    service = GemmaService()
    
    segments = [{"start": 0.0, "end": 2.5, "text": "raw transcription"}]
    result = service.enhance_transcript(segments, "en")
    
    assert result == segments

@patch("app.services.gemma_service.OpenAI")
def test_gemma_service_success(mock_openai_class):
    """
    Test that GemmaService correctly requests corrections from OpenAI client
    and returns parsed, enhanced text.
    """
    settings.OPENROUTER_API_KEY = "sk-test-key-12345"
    
    # Mock client and completion create
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '```json\n[{"start": 0.0, "end": 2.5, "text": "Enhanced Transcription."}]\n```'
    mock_client.chat.completions.create.return_value = mock_response
    
    service = GemmaService()
    segments = [{"start": 0.0, "end": 2.5, "text": "raw transcription"}]
    
    result = service.enhance_transcript(segments, "en")
    
    assert len(result) == 1
    assert result[0]["text"] == "Enhanced Transcription."
    assert result[0]["start"] == 0.0
    mock_client.chat.completions.create.assert_called_once()

@patch("app.services.gemma_service.OpenAI")
def test_gemma_service_count_mismatch(mock_openai_class):
    """
    Test that GemmaService returns original segments if the response JSON contains
    a different number of segments than the input.
    """
    settings.OPENROUTER_API_KEY = "sk-test-key-12345"
    
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    # Return 2 items instead of 1
    mock_response.choices[0].message.content = (
        '[{"start": 0.0, "end": 2.5, "text": "Enhanced 1"}, '
        '{"start": 2.5, "end": 5.0, "text": "Enhanced 2"}]'
    )
    mock_client.chat.completions.create.return_value = mock_response
    
    service = GemmaService()
    segments = [{"start": 0.0, "end": 2.5, "text": "raw transcription"}]
    
    result = service.enhance_transcript(segments, "en")
    
    # Count mismatch -> fallback to original input
    assert result == segments
