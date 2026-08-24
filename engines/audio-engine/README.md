# Audio Engine

The audio-engine generates audio content from text — audiobooks and podcasts in WAV or MP3 format — using text-to-speech orchestration. It takes written material (such as journey content, podcast scripts, or language lessons) and converts it into spoken audio, enabling offline listening and multi-format consumption. If this engine is deleted, all audio output (audiobooks, podcasts, spoken lessons) is lost; text-based outputs remain unaffected.

## Module map

- `voice_catalog.py` — the one (language, role) → voice table; all consumers resolve voices here.
- `assembly.py` — the public seam: `render_segments(segments) -> AudioResult` owns synthesis, silence, WAV concat, and MP3 conversion.
- `narration.py` — plain text → single-voice audio (Narration), auto-selecting backends via `KOKORO_IMPLEMENTED`.
- `podcast_audio.py` — PodcastScript → multi-voice audio; speaker→voice mapping via the catalog.
- `provisioning.py` — offline voice setup (see below).
- `podcast_script.py` — PodcastScript generation via the Generation Pipeline.

## Offline voice provisioning (P2.5)

A fresh machine has no Piper voices. While online, fetch everything the
catalog can produce:

```python
from pathlib import Path
from engines.audio_engine import provisioning

report = provisioning.missing_voices(models_dir=Path("models/tts"))
for item in report:
    print("missing:", item.voice_id, "->", item.model_url)
    provisioning.download_voice(item.voice_id, models_dir=Path("models/tts"))
```

Once downloaded, all narration/podcast/language-lab rendering runs fully
offline. An empty `missing_voices()` report means the machine is
provisioned for every language in the Voice Catalog.
