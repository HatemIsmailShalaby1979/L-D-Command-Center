# desktop-shell/controller.py
#
# WHAT: The shell controller — every engine interaction the desktop UI
#       needs, behind one testable object with typed results.
# WHY:  P5.2/P5.3 of docs/PRODUCTION_PLAN.md. Tkinter cannot run headless,
#       so ALL logic lives here and the UI layer (app.py) stays thin:
#       call controller, map FlowResult.error_kind to a dialog. Typed
#       errors surface as kinds, never as tracebacks (E6).
# BREAKS IF DELETED: The UI has no way to reach engines; error taxonomy
#       would be hand-rolled in widget callbacks.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engines.playground_bridge.import_inbox import unique_artifact_name
from model_layer.client import ApiError, ConnectionError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL
from model_layer.schema import SchemaValidationError
from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)

_EXT_FOR_KIND = {"image": ".png", "audio": ".wav", "video": ".mp4",
                 "design": ".png"}


@dataclass
class FlowResult:
    """Typed envelope between controller and UI. ok=False carries kind."""
    ok: bool
    payload: Any = None
    error_kind: Optional[str] = None   # "no_model" | "bad_output" | "input" | "unexpected"
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _flow(fn):
    """Decorator: run a flow, collapse every failure into FlowResult."""
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except ConnectionError as exc:
            logger.warning("LM Studio unreachable: %s", exc)
            return FlowResult(False, error_kind="no_model",
                              detail="LM Studio is not reachable at localhost:1234 — start it and load a model.")
        except ApiError as exc:
            logger.warning("Model API error: %s", exc)
            return FlowResult(False, error_kind="no_model", detail=str(exc))
        except SchemaValidationError as exc:
            logger.warning("Model output rejected after retries: %s", exc)
            return FlowResult(False, error_kind="bad_output",
                              detail="The model kept producing invalid content — try rephrasing or lowering card count.")
        except (ValueError,) as exc:
            return FlowResult(False, error_kind="input", detail=str(exc))
        except Exception as exc:  # noqa: BLE001 — the shell's last line of defense
            logger.exception("Unexpected shell failure")
            return FlowResult(False, error_kind="unexpected", detail=str(exc))
    return wrapper


