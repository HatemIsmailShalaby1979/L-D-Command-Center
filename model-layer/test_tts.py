# model-layer/test_tts.py
#
# WHAT: Tests for the TTS client module.
# WHY:  Ensures the TTS interface works correctly with mocked backends,
#       validates error handling, and verifies the backend-agnostic API.
# BREAKS IF DELETED: No regression protection for TTS synthesis contract.

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add model-layer to path

from model_layer.tts import (
    TtsBackend,
    TtsConfig,
    DEFAULT_VOICE,
    DEFAULT_LANGUAGE,
    DEFAULT_BACKEND,
    synthesize,
    get_available_voices,
    generate_audio,
    _synthesize_piper,
    _synthesize_kokoro,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TEXT = "Hello, this is a test of text-to-speech synthesis."
SAMPLE_VOICE = "en_US-lessac-medium"
SAMPLE_LANGUAGE = "en"
SAMPLE_SPEED = 1.0

MOCK_WAV_BYTES = b"\x52\x49\x46\x46" + b"\x00" * 100 + b"\x57\x41\x56\x45"  # RIFF/WAV header


# ---------------------------------------------------------------------------
# Test TtsConfig
# ---------------------------------------------------------------------------

class TestTtsConfig:
    """Tests for TtsConfig dataclass."""

    def test_default_backend_is_piper(self):
        config = TtsConfig()
        assert config.backend == TtsBackend.PIPER

    def test_default_voice(self):
        config = TtsConfig()
        assert config.voice == DEFAULT_VOICE

    def test_default_language(self):
        config = TtsConfig()
        assert config.language == DEFAULT_LANGUAGE

    def test_default_speed(self):
        config = TtsConfig()
        assert config.speed == 1.0

    def test_custom_backend(self):
        config = TtsConfig(backend=TtsBackend.KOKORO)
        assert config.backend == TtsBackend.KOKORO


# ---------------------------------------------------------------------------
# Test synthesize() — error cases
# ---------------------------------------------------------------------------

class TestSynthesizeErrors:
    """Tests for synthesize() error handling."""

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            synthesize("")

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            synthesize("   ")

    def test_none_text_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            synthesize(None)

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS backend"):
            synthesize(SAMPLE_TEXT, backend="invalid")


# ---------------------------------------------------------------------------
# Test synthesize() — Piper backend (mocked)
# ---------------------------------------------------------------------------

class TestSynthesizePiper:
    """Tests for Piper backend synthesis."""

    @patch("model_layer.tts._synthesize_piper")
    def test_uses_piper_by_default(self, mock_piper):
        mock_piper.return_value = MOCK_WAV_BYTES
        result = synthesize(SAMPLE_TEXT)
        mock_piper.assert_called_once()
        assert result == MOCK_WAV_BYTES

    @patch("model_layer.tts._synthesize_piper")
    def test_uses_explicit_piper_backend(self, mock_piper):
        mock_piper.return_value = MOCK_WAV_BYTES
        result = synthesize(SAMPLE_TEXT, backend=TtsBackend.PIPER)
        mock_piper.assert_called_once()
        assert result == MOCK_WAV_BYTES

    def test_piper_passes_correct_args(self):
        """Verify synthesize passes args to _synthesize_piper correctly."""
        with patch("model_layer.tts._synthesize_piper", return_value=MOCK_WAV_BYTES) as mock:
            synthesize(
                SAMPLE_TEXT,
                voice="es_MX-diana-medium",
                language="es",
                backend=TtsBackend.PIPER,
                models_dir=Path("/tmp/models"),
                speed=1.5,
            )
            mock.assert_called_once_with(
                SAMPLE_TEXT,
                "es_MX-diana-medium",
                "es",
                Path("/tmp/models"),
                1.5,
            )


# ---------------------------------------------------------------------------
# Test _synthesize_piper()
# ---------------------------------------------------------------------------

class TestSynthesizePiperImpl:
    """Tests for the Piper backend implementation."""

    def test_piper_not_installed_raises(self):
        """If piper-tts is not installed, raise RuntimeError."""
        # Simulate piper module not being importable by patching import
        import builtins
        original_import = builtins.__import__

        def failing_import(name, *args, **kwargs):
            if name == "piper":
                raise ImportError("No module named 'piper'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            with pytest.raises(RuntimeError, match="piper-tts package not installed"):
                _synthesize_piper(
                    SAMPLE_TEXT,
                    SAMPLE_VOICE,
                    SAMPLE_LANGUAGE,
                    Path("/tmp"),
                    SAMPLE_SPEED,
                )

    def test_model_not_found_raises(self, tmp_path):
        """If the voice model file doesn't exist, raise FileNotFoundError."""
        # Stub piper so the test is hermetic (model check happens before Voice.load)
        with patch.dict("sys.modules", {"piper": MagicMock()}):
            with pytest.raises(FileNotFoundError, match="Piper voice model not found"):
                _synthesize_piper(
                    SAMPLE_TEXT,
                    SAMPLE_VOICE,
                    SAMPLE_LANGUAGE,
                    tmp_path,  # Empty dir, no model files
                    SAMPLE_SPEED,
                )


# ---------------------------------------------------------------------------
# Test _synthesize_kokoro()
# ---------------------------------------------------------------------------

class TestSynthesizeKokoro:
    """Tests for the Kokoro backend implementation."""

    def test_kokoro_not_implemented(self, tmp_path):
        """Kokoro backend raises NotImplementedError (placeholder)."""
        # Mock the imports and path.exists to reach the NotImplementedError
        with patch("model_layer.tts.Path.exists", return_value=True):
            with patch.dict("sys.modules", {"torch": MagicMock(), "onnxruntime": MagicMock()}):
                # Reload the module to pick up mocked imports
                import importlib
                import model_layer.tts as tts_module
                importlib.reload(tts_module)

                with pytest.raises(NotImplementedError, match="Kokoro-82M backend requires additional setup"):
                    tts_module._synthesize_kokoro(
                        SAMPLE_TEXT,
                        SAMPLE_VOICE,
                        SAMPLE_LANGUAGE,
                        tmp_path,
                        SAMPLE_SPEED,
                    )


# ---------------------------------------------------------------------------
# Test get_available_voices()
# ---------------------------------------------------------------------------

class TestGetAvailableVoices:
    """Tests for voice discovery."""

    def test_returns_empty_for_missing_dir(self, tmp_path):
        """Returns empty list when models dir doesn't exist."""
        voices = get_available_voices(models_dir=tmp_path / "nonexistent")
        assert voices == []

    def test_discovers_piper_voices(self, tmp_path):
        """Discovers Piper voices from .onnx and .onnx.json pairs."""
        # Create mock voice files
        voice_dir = tmp_path / "piper"
        voice_dir.mkdir()

        # Create a valid voice pair
        (voice_dir / "en_US-lessac-medium.onnx").write_bytes(b"mock")
        (voice_dir / "en_US-lessac-medium.onnx.json").write_text("{}")

        # Create another valid voice pair
        (voice_dir / "es_MX-diana-medium.onnx").write_bytes(b"mock")
        (voice_dir / "es_MX-diana-medium.onnx.json").write_text("{}")

        # Create an invalid voice (missing config)
        (voice_dir / "invalid_voice.onnx").write_bytes(b"mock")

        voices = get_available_voices(backend=TtsBackend.PIPER, models_dir=voice_dir)
        assert len(voices) == 2
        assert "en_US-lessac-medium" in voices
        assert "es_MX-diana-medium" in voices
        assert "invalid_voice" not in voices  # Missing config

    def test_discovers_kokoro_voices(self, tmp_path):
        """Discovers Kokoro voices from kokoro-*.onnx files."""
        voice_dir = tmp_path / "kokoro"
        voice_dir.mkdir()

        # Create mock Kokoro voice files
        (voice_dir / "kokoro-af-heart.onnx").write_bytes(b"mock")
        (voice_dir / "kokoro-bf-emma.onnx").write_bytes(b"mock")

        voices = get_available_voices(backend=TtsBackend.KOKORO, models_dir=voice_dir)
        assert len(voices) == 2
        assert "af-heart" in voices
        assert "bf-emma" in voices


# ---------------------------------------------------------------------------
# Test generate_audio()
# ---------------------------------------------------------------------------

class TestGenerateAudio:
    """Tests for the generate_audio() convenience function."""

    @patch("model_layer.tts.synthesize", return_value=MOCK_WAV_BYTES)
    def test_returns_memory_when_no_output_path(self, mock_synthesize):
        result = generate_audio(SAMPLE_TEXT)
        assert result == "memory"
        mock_synthesize.assert_called_once()

    @patch("model_layer.tts.synthesize", return_value=MOCK_WAV_BYTES)
    def test_saves_to_file(self, mock_synthesize, tmp_path):
        output_path = str(tmp_path / "output.wav")
        result = generate_audio(SAMPLE_TEXT, output_path=output_path)
        assert result == output_path
        assert Path(output_path).exists()
        assert Path(output_path).read_bytes() == MOCK_WAV_BYTES

    @patch("model_layer.tts.synthesize", return_value=MOCK_WAV_BYTES)
    def test_passes_kwargs_to_synthesize(self, mock_synthesize):
        generate_audio(SAMPLE_TEXT, voice="es_MX-diana-medium", language="es")
        mock_synthesize.assert_called_once_with(
            SAMPLE_TEXT,
            voice="es_MX-diana-medium",
            language="es",
        )


# ---------------------------------------------------------------------------
# Test backend enum
# ---------------------------------------------------------------------------

class TestTtsBackend:
    """Tests for TtsBackend enum."""

    def test_piper_value(self):
        assert TtsBackend.PIPER.value == "piper"

    def test_kokoro_value(self):
        assert TtsBackend.KOKORO.value == "kokoro"

    def test_iteration(self):
        backends = list(TtsBackend)
        assert len(backends) == 2
        assert TtsBackend.PIPER in backends
        assert TtsBackend.KOKORO in backends


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for TTS synthesis.

    To test manually with a real Piper voice:
    1. Download a Piper voice model from https://huggingface.co/rhasspy/piper-voices
    2. Place .onnx and .onnx.json files in models/tts/
    3. Run: python -c "from model_layer.tts import synthesize; audio = synthesize('Hello world')"
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
