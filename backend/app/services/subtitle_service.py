from pathlib import Path
from typing import List, Dict, Any
from app.core.logging import logger

def format_timestamp(seconds: float) -> str:
    """
    Format numeric seconds into the standard SRT timestamp format: HH:MM:SS,mmm
    
    Args:
        seconds (float): Time in seconds.
        
    Returns:
        str: Formatted SRT timestamp.
    """
    # Prevent negative values
    seconds = max(0.0, seconds)
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    
    # Handle rounding overflows
    if milliseconds >= 1000:
        milliseconds -= 1000
        secs += 1
        if secs >= 60:
            secs -= 60
            minutes += 1
            if minutes >= 60:
                minutes -= 60
                hours += 1
                
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def generate_srt(segments: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Takes a list of subtitle segments and compiles them into a valid SRT file.
    
    Args:
        segments (List[Dict[str, Any]]): List of segments containing 'start', 'end', and 'text'.
        output_path (Path): Path to save the compiled SRT file.
        
    Returns:
        Path: Path to the generated SRT file.
        
    Raises:
        RuntimeError: If writing to the file fails.
    """
    logger.info(f"Generating SRT subtitle file at: {output_path}")
    
    # Ensure output parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Save file with UTF-8 encoding
        with open(output_path, "w", encoding="utf-8") as f:
            for idx, segment in enumerate(segments, start=1):
                start_sec = segment["start"]
                end_sec = segment["end"]
                text = segment["text"]
                
                start_time = format_timestamp(start_sec)
                end_time = format_timestamp(end_sec)
                
                f.write(f"{idx}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
                
        logger.info(f"Successfully generated SRT subtitle file: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to write SRT file: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate SRT file: {e}") from e


def format_timestamp_vtt(seconds: float) -> str:
    """
    Format numeric seconds into the standard VTT timestamp format: HH:MM:SS.mmm
    """
    # Prevent negative values
    seconds = max(0.0, seconds)
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    
    # Handle rounding overflows
    if milliseconds >= 1000:
        milliseconds -= 1000
        secs += 1
        if secs >= 60:
            secs -= 60
            minutes += 1
            if minutes >= 60:
                minutes -= 60
                hours += 1
                
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def generate_vtt(segments: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Takes a list of subtitle segments and compiles them into a valid VTT file.
    """
    logger.info(f"Generating VTT subtitle file at: {output_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for idx, segment in enumerate(segments, start=1):
                start_sec = segment["start"]
                end_sec = segment["end"]
                text = segment["text"]
                
                start_time = format_timestamp_vtt(start_sec)
                end_time = format_timestamp_vtt(end_sec)
                
                f.write(f"{idx}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
                
        logger.info(f"Successfully generated VTT subtitle file: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to write VTT file: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate VTT file: {e}") from e
