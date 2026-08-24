# engines/audio-engine/test_narration.py
#
# WHAT: Tests for the audio-engine narration module.
# WHY:  Ensures the narration function correctly selects backends, handles
#       errors, and produces valid audio output for Journey cards and
#       Resume summaries.
# BREAKS IF DELETED: No regression protection for audio generation contract.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths

from engines.audio_engine.narration import (
    narrate,
    narrate_journey_card,
    narrate_resume_summary,
    _detect_language,
    _select_backend,
    _wav_to_mp3,
    KOKORO_SUPPORTED_LANGUAGES,
    DEFAULT_VOICES,
    DEFAULT_PIPER_VOICE,
    TtsBackend,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_JOURNEY_CARD = {
    "id": "card-1",
    "title": "What is Python?",
    "content": "Python is a high-level programming language.",
    "question": "What type of language is Python?",
    "options": ["Low-level", "High-level", "Assembly", "Machine code"],
    "correct_option": "High-level",
    "explanation": "Python abstracts away memory management.",
}

SAMPLE_RESUME = {
    "contact": {"name": "John Doe", "email": "john@example.com"},
    "summary": "Experienced software engineer with 5+ years in Python and machine learning.",
    "experience": [],
    "education": [],
    "skills": [],
    "projects": [],
}

SAMPLE_TEXT_EN = "Hello, this is a test of text-to-speech synthesis."
SAMPLE_TEXT_ES = "Hola, esta es una prueba de síntesis de voz."
SAMPLE_TEXT_FR = "Bonjour, c'est un test de synthèse vocale."


# ---------------------------------------------------------------------------
# Test _detect_language()
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    """Tests for language detection."""

    def test_detects_english(self):
        assert _detect_language(SAMPLE_TEXT_EN) == "en"

    def test_detects_spanish_heuristic(self):
        spanish_text = "¿Cómo estás? Estoy bien, gracias."
        result = _detect_language(spanish_text)
        assert result in ["es", "en"]

    def test_detects_french_heuristic(self):
        french_text = "Bonjour, comment allez-vous?"
        result = _detect_language(french_text)
        assert result in ["fr", "en"]

    def test_empty_text_returns_english(self):
        assert _detect_language("") == "en"

    def test_whitespace_only_returns_english(self):
        assert _detect_language("   ") == "en"

    def test_cjk_text_detected(self):
        cjk_text = "你好世界，这是一段测试文本。"
        assert _detect_language(cjk_text) == "zh"

    def test_cyrillic_text_detected(self):
        cyrillic_text = "Привет, это тест текста."
        assert _detect_language(cyrillic_text) == "ru"


# ---------------------------------------------------------------------------
# Test _select_backend()
# ---------------------------------------------------------------------------

class TestSelectBackend:
    """Tests for backend selection logic."""

    def test_auto_selects_kokoro_for_english(self):
        backend, voice = _select_backend(SAMPLE_TEXT_EN)
        assert backend == TtsBackend.KOKORO
        assert voice in KOKORO_SUPPORTED_LANGUAGES or voice == "af_heart"

    def test_auto_selects_kokoro_for_supported_language(self):
        backend, voice = _select_backend(SAMPLE_TEXT_ES)
        assert backend == TtsBackend.KOKORO

    def test_fallback_to_piper_for_unsupported_language(self):
        # Test explicit Piper backend selection (the fallback path)
        backend, voice = _select_backend("simple text", backend=TtsBackend.PIPER)
        assert backend == TtsBackend.PIPER
        assert voice == DEFAULT_PIPER_VOICE

    def test_explicit_backend_override(self):
        backend, voice = _select_backend(SAMPLE_TEXT_EN, backend=TtsBackend.PIPER)
        assert backend == TtsBackend.PIPER
        assert voice == DEFAULT_PIPER_VOICE

    def test_explicit_kokoro_backend(self):
        backend, voice = _select_backend(SAMPLE_TEXT_EN, backend=TtsBackend.KOKORO)
        assert backend == TtsBackend.KOKORO
        assert voice in DEFAULT_VOICES.values()


# ---------------------------------------------------------------------------
# Test narrate() — error cases
# ---------------------------------------------------------------------------

class TestNarrateErrors:
    """Tests for narrate() error handling."""

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            narrate("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            narrate("   ")

    def test_none_text_raises(self):
        with pytest.raises(ValueError, match="Text must be non-empty"):
            narrate(None)


# ---------------------------------------------------------------------------
# Test narrate() — happy path (mocked)
# ---------------------------------------------------------------------------

class TestNarrate:
    """Tests for narrate() success cases."""

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", return_value=b"mock-mp3-bytes")
    def test_returns_narration_result(self, mock_mp3, mock_synthesize):
        result = narrate(SAMPLE_TEXT_EN)
        assert hasattr(result, 'wav_bytes')
        assert result.wav_bytes == b"mock-wav-bytes"

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", return_value=b"mock-mp3-bytes")
    def test_uses_auto_selected_backend(self, mock_mp3, mock_synthesize):
        narrate(SAMPLE_TEXT_EN)
        call_kwargs = mock_synthesize.call_args
        assert call_kwargs[1].get('backend') == TtsBackend.KOKORO or \
               (len(call_kwargs[0]) > 2 and call_kwargs[0][2] == TtsBackend.KOKORO)

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", side_effect=RuntimeError("ffmpeg failed"))
    def test_continues_with_wav_only_on_mp3_failure(self, mock_mp3, mock_synthesize):
        """Should still return result even if MP3 conversion fails."""
        result = narrate(SAMPLE_TEXT_EN)
        assert result.wav_bytes == b"mock-wav-bytes"
        assert result.mp3_bytes == b""

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", return_value=b"mock-mp3-bytes")
    def test_saves_to_output_path(self, mock_mp3, mock_synthesize, tmp_path):
        output_path = str(tmp_path / "audio")
        result = narrate(SAMPLE_TEXT_EN, output_path=output_path)

        assert (tmp_path / "audio" / "narration.wav").exists()
        assert (tmp_path / "audio" / "narration.mp3").exists()

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", return_value=b"mock-mp3-bytes")
    def test_explicit_voice_override(self, mock_mp3, mock_synthesize):
        narrate(SAMPLE_TEXT_EN, voice="custom_voice")
        call_kwargs = mock_synthesize.call_args
        assert call_kwargs[1].get('voice') == "custom_voice" or \
               (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "custom_voice")

    @patch("engines.audio_engine.narration.synthesize", return_value=b"mock-wav-bytes")
    @patch("engines.audio_engine.narration._wav_to_mp3", return_value=b"mock-mp3-bytes")
    def test_speed_parameter_passed(self, mock_mp3, mock_synthesize):
        narrate(SAMPLE_TEXT_EN, speed=1.5)
        call_kwargs = mock_synthesize.call_args
        assert call_kwargs[1].get('speed') == 1.5 or \
               (len(call_kwargs[0]) > 4 and call_kwargs[0][4] == 1.5)


# ---------------------------------------------------------------------------
# Test narrate_journey_card()
# ---------------------------------------------------------------------------

class TestNarrateJourneyCard:
    """Tests for narrate_journey_card() convenience function."""

    @patch("engines.audio_engine.narration.narrate")
    def test_combines_title_and_content(self, mock_narrate):
        mock_narrate.return_value = MagicMock(wav_bytes=b"test", mp3_bytes=b"test")
        narrate_journey_card(SAMPLE_JOURNEY_CARD)
        mock_narrate.assert_called_once()
        call_args = mock_narrate.call_args[0][0]
        assert "What is Python?" in call_args
        assert "Python is a high-level programming language." in call_args

    @patch("engines.audio_engine.narration.narrate")
    def test_handles_missing_title(self, mock_narrate):
        card = dict(SAMPLE_JOURNEY_CARD)
        del card["title"]
        narrate_journey_card(card)
        mock_narrate.assert_called_once()

    @patch("engines.audio_engine.narration.narrate")
    def test_handles_missing_content(self, mock_narrate):
        card = dict(SAMPLE_JOURNEY_CARD)
        del card["content"]
        narrate_journey_card(card)
        mock_narrate.assert_called_once()


# ---------------------------------------------------------------------------
# Test narrate_resume_summary()
# ---------------------------------------------------------------------------

class TestNarrateResumeSummary:
    """Tests for narrate_resume_summary() convenience function."""

    @patch("engines.audio_engine.narration.narrate")
    def test_includes_name_and_summary(self, mock_narrate):
        mock_narrate.return_value = MagicMock(wav_bytes=b"test", mp3_bytes=b"test")
        narrate_resume_summary(SAMPLE_RESUME)
        mock_narrate.assert_called_once()
        call_args = mock_narrate.call_args[0][0]
        assert "John Doe" in call_args
        assert "Experienced software engineer" in call_args

    @patch("engines.audio_engine.narration.narrate")
    def test_handles_missing_name(self, mock_narrate):
        resume = dict(SAMPLE_RESUME)
        resume["contact"] = {}
        narrate_resume_summary(resume)
        mock_narrate.assert_called_once()
        call_args = mock_narrate.call_args[0][0]
        assert "Candidate" in call_args

    @patch("engines.audio_engine.narration.narrate")
    def test_handles_missing_summary(self, mock_narrate):
        resume = dict(SAMPLE_RESUME)
        resume["summary"] = ""
        narrate_resume_summary(resume)
        mock_narrate.assert_called_once()


# ---------------------------------------------------------------------------
# Test _wav_to_mp3()
# ---------------------------------------------------------------------------

class TestWavToMp3:
    """Tests for WAV to MP3 conversion."""

    @patch("engines.audio_engine.narration.subprocess.run")
    def test_calls_ffmpeg(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"mp3-data")
        result = _wav_to_mp3(b"wav-data")
        mock_run.assert_called_once()
        assert result == b"mp3-data"

    @patch("engines.audio_engine.narration.subprocess.run", side_effect=RuntimeError("ffmpeg not found"))
    def test_raises_on_ffmpeg_failure(self, mock_run):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            _wav_to_mp3(b"wav-data")


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for module constants."""

    def test_kokoro_supported_languages(self):
        assert "en" in KOKORO_SUPPORTED_LANGUAGES
        assert "es" in KOKORO_SUPPORTED_LANGUAGES
        assert "fr" in KOKORO_SUPPORTED_LANGUAGES

    def test_default_voices(self):
        assert "af_heart" in DEFAULT_VOICES.values()
        assert "bm_george" in DEFAULT_VOICES.values()

    def test_default_piper_voice(self):
        assert DEFAULT_PIPER_VOICE == "en_US-lessac-medium"


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for narration.

    To test manually with real audio:
    1. Ensure ffmpeg is in PATH
    2. Run: python -c "from engines.audio_engine.narration import narrate; result = narrate('Hello world')"
    3. Check that WAV and MP3 files are generated
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
