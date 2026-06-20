import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
from faster_whisper import WhisperModel
from app.core.config import settings
from app.core.logging import logger

SUPPORTED_LANGUAGES = {"en", "ru", "ja", "de", "fr"}

class WhisperService:
    _model: WhisperModel = None

    @classmethod
    def get_model(cls) -> WhisperModel:
        """
        Get or initialize the Faster-Whisper model singleton.
        Lazy loads the model on first call to optimize memory usage.
        """
        if cls._model is None:
            model_size = settings.WHISPER_MODEL
            device = settings.WHISPER_DEVICE
            compute_type = settings.WHISPER_COMPUTE_TYPE

            logger.info(f"Loading Faster-Whisper model '{model_size}' on '{device}' with compute_type '{compute_type}'...")
            try:
                cls._model = WhisperModel(
                    model_size_or_path=model_size,
                    device=device,
                    compute_type=compute_type
                )
                logger.info("Faster-Whisper model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load Faster-Whisper model: {e}", exc_info=True)
                raise RuntimeError(f"Whisper Model load failed: {e}") from e
        return cls._model

    def transcribe(self, audio_path: Path) -> Tuple[List[Dict[str, Any]], str]:
        """
        Transcribes the audio file, validates the language, and returns the segment list.
        
        Args:
            audio_path (Path): Path to the input audio file (mono 16kHz wav).
            
        Returns:
            Tuple[List[Dict[str, Any]], str]: A tuple of:
                - List of segments (dictionaries containing 'start', 'end', and 'text').
                - The detected language code (e.g. 'en').
                
        Raises:
            ValueError: If the detected language is not in the supported set.
            FileNotFoundError: If the input audio file does not exist.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model = self.get_model()
        logger.info(f"Starting ASR transcription on: {audio_path}")

        # Run transcription
        # beam_size=5 is standard for a good speed/accuracy balance
        segments_generator, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            word_timestamps=False
        )

        detected_lang = info.language
        logger.info(f"Language detection result: {detected_lang} (probability: {info.language_probability:.4f})")

        if detected_lang not in SUPPORTED_LANGUAGES:
            logger.warning(f"Aborting task: Detected language '{detected_lang}' is not supported.")
            raise ValueError(
                f"Unsupported language '{detected_lang}'. Allowed languages: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )

        # Retrieve and format segments
        segments = []
        for segment in segments_generator:
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })
            
        logger.info(f"Transcription successfully completed. Generated {len(segments)} segments.")
        return segments, detected_lang
