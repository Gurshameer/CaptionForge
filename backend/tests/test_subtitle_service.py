from pathlib import Path
from app.services.subtitle_service import format_timestamp, generate_srt

def test_format_timestamp():
    """
    Test that format_timestamp correctly formats fractional seconds into standard SRT format.
    Checks standard times, rounding, overflows, and safety boundaries.
    """
    # Standard times
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(65.520) == "00:01:05,520"
    
    # Rounding and overflow checks
    assert format_timestamp(59.9999) == "00:01:00,000"
    assert format_timestamp(3599.9999) == "01:00:00,000"
    
    # Negative bounds safety
    assert format_timestamp(-5.0) == "00:00:00,000"

def test_generate_srt(tmp_path):
    """
    Test that generate_srt correctly writes a list of segments into a valid SubRip format file.
    """
    segments = [
        {"start": 1.25, "end": 3.456, "text": "Hello world"},
        {"start": 4.0, "end": 7.89, "text": "This is CaptionForge"}
    ]
    output_path = tmp_path / "subtitles.srt"
    
    result_path = generate_srt(segments, output_path)
    
    assert result_path.exists()
    assert result_path == output_path
    
    content = output_path.read_text(encoding="utf-8")
    
    expected_content = (
        "1\n"
        "00:00:01,250 --> 00:00:03,456\n"
        "Hello world\n\n"
        "2\n"
        "00:00:04,000 --> 00:00:07,890\n"
        "This is CaptionForge\n\n"
    )
    
    assert content.replace("\r\n", "\n") == expected_content.replace("\r\n", "\n")
