import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from faster_whisper import WhisperModel
from app.core.config import settings
from app.core.logging import logger

# All 12 supported transcription languages
SUPPORTED_LANGUAGES = {
    "en", "hi", "fr", "de", "es",
    "it", "pt", "ru", "ja", "ko", "zh", "ar"
}

# Human-readable names for logging
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
}


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

    def transcribe(
        self,
        audio_path: Path,
        language_hint: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Transcribes the audio file and returns segment list + detected language.

        When language_hint is provided (and is not 'auto'), Whisper skips
        auto-detection and transcribes directly in that language — this
        improves accuracy for non-English content significantly.

        Args:
            audio_path (Path): Path to the input audio file (mono 16kHz wav).
            language_hint (Optional[str]): ISO 639-1 language code (e.g. 'hi',
                'fr') or None/'auto' to use Whisper's auto-detection.

        Returns:
            Tuple[List[Dict[str, Any]], str]: A tuple of:
                - List of segments (dicts containing 'start', 'end', 'text').
                - The language code used for transcription.

        Raises:
            ValueError: If the resulting language is not in the supported set.
            FileNotFoundError: If the input audio file does not exist.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model = self.get_model()

        # Determine whether to force a language or auto-detect
        forced_language = None
        if language_hint and language_hint.strip().lower() not in ("", "auto"):
            forced_language = language_hint.strip().lower()
            logger.info(f"Transcribing with forced language: '{forced_language}' ({LANGUAGE_NAMES.get(forced_language, forced_language)})")
        else:
            logger.info(f"Starting ASR transcription with auto language detection on: {audio_path}")

        # Run transcription
        # beam_size=5 is standard for a good speed/accuracy balance
        segments_generator, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            word_timestamps=False,
            language=forced_language  # None triggers auto-detection
        )

        detected_lang = info.language
        logger.info(f"Language result: '{detected_lang}' (probability: {info.language_probability:.4f})")

        if detected_lang not in SUPPORTED_LANGUAGES:
            logger.warning(f"Aborting task: Language '{detected_lang}' is not supported.")
            raise ValueError(
                f"Unsupported language '{detected_lang}'. "
                f"Supported languages: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )

        # Retrieve and format segments
        segments = []
        for segment in segments_generator:
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })

        logger.info(f"Transcription complete. Generated {len(segments)} segments in '{detected_lang}'.")
        return segments, detected_lang
