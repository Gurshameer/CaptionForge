import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
import uuid
import os
from pathlib import Path
from app.core.config import settings
from app.core.logging import logger
from fastapi import HTTPException

def download_youtube_video(url: str, task_id: str) -> Path:
    """
    Downloads a YouTube video to the uploads directory using yt-dlp.
    Returns the path to the downloaded video.
    """
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    
    # Template for output file
    outtmpl = str(settings.upload_path / f"{task_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'legacyserverconnect': True,
        'nocheckcertificate': True,
    }

    # If the user has provided YOUTUBE_COOKIES as an environment variable (e.g. via Hugging Face Secrets),
    # write them to a temporary file and pass it to yt-dlp to bypass bot detection on datacenter IPs.
    youtube_cookies = os.environ.get('YOUTUBE_COOKIES')
    cookie_file_path = None
    if youtube_cookies:
        cookie_file_path = '/tmp/youtube_cookies.txt'
        with open(cookie_file_path, 'w', encoding='utf-8') as f:
            f.write(youtube_cookies)
        ydl_opts['cookiefile'] = cookie_file_path

    try:
        logger.info(f"Downloading YouTube video {url} for task {task_id}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            ext = info_dict.get('ext', 'mp4')
            downloaded_file = settings.upload_path / f"{task_id}.{ext}"
            
            if not downloaded_file.exists():
                raise FileNotFoundError(f"File {downloaded_file} not found after download.")
            
            logger.info(f"Successfully downloaded YouTube video to {downloaded_file}")
            return downloaded_file
    except Exception as e:
        logger.error(f"Failed to download YouTube video: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to download video from URL: {str(e)}")
