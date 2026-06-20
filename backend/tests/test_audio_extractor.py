import pytest
import subprocess
from pathlib import Path
from app.services.audio_extractor import extract_audio

def test_extract_audio(tmp_path):
    """
    Test that extract_audio successfully extracts audio from a valid video file.
    Creates a temporary 1-second silent MP4 video using FFmpeg and verifies the output.
    """
    video_path = tmp_path / "dummy_video.mp4"
    audio_output_path = tmp_path / "extracted_audio.wav"
    
    # Generate 1-second silent audio track wrapped in an MP4 container
    gen_cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=16000:cl=mono",
        "-t", "1",
        str(video_path)
    ]
    
    try:
        subprocess.run(gen_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to generate dummy video asset for test: {e.stderr.decode()}")
        
    assert video_path.exists(), "Test setup failed: Dummy video file was not created"
    
    # Execute extraction
    extracted_path = extract_audio(video_path, audio_output_path)
    
    # Assertions
    assert extracted_path.exists()
    assert extracted_path == audio_output_path
    assert audio_output_path.stat().st_size > 0

def test_extract_audio_missing_file(tmp_path):
    """Test that FilerNotFoundError is raised if the source file is missing."""
    video_path = tmp_path / "does_not_exist.mp4"
    audio_output_path = tmp_path / "extracted.wav"
    
    with pytest.raises(FileNotFoundError):
        extract_audio(video_path, audio_output_path)
