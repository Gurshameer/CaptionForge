import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.services.whisper_service import WhisperService

class MockSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

class MockTranscriptionInfo:
    def __init__(self, language, language_probability):
        self.language = language
        self.language_probability = language_probability

@patch("app.services.whisper_service.WhisperModel")
def test_transcribe_success(mock_whisper_model_class, tmp_path):
    """
    Test that WhisperService correctly parses segments and returns detected language
    when speech recognition is successful.
    """
    mock_model = MagicMock()
    mock_whisper_model_class.return_value = mock_model
    
    mock_segments = [
        MockSegment(0.0, 2.5, "Hello world"),
        MockSegment(2.5, 5.0, "This is a test subtitle.")
    ]
    mock_info = MockTranscriptionInfo("en", 0.999)
    mock_model.transcribe.return_value = (mock_segments, mock_info)
    
    # Create fake audio input
    audio_path = tmp_path / "mock_audio.wav"
    audio_path.write_bytes(b"dummy wav content")
    
    # Reset singleton state to inject mock class
    WhisperService._model = None
    service = WhisperService()
    
    segments, lang = service.transcribe(audio_path)
    
    # Assertions
    assert lang == "en"
    assert len(segments) == 2
    assert segments[0]["start"] == 0.0
    assert segments[0]["text"] == "Hello world"
    assert segments[1]["end"] == 5.0
    mock_model.transcribe.assert_called_once()

@patch("app.services.whisper_service.WhisperModel")
def test_transcribe_unsupported_language(mock_whisper_model_class, tmp_path):
    """
    Test that WhisperService throws a ValueError when the detected language
    is not in the supported language set (en, ru, ja, de, fr).
    """
    mock_model = MagicMock()
    mock_whisper_model_class.return_value = mock_model
    
    mock_segments = []
    # Spanish ('es') is unsupported
    mock_info = MockTranscriptionInfo("es", 0.95)
    mock_model.transcribe.return_value = (mock_segments, mock_info)
    
    audio_path = tmp_path / "mock_audio.wav"
    audio_path.write_bytes(b"dummy wav content")
    
    # Reset singleton state
    WhisperService._model = None
    service = WhisperService()
    
    with pytest.raises(ValueError) as exc_info:
        service.transcribe(audio_path)
        
    assert "Unsupported language 'es'" in str(exc_info.value)
