# engines/audio-engine/provisioning.py
#
# WHAT: Offline voice provisioning — maps catalog voice ids to their
#       Piper download URLs, reports which voices are missing locally,
#       and fetches them into the TTS models directory.
# WHY:  The product is offline-first (MASTER_STORY), but a fresh machine
#       has zero voice files, and synthesis failures were previously just
#       a FileNotFoundError with a bare URL. P2.5 turns provisioning into
#       an inspectable, scriptable step: one call tells the user exactly
#       what to fetch, and one call fetches it while online.
# BREAKS IF DELETED: Fresh-machine setup loses its checklist/downloader;
#       missing-voice errors stay generic.

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engines.audio_engine import voice_catalog
from model_layer.tts import get_available_voices

logger = logging.getLogger(__name__)

# rhasspy/piper-voices layout: {lang}/{lang}_{COUNTRY}/{speaker}/{quality}/{name}.onnx
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


@dataclass
class VoiceDownload:
    """One downloadable voice plus its sidecar config file."""
    voice_id: str
    model_url: str
    config_url: str
    installed: bool


def parse_voice_id(voice_id: str) -> tuple[str, str, str, str]:
    """'es_ES-carlos-medium' -> ('es', 'ES', 'carlos', 'medium').

    Piper ids are inconsistent about the speaker/quality separator
    ('carlos-medium' vs 'ken_medium' in ja_JP-ken_medium), so try '_'
    first and fall back to '-'."""
    lang_country, rest = voice_id.split("-", 1)
    lang, country = lang_country.split("_", 1)
    if "_" in rest:
        speaker, quality = rest.rsplit("_", 1)
    else:
        speaker, quality = rest.rsplit("-", 1)
    return lang.lower(), country.upper(), speaker, quality


def voice_urls(voice_id: str) -> tuple[str, str]:
    """HF download URLs for the .onnx model and its .onnx.json config."""
    lang, country, speaker, quality = parse_voice_id(voice_id)
    base = f"{_HF_BASE}/{lang}/{lang}_{country}/{speaker}/{quality}/{voice_id}"
    return f"{base}.onnx", f"{base}.onnx.json"


def _installed_voices(models_dir: Optional[Path]) -> set[str]:
    from model_layer.tts import DEFAULT_BACKEND
    return set(get_available_voices(backend=DEFAULT_BACKEND, models_dir=models_dir))


def missing_voices(models_dir: Optional[Path] = None) -> list[VoiceDownload]:
    """
    Provisioning report: every catalog language voice not yet on disk,
    with ready-to-use URLs. Empty result == machine is provisioned for
    everything the Voice Catalog can produce.
    """
    installed = _installed_voices(models_dir)
    report = []
    for lang, voice_id in sorted(voice_catalog.PIPER_LANGUAGE_VOICES.items()):
        if voice_id in installed:
            continue
        model_url, config_url = voice_urls(voice_id)
        report.append(VoiceDownload(
            voice_id=voice_id,
            model_url=model_url,
            config_url=config_url,
            installed=False,
        ))
    return report


def download_voice(voice_id: str, models_dir: Path) -> Path:
    """
    Fetch one voice (model + config) into models_dir. Requires network;
    once downloaded, all synthesis runs fully offline.
    """
    models_dir.mkdir(parents=True, exist_ok=True)
    model_url, config_url = voice_urls(voice_id)

    for url, suffix in ((model_url, ".onnx"), (config_url, ".onnx.json")):
        dest = models_dir / f"{voice_id}{suffix}"
        if dest.exists():
            logger.info("Already present: %s", dest.name)
            continue
        logger.info("Downloading %s", url)
        with urllib.request.urlopen(url) as resp, dest.open("wb") as fh:
            fh.write(resp.read())
    return models_dir / f"{voice_id}.onnx"