class ShellController:
    """
    Contract: the entire engine surface the desktop UI is allowed to touch.
    Every public method returns a FlowResult; nothing raises past this seam.
    """

    def __init__(
        self,
        *,
        client: Optional[LmStudioClient] = None,
        storage: Optional[Storage] = None,
        model: str = DEFAULT_MODEL,
        connectors: Optional[list] = None,
        inbox_path: Optional[str] = None,
    ) -> None:
        self.client = client if client is not None else LmStudioClient()
        self.storage = storage if storage is not None else default_storage()
        self.model = model
        self._extra_connectors = list(connectors or [])
        self._hub = None
        self.inbox_path = inbox_path  # None -> <storage root>/inbox

    # -- health -----------------------------------------------------------

    @_flow
    def check_model_health(self) -> FlowResult:
        if self.client.is_available():
            return FlowResult(True, payload="ready")
        return FlowResult(False, error_kind="no_model",
                          detail="LM Studio is not responding on localhost:1234.")

    # -- capabilities -------------------------------------------------------

    @_flow
    def run_capability_probe(self) -> FlowResult:
        from model_layer.capabilities import probe_model_capabilities
        doc = probe_model_capabilities(self.client, storage=self.storage)
        logger.info("Capability probe: %s", doc.get("overall"))
        return FlowResult(True, payload=doc)

    @_flow
    def capability_summary(self) -> FlowResult:
        """Offline read of the last stored verdict; payload is a
        one-line health-bar string or None when never probed."""
        from model_layer.capabilities import latest_verdict, summarize_verdict
        doc = latest_verdict(self.storage)
        if doc is None:
            return FlowResult(True, payload=None)
        return FlowResult(True, payload=summarize_verdict(doc))

    # -- audio studio -------------------------------------------------------

    def _slug(self, text: str, fallback: str) -> str:
        return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:40] or fallback

    @_flow
    def generate_audiobook(self, text: str, language: str = "en",
                           speed: float = 1.0) -> FlowResult:
        """Narration engine -> WAV+MP3 saved under exports."""
        from engines.audio_engine import voice_catalog
        from engines.audio_engine.narration import narrate

        text = (text or "").strip()
        if not text:
            raise ValueError("Text must be non-empty")
        result = narrate(
            text, voice=voice_catalog.narrator_voice(language),
            include_mp3=True, speed=float(speed))
        existing = set(self.storage.list_artifacts("exports"))
        base = unique_artifact_name(existing, f"{self._slug(text, 'audiobook')}.wav")
        base = base[:-4]  # strip .wav; we add per-format suffixes
        wav_path = self.storage.save_artifact("exports", f"{base}.wav",
                                              result.wav_bytes)
        payload: dict[str, Any] = {
            "wav": str(wav_path),
            "mp3": None,
            "duration_seconds": round(len(result.wav_bytes) / 2
                                      / max(result.sample_rate, 1), 1),
            "voice": result.voice_used,
        }
        if result.mp3_bytes:
            payload["mp3"] = str(self.storage.save_artifact(
                "exports", f"{base}.mp3", result.mp3_bytes))
        logger.info("Audiobook generated (%s): %.1fs",
                    payload["voice"], payload["duration_seconds"])
        return FlowResult(True, payload=payload)

    @_flow
    def generate_podcast(self, topic: str, language: str = "en",
                         level: str = "beginner", num_segments: int = 6,
                         duration_minutes: int = 5,
                         host_name: str = "Alex") -> FlowResult:
        """Script generation (Guardrail Loop) + two-voice render -> WAV/MP3."""
        from engines.audio_engine import voice_catalog
        from engines.audio_engine.podcast_audio import (
            render_podcast_to_audio,
        )
        from engines.audio_engine.podcast_script import (
            generate_script_from_topic,
        )

        topic = (topic or "").strip()
        if not topic:
            raise ValueError("Topic must be non-empty")
        script = generate_script_from_topic(
            topic,
            num_segments=int(num_segments),
            duration_minutes=int(duration_minutes),
            host_name=(host_name or "Alex").strip() or "Alex",
            language=voice_catalog.language_name(language),
            level=level,
            client=self.client, model=self.model,
        )
        audio = render_podcast_to_audio(script, include_mp3=True)
        existing = set(self.storage.list_artifacts("exports"))
        base = unique_artifact_name(existing,
                                    f"podcast-{self._slug(topic, 'episode')}.wav")
        base = base[:-4]
        self.storage.save_artifact("podcast_scripts", f"{base}.json",
                                   script.to_dict())
        wav_path = self.storage.save_artifact("exports", f"{base}.wav",
                                              audio.wav_bytes)
        payload: dict[str, Any] = {
            "wav": str(wav_path),
            "mp3": None,
            "segments": len(script.segments),
            "duration_seconds": audio.duration_seconds,
            "title": script.title,
        }
        if audio.mp3_bytes:
            payload["mp3"] = str(self.storage.save_artifact(
                "exports", f"{base}.mp3", audio.mp3_bytes))
        logger.info("Podcast generated: %s (%d segments)",
                    script.title, len(script.segments))
        return FlowResult(True, payload=payload)

    # -- journeys -----------------------------------------------------------

    @_flow
    def generate_journey(self, topic: str, level: str,
                         num_cards: int = 5) -> FlowResult:
        from engines.journey_core.generator import generate_journey
        journey = generate_journey(
            topic=topic.strip(), level=level.strip(),
            num_cards=int(num_cards), client=self.client, model=self.model,
        )
        return FlowResult(True, payload=journey)

    @_flow
    def render_and_save_journey(self, journey: dict) -> FlowResult:
        from engines.journey_core.renderer import render_journey_html

        topic = journey.get("topic") or "untitled"
        slug = "".join(c if c.isalnum() else "-" for c in topic.lower()).strip("-")
        name = f"{slug or 'journey'}.html"
        html = render_journey_html(journey)
        path = self.storage.save_artifact("exports", name, html)
        return FlowResult(True, payload=path)

    # -- language lab -------------------------------------------------------

    @_flow
    def generate_lesson_pack(self, topic: str, target_language: str,
                             known_language: str, level: str) -> FlowResult:
        """One guardrailed generation -> validated pack -> interactive
        HTML saved under exports. Returns the file path for the UI to
        open in a browser."""
        from engines.language_lab.lesson_pack import generate_lesson_pack as run_generation
        from engines.language_lab.renderer import render_lesson_pack_html

        topic = topic.strip()
        if not topic:
            raise ValueError("Topic must be non-empty")
        pack = run_generation(
            topic, target_language.strip().lower(),
            known_language.strip().lower(), level.strip().lower(),
            client=self.client, model=self.model,
        )
        slug = "".join(c if c.isalnum() else "-" for c in topic.lower()).strip("-")
        base = f"lesson-{slug or 'pack'}-{target_language.lower()}"
        # the pack itself persists under its own kind; its fidelity audit
        # lands under verdicts so both stay inspectable (CONTEXT.md)
        self.storage.save_artifact("lesson_packs", f"{base}.json", pack)
        try:
            from engines.language_lab.graders import verify_lesson_pack
            audit = verify_lesson_pack(pack, client=self.client,
                                       model=self.model)
            self.storage.save_artifact("verdicts", f"{base}-audit.json",
                                       audit)
        except (SchemaValidationError, ApiError) as exc:
            logger.warning("Pack fidelity audit skipped: %s", exc)

        # per-segment audio: rendered NEXT TO the HTML so its relative
        # <audio> srcs resolve when opened in a browser (spec C2). TTS
        # absence degrades honestly — the pack ships without audio.
        audio_files: dict[str, str] = {}
        try:
            from engines.language_lab.pack_audio import render_pack_audio
            exports_dir = Path(self.storage.root) / "exports"
            segments = render_pack_audio(
                pack, stem=base, output_path=str(exports_dir))
            audio_files = {s.key: s.name for s in segments}
        except (RuntimeError, FileNotFoundError) as exc:
            logger.warning("Pack audio skipped (%s); shipping silent pack",
                           exc)

        path = self.storage.save_artifact(
            "exports", f"{base}.html",
            render_lesson_pack_html(pack, audio_files=audio_files or None))
        logger.info("Lesson pack rendered -> %s (%d audio segments)",
                    path, len(audio_files))
        return FlowResult(True, payload=str(path))

    @_flow
    def export_artifact(self, content: dict, fmt: str) -> FlowResult:
        from engines.export_engine.export import export as run_export
        result = run_export(content, format=fmt)
        return FlowResult(True, payload=result)

    @_flow
    def save_raw_export(self, data: Any, name: str) -> FlowResult:
        path = self.storage.save_artifact("exports", name, data)
        return FlowResult(True, payload=path)

    # -- library ----------------------------------------------------------

    @_flow
    def list_saved(self, kind: str) -> FlowResult:
        return FlowResult(True, payload=self.storage.list_artifacts(kind))

    @_flow
    def load_saved(self, kind: str, name: str) -> FlowResult:
        return FlowResult(True, payload=self.storage.load_artifact(kind, name))

    # -- playground (P7.12) -------------------------------------------------

    def default_inbox_path(self) -> str:
        if self.inbox_path:
            return self.inbox_path
        return str(Path(self.storage.root) / "inbox")

    def _ensure_hub(self):
        if self._hub is None:
            from engines.playground_bridge.connectors_gradio import (
                default_image_connector,
                default_music_connector,
            )
            from engines.playground_bridge.connectors_hub import ConnectorHub
            from engines.playground_bridge.connectors_figma import (
                FigmaConnector,
            )
            from engines.playground_bridge.connectors_pollinations import (
                PollinationsConnector,
            )
            hub = ConnectorHub()
            for connector in [
                PollinationsConnector(),
                default_image_connector(),
                default_music_connector(),
                FigmaConnector(),
                *self._extra_connectors,
            ]:
                hub.register(connector)
            self._hub = hub
        return self._hub

    @_flow
    def connector_names(self) -> FlowResult:
        return FlowResult(True, payload=self._ensure_hub().names())

    @_flow
    def connector_capabilities(self) -> FlowResult:
        """[{connector, auth, items:[{kind,description,quota_note}]}] —
        quota notes are UI-mandated reading (plan B0.4)."""
        payload = [
            {"connector": caps.connector, "auth": caps.auth,
             "items": [item.__dict__ for item in caps.items]}
            for caps in self._ensure_hub().all_capabilities()
        ]
        return FlowResult(True, payload=payload)

    @_flow
    def run_connector_job(self, name: str, op: dict) -> FlowResult:
        """send+poll in one flow; successful media lands under
        media/generated with a collision-safe name."""
        from engines.playground_bridge.connectors_hub import Job

        hub = self._ensure_hub()
        try:
            connector = hub.get(name)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        job = connector.send(None, op)
        result = connector.poll(Job(job.id, job.connector, job.status))
        if not result.ok:
            logger.warning("Connector %s failed: %s", name, result.error)
            return FlowResult(False, error_kind="connector",
                              detail=result.error or "generation failed")
        ext = _EXT_FOR_KIND.get(str(getattr(
            connector.capabilities().items[0], "kind", "")) , ".bin") \
            if connector.capabilities().items else ".bin"
        prompt = str(op.get("prompt", name))
        slug = "".join(c if c.isalnum() else "-" for c in prompt.lower())
        slug = slug.strip("-")[:40] or name
        existing = set(self.storage.list_artifacts("media/generated"))
        artifact_name = unique_artifact_name(existing, f"{slug}{ext}")
        self.storage.save_artifact("media/generated", artifact_name,
                                   result.media_bytes)
        return FlowResult(True, payload={"artifact_name": artifact_name,
                                         "size_bytes":
                                             len(result.media_bytes)})

    @_flow
    def scan_import_inbox(self) -> FlowResult:
        from engines.playground_bridge.import_inbox import scan_inbox
        records = scan_inbox(self.default_inbox_path(), self.storage)
        return FlowResult(True, payload=[
            {"source": r.source_name, "artifact": r.artifact_name,
             "ok": r.ok, "error": r.error}
            for r in records
        ])

    @_flow
    def import_files(self, paths: list[str]) -> FlowResult:
        """Copy picked files into media/library with collision-safe
        names; per-file errors are reported, never fatal to the batch."""
        results = []
        existing = set(self.storage.list_artifacts("media/library"))
        for raw_path in paths:
            path = Path(raw_path)
            try:
                data = path.read_bytes()
                name = unique_artifact_name(existing, path.name)
                self.storage.save_artifact("media/library", name, data)
                existing.add(name)
                results.append({"source": path.name, "artifact": name,
                                "ok": True, "error": None})
            except OSError as exc:
                results.append({"source": path.name, "artifact": None,
                                "ok": False, "error": str(exc)})
        return FlowResult(True, payload=results)

    @_flow
    def list_media(self, subkind: str) -> FlowResult:
        return FlowResult(True,
                          payload=self.storage.list_artifacts(f"media/{subkind}"))

    @_flow
    def load_media(self, subkind: str, name: str) -> FlowResult:
        return FlowResult(True, payload=self.storage.load_artifact(
            f"media/{subkind}", name))
