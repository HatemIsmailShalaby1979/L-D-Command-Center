# engines/audio-engine/test_provisioning.py
#
# WHAT: Tests for offline voice provisioning — URL construction from
#       catalog voice ids, missing-voice reporting, and download wiring.
# WHY:  P2.5 — fresh machines must get an exact, testable fetch list
#       instead of a generic FileNotFoundError; the URL scheme is the
#       part most worth pinning.
# BREAKS IF DELETED: The provisioning contract (URLs/report shape) is
#       unprotected; silent drift breaks fresh-machine setup.

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engines.audio_engine import provisioning as prov
from engines.audio_engine.voice_catalog import PIPER_LANGUAGE_VOICES


class TestParseVoiceId:
    def test_standard_voice_id(self):
        assert prov.parse_voice_id("es_ES-carlos-medium") == ("es", "ES", "carlos", "medium")

    def test_american_english(self):
        assert prov.parse_voice_id("en_US-lessac-medium") == ("en", "US", "lessac", "medium")


class TestVoiceUrls:
    def test_urls_follow_hf_layout(self):
        model, config = prov.voice_urls("es_ES-carlos-medium")
        assert model == ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                         "es/es_ES/carlos/medium/es_ES-carlos-medium.onnx")
        assert config.endswith(".onnx.json")

    def test_every_catalog_voice_yields_urls(self):
        for voice_id in PIPER_LANGUAGE_VOICES.values():
            model, config = prov.voice_urls(voice_id)
            assert model.startswith("https://huggingface.co/")
            assert config == model + ".json"


class TestMissingVoices:
    def test_all_missing_on_empty_dir(self, tmp_path):
        report = prov.missing_voices(models_dir=tmp_path)
        assert {item.voice_id for item in report} == set(PIPER_LANGUAGE_VOICES.values())
        assert all(item.installed is False for item in report)

    def test_installed_voice_excluded(self, tmp_path):
        voice = PIPER_LANGUAGE_VOICES["en"]
        (tmp_path / f"{voice}.onnx").write_bytes(b"x")
        (tmp_path / f"{voice}.onnx.json").write_text("{}")
        report = prov.missing_voices(models_dir=tmp_path)
        assert all(item.voice_id != voice for item in report)


class TestDownloadVoice:
    @staticmethod
    def _urlopen_mock():
        resp = MagicMock()
        resp.__enter__.return_value.read.return_value = b"data"
        return resp

    def test_downloads_model_and_config(self, tmp_path):
        with patch.object(prov.urllib.request, "urlopen",
                          return_value=self._urlopen_mock()) as mock_open:
            result = prov.download_voice("es_ES-carlos-medium", tmp_path)
        assert result == tmp_path / "es_ES-carlos-medium.onnx"
        assert (tmp_path / "es_ES-carlos-medium.onnx").read_bytes() == b"data"
        assert (tmp_path / "es_ES-carlos-medium.onnx.json").read_bytes() == b"data"
        assert mock_open.call_count == 2

    def test_skips_existing_files(self, tmp_path):
        existing = tmp_path / "es_ES-carlos-medium.onnx"
        existing.write_bytes(b"original")
        with patch.object(prov.urllib.request, "urlopen",
                          return_value=self._urlopen_mock()) as mock_open:
            prov.download_voice("es_ES-carlos-medium", tmp_path)
        assert existing.read_bytes() == b"original"
        assert mock_open.call_count == 1  # only the sidecar config

    def test_ja_style_voice_id_parses(self):
        model, _ = prov.voice_urls("ja_JP-ken_medium")
        assert "ja/ja_JP/ken/medium/ja_JP-ken_medium.onnx" in model
