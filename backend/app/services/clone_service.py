"""
clone_service.py — Voice cloning using Chatterbox TTS.

Uses the chatterbox-tts Python library for zero-shot voice cloning
from a reference audio sample. Runs on CPU.

Correct API (chatterbox-tts >= 0.1.7):
    from chatterbox import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained('cpu')
    wav_tensor = model.generate(text, audio_prompt_path=ref_audio)
    # wav_tensor is a torch.Tensor; model.sr holds the sample rate
"""

from pathlib import Path
from app.core.logging import logger
from app.core.config import settings


class CloneService:
    """Chatterbox TTS wrapper for zero-shot voice cloning on CPU."""

    def __init__(self):
        # Model is loaded lazily on first clone call to keep memory low
        # when voice cloning is not in use.
        pass

    def clone(
        self,
        text: str,
        reference_audio_path: Path,
        output_path: Path,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5
    ) -> Path:
        """
        Clone a voice from a reference audio file and generate speech.

        Args:
            text (str): Input text to synthesize (max 500 chars).
            reference_audio_path (Path): Path to the reference audio WAV/MP3/OGG/FLAC/M4A/AAC.
            output_path (Path): Where to save the output WAV file.
            language (str): Language code (default 'en'). Note: ChatterboxTTS is
                            primarily English-optimised.
            exaggeration (float): Expressiveness exaggeration (0.0 to 1.0)
            cfg_weight (float): Expressiveness cfg_weight (0.0 to 1.0)

        Returns:
            Path: Path to the generated WAV file.

        Raises:
            FileNotFoundError: If the reference audio file does not exist.
            RuntimeError: If Chatterbox fails or is not installed.
        """
        # Hard cap to prevent CPU timeouts
        if len(text) > settings.VOICE_TEXT_MAX_CHARS:
            logger.warning(
                f"Cloning text truncated from {len(text)} to "
                f"{settings.VOICE_TEXT_MAX_CHARS} characters."
            )
            text = text[:settings.VOICE_TEXT_MAX_CHARS]

        if not reference_audio_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {reference_audio_path}")

        logger.info(
            f"Cloning voice. Text len: {len(text)}, "
            f"Reference: {reference_audio_path.name}, Lang: {language}, "
            f"exaggeration: {exaggeration}, cfg_weight: {cfg_weight}"
        )

        try:
            # Lazy import so the dependency is optional and only fails when
            # cloning is actually requested.
            from chatterbox import ChatterboxTTS
            import soundfile as sf
        except ImportError as e:
            raise RuntimeError(
                "Voice cloning requires chatterbox-tts and soundfile. "
                "Run: pip install chatterbox-tts soundfile"
            ) from e

        try:
            logger.info("Loading ChatterboxTTS model on CPU (first run downloads weights)...")
            model = ChatterboxTTS.from_pretrained('cpu')

            logger.info("Running Chatterbox inference (this may take 1–2 minutes on CPU)...")

            # generate() accepts audio_prompt_path for zero-shot voice cloning.
            # It returns a torch.Tensor of shape (1, samples); model.sr is the
            # sample rate.
            wav_tensor = model.generate(
                text,
                audio_prompt_path=str(reference_audio_path),
                exaggeration=exaggeration,
                cfg_weight=cfg_weight
            )

            # Convert tensor → numpy array
            audio_array = wav_tensor.squeeze(0).detach().cpu().numpy()
            sample_rate = model.sr

            # Save the output WAV
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_path), audio_array, samplerate=sample_rate)

            logger.info(f"Cloned audio saved to: {output_path} (sr={sample_rate})")
            return output_path

        except Exception as e:
            logger.error(f"Voice cloning failed: {e}", exc_info=True)
            raise RuntimeError(f"Voice cloning failed: {e}") from e
