"""
voice_service.py — Kokoro TTS preset voice generation.

Uses the kokoro Python library (82M ONNX model) which runs efficiently
on CPU — suitable for Hugging Face Spaces free tier.
"""

from pathlib import Path
from typing import Optional
from app.core.logging import logger

# -------------------------------------------------------------------------
# Preset voice catalogue
# Each entry maps a Kokoro voice ID to display metadata.
# Language codes match the 12 supported subtitle languages where possible.
# -------------------------------------------------------------------------
AVAILABLE_VOICES = {
    # American English — Female
    "af_heart":   {"name": "Heart",    "gender": "Female", "accent": "American English",  "lang": "en"},
    "af_bella":   {"name": "Bella",    "gender": "Female", "accent": "American English",  "lang": "en"},
    "af_nicole":  {"name": "Nicole",   "gender": "Female", "accent": "American English",  "lang": "en"},
    "af_sarah":   {"name": "Sarah",    "gender": "Female", "accent": "American English",  "lang": "en"},
    # American English — Male
    "am_adam":    {"name": "Adam",     "gender": "Male",   "accent": "American English",  "lang": "en"},
    "am_michael": {"name": "Michael",  "gender": "Male",   "accent": "American English",  "lang": "en"},
    # British English
    "bf_emma":    {"name": "Emma",     "gender": "Female", "accent": "British English",   "lang": "en"},
    "bm_george":  {"name": "George",   "gender": "Male",   "accent": "British English",   "lang": "en"},
    # French
    "ff_siwis":   {"name": "Siwis",    "gender": "Female", "accent": "French",            "lang": "fr"},
    # Hindi
    "hf_alpha":   {"name": "Alpha",    "gender": "Female", "accent": "Hindi",             "lang": "hi"},
    "hm_omega":   {"name": "Omega",    "gender": "Male",   "accent": "Hindi",             "lang": "hi"},
    # Japanese
    "jf_alpha":   {"name": "Alpha",    "gender": "Female", "accent": "Japanese",          "lang": "ja"},
    "jm_kumo":    {"name": "Kumo",     "gender": "Male",   "accent": "Japanese",          "lang": "ja"},
    # Chinese
    "zf_xiaobei": {"name": "Xiaobei",  "gender": "Female", "accent": "Chinese",           "lang": "zh"},
    "zm_yunxi":   {"name": "Yunxi",    "gender": "Male",   "accent": "Chinese",           "lang": "zh"},
    # Spanish
    "ef_dora":    {"name": "Dora",     "gender": "Female", "accent": "Spanish",           "lang": "es"},
    # Portuguese
    "pf_dora":    {"name": "Dora",     "gender": "Female", "accent": "Portuguese",        "lang": "pt"},
    # Italian
    "if_sara":    {"name": "Sara",     "gender": "Female", "accent": "Italian",           "lang": "it"},
}


class VoiceService:
    """Kokoro TTS wrapper for preset voice generation on CPU."""

    _pipeline = None  # Class-level singleton to avoid reloading the model

    @classmethod
    def _get_pipeline(cls):
        """
        Lazy-load the Kokoro pipeline on first use.
        Keeps the model in memory for subsequent requests.
        """
        if cls._pipeline is None:
            logger.info("Loading Kokoro TTS pipeline (82M model)...")
            try:
                from kokoro import KPipeline
                # 'a' = American English phonemizer; works for multilingual voices too
                cls._pipeline = KPipeline(lang_code='a')
                logger.info("Kokoro TTS pipeline loaded successfully.")
            except ImportError:
                raise RuntimeError(
                    "Kokoro is not installed. Run: pip install kokoro soundfile"
                )
            except Exception as e:
                logger.error(f"Failed to load Kokoro pipeline: {e}", exc_info=True)
                raise RuntimeError(f"Kokoro pipeline load failed: {e}") from e
        return cls._pipeline

    def generate(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        speed: float = 1.0
    ) -> Path:
        """
        Generate speech from text using a Kokoro preset voice.

        Args:
            text (str): Input text to synthesize.
            voice_id (str): A key from AVAILABLE_VOICES (e.g. 'af_heart').
            output_path (Path): Where to save the output WAV file.
            speed (float): Speech speed multiplier (0.5–2.0). Default 1.0.

        Returns:
            Path: Path to the generated WAV file.

        Raises:
            ValueError: If voice_id is not in the AVAILABLE_VOICES catalogue.
            RuntimeError: If audio generation or file write fails.
        """
        if voice_id not in AVAILABLE_VOICES:
            raise ValueError(
                f"Unknown voice '{voice_id}'. "
                f"Available voices: {', '.join(AVAILABLE_VOICES.keys())}"
            )

        pipeline = self._get_pipeline()
        voice_meta = AVAILABLE_VOICES[voice_id]
        logger.info(
            f"Generating speech with Kokoro voice '{voice_id}' "
            f"({voice_meta['name']}, {voice_meta['accent']})..."
        )

        try:
            import soundfile as sf
            import numpy as np

            all_audio = []

            # Kokoro returns a generator of (graphemes, phonemes, audio_tensor) tuples
            for _, _, audio in pipeline(text, voice=voice_id, speed=speed):
                all_audio.append(audio.numpy())

            if not all_audio:
                raise RuntimeError("Kokoro returned no audio segments.")

            # Concatenate all chunks and write WAV
            combined = np.concatenate(all_audio, axis=0)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_path), combined, samplerate=24000)

            logger.info(f"Kokoro audio saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Kokoro voice generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Voice generation failed: {e}") from e
