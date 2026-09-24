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
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engines.playground_bridge.import_inbox import unique_artifact_name
from model_layer.client import ApiError, ConnectionError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL
from model_layer.schema import SchemaValidationError
from storage.licensing import (
    TIER_PRICES, UPGRADE_URL, LicenseStore,
)
from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)

_EXT_FOR_KIND = {"image": ".png", "audio": ".wav", "video": ".mp4",
                 "design": ".png"}


def _render_reading_pack_html(pack: dict[str, Any]) -> str:
    """Deterministic HTML for reading/listening packs — no model
    calls, everything escaped, self-contained (shares the app footer
    so every exported pack is a landing page)."""
    import html as html_mod
    from engines.language_lab.renderer import (
        APP_NAME, APP_URL, PackFooter,
    )
    footer = PackFooter().render()
    title = html_mod.escape(str(pack.get("title") or "Reading pack"))
    text = html_mod.escape(str(pack.get("cleaned_text") or ""))
    glossary = "".join(
        f"<li><b>{html_mod.escape(str(g.get('term')))}</b> — "
        f"{html_mod.escape(str(g.get('translation')))}</li>"
        for g in pack.get("glossary") or [])
    questions = []
    for i, q in enumerate(pack.get("questions") or [], 1):
        options = "".join(
            f'<button onclick="pick({i},this,{qi})">'
            f"{html_mod.escape(str(opt))}</button>"
            for qi, opt in enumerate(q.get("options") or []))
        questions.append(
            f"<div class='q'><p><b>Q{i}.</b> "
            f"{html_mod.escape(str(q.get('question')))}</p>"
            f"<div class='opts'>{options}</div>"
            f"<p class='fb' id='fb{i}'></p></div>")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:760px;margin:24px
auto;padding:0 16px;line-height:1.6;color:#182a23;background:#faf8f2}}
h1{{color:#1e5a48}} .text{{background:#fff;padding:18px;border-radius:
12px;border:1px solid #ddd4c1;white-space:pre-wrap}} .glossary li{{
margin:4px 0}} .q{{margin:16px 0;padding:14px;background:#fff;
border-radius:12px;border:1px solid #ddd4c1}} .opts button{{
display:block;width:100%;text-align:left;margin:6px 0;padding:10px
14px;border:1.5px solid #ddd4c1;border-radius:10px;background:#fff;
cursor:pointer;font-size:1rem}} .opts button:hover{{border-color:#1e5a48}}
.opts button.ok{{background:#d1fae5;border-color:#2e7d5b;font-weight:700}}
.opts button.bad{{background:#fee2e2;border-color:#b23c2a}}
.fb{{font-weight:700}} .ldcc-footer{{margin-top:2rem;padding-top:1rem;
border-top:1px solid #ddd4c1;color:#6b7a70;font-size:.85rem}}
</style></head><body>
<h1>{title}</h1>
<div class="text">{text}</div>
<h2>Glossary</h2><ul class="glossary">{glossary}</ul>
<h2>Questions</h2>{"".join(questions)}
{footer}
<script>
function pick(q,btn,i){{
  var fb=document.getElementById('fb'+q);
  var correct={"".join(str(q.get("correct_index", 0)) for q in pack.get("questions") or [])};
  var target=correct[q-1];
  if(i===target){{btn.className='ok';fb.textContent='✅ Richtig!';
  fb.style.color='#2e7d5b';}}
  else{{btn.className='bad';fb.textContent='❌ Not this one — try '
  + 'another.';fb.style.color='#b23c2a';}}
}}
</script></body></html>"""

# Human reading of every license failure reason — the shell must never
# show a raw token error to someone who paid (or is about to).
_LICENSE_REASONS = {
    "no_license": "No license key has been activated on this machine.",
    "malformed": "That key is not a valid license key — it should look "
                 "like LDCC1.<long string> and be copied in full.",
    "bad_signature": "That key was not issued by L&D Command Center "
                     "(or was altered). Check you copied the whole line.",
    "expired": "That key has expired. Renew to keep Pro features.",
    "other_machine": "That key is locked to a different machine.",
    "unknown_tier": "That key carries an unknown tier.",
}


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
            # Surface the real validator reason (word-budget, speaker balance,
            # etc.) instead of the generic "card count" story — the change
            # trace from screen to store is only visible if the seam tells the
            # truth (scalable-code: borrowed constraints are only useful when
            # their errors are readable).
            detail = "The model kept producing invalid content — try rephrasing or lowering card count."
            if getattr(exc, "errors", None):
                # Keep the detail glanceable but specific: first two errors + attempt count.
                err_text = "; ".join(str(e) for e in exc.errors[:2])
                if err_text:
                    detail = f"After {exc.attempt} attempt(s): {err_text}"
            return FlowResult(False, error_kind="bad_output", detail=detail)
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
        licenses: Optional[LicenseStore] = None,
        machine_id: Optional[str] = None,
    ) -> None:
        self.client = client if client is not None else LmStudioClient()
        self.storage = storage if storage is not None else default_storage()
        self.model = model
        self._extra_connectors = list(connectors or [])
        self._hub = None
        self.inbox_path = inbox_path  # None -> <storage root>/inbox
        # Entitlements: offline-only, never a network call (PROFIT_PLAN §2).
        self.machine_id = machine_id
        self.licenses = licenses or LicenseStore(self.storage,
                                                 machine_id=machine_id)

    # -- health -----------------------------------------------------------

    @_flow
    def list_available_models(self) -> FlowResult:
        return FlowResult(True, payload=self.client.list_models())

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

    # -- licensing (F7 / PROFIT_PLAN §2) ------------------------------------

    @_flow
    def license_status(self) -> FlowResult:
        """The whole entitlement picture in one offline read: tier,
        validity, per-feature quotas, and the price ladder for the
        upgrade panel."""
        return FlowResult(True, payload=self.licenses.summary())

    @_flow
    def activate_license(self, token: str) -> FlowResult:
        """Activate a purchased key. Verified offline — no account, no
        phone-home; an invalid key never replaces a working one."""
        status = self.licenses.activate(token)
        if not status.valid:
            detail = _LICENSE_REASONS.get(
                status.reason, "That key could not be activated.")
            return FlowResult(False, error_kind="license", detail=detail,
                              payload=status.as_dict())
        logger.info("License activated: %s", status.tier)
        return FlowResult(True, payload=self.licenses.summary())

    @_flow
    def deactivate_license(self) -> FlowResult:
        """Forget the key (reinstall / support hand-off). Usage counters
        stay — they belong to the install, not the license."""
        self.licenses.deactivate()
        return FlowResult(True, payload=self.licenses.summary())

    def _gate(self, feature: str) -> Optional[FlowResult]:
        """Refusal envelope when the free tier is out of quota, else None.

        The payload carries the quota so the UI can say "2 of 3 packs
        left this week" without a second round trip. Gating happens
        BEFORE any expensive work: nobody burns a 3-minute CPU
        generation only to be told they are out of packs.
        """
        quota = self.licenses.quota(feature)
        if quota.allowed:
            return None
        detail = quota.message
        if UPGRADE_URL:
            detail = f"{detail}\n\n{UPGRADE_URL}"
        logger.info("Gate blocked %r (used %s/%s)", feature, quota.used,
                    quota.limit)
        return FlowResult(False, error_kind="license", detail=detail,
                          payload=quota.as_dict())

    # -- audio studio -------------------------------------------------------

    _TTS_MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "tts"

    @staticmethod
    def _voice_id_from_error(exc: FileNotFoundError) -> Optional[str]:
        m = re.search(r"([A-Za-z]{2}_[A-Za-z]{2}-[A-Za-z0-9_.\-]+)\.onnx",
                      str(exc))
        return m.group(1) if m else None

    def _ensure_voice(self, exc: FileNotFoundError) -> str:
        """Download the missing Piper voice named in the error and return
        its id. Re-raises when the message carries no usable id."""
        from engines.audio_engine.provisioning import download_voice
        voice_id = self._voice_id_from_error(exc)
        if not voice_id:
            raise exc
        logger.info("Voice %s missing — downloading on demand", voice_id)
        download_voice(voice_id, self._TTS_MODELS_DIR)
        return voice_id

    @_flow
    def download_voice(self, voice_id: str) -> FlowResult:
        """Explicitly fetch one Piper voice (model + config)."""
        from engines.audio_engine.provisioning import download_voice
        if not re.fullmatch(r"[A-Za-z]{2}_[A-Za-z]{2}-[A-Za-z0-9_.\-]+",
                            voice_id or ""):
            raise ValueError(f"Invalid voice id: {voice_id!r}")
        download_voice(voice_id, self._TTS_MODELS_DIR)
        return FlowResult(True, payload=voice_id)

    def all_known_voices(self) -> list[str]:
        """Every voice the app can ever reference: catalog narrators plus
        the podcast speaker pool."""
        from engines.audio_engine import voice_catalog
        known = sorted(set(voice_catalog.PIPER_LANGUAGE_VOICES.values())
                       | set(voice_catalog.PIPER_SPEAKER_POOL))
        installed = set(self.available_voices())
        return [v + ("   (will download on first use)" if v not in installed
                     else "") for v in known]

    def _slug(self, text: str, fallback: str) -> str:
        return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:40] or fallback

    # -- curriculum library (L4, Project E.T. 2026-09-06) -------------------
    #
    # The ready-made catalogue: levels A1..C1 per language with a
    # deterministic lesson-slot matrix. Browsing is instant (zero
    # LLM); generating a slot runs the existing LessonPack pipeline
    # and auto-registers it in the library.

    def _catalog(self):
        from engines.language_lab.catalog_store import CatalogStore
        return CatalogStore(self.storage)

    @_flow
    def curriculum_catalog(self, language: str) -> FlowResult:
        """The full library view for one language, progress merged in.
        Instant and offline — never gated, never a model call."""
        return FlowResult(True, payload=self._catalog().catalog_index(
            language))

    @_flow
    def curriculum_stats(self, language: str) -> FlowResult:
        return FlowResult(True, payload=self._catalog().stats(language))

    @_flow
    def curriculum_next_lesson(self, language: str) -> FlowResult:
        """The 'continue learning' pointer for the home card."""
        nxt = self._catalog().next_lesson(language)
        return FlowResult(True, payload=nxt)  # None = curriculum done

    @_flow
    def curriculum_generate_slot(self, language: str,
                                 slot_key: str) -> FlowResult:
        """Generate ONE catalog slot's lesson pack (gated by the
        lesson_pack quota; auto-registered in the library)."""
        from engines.language_lab.cefr import slot_for
        from engines.language_lab.lesson_pack import (
            generate_lesson_pack as run_generation,
        )
        slot = slot_for(slot_key)
        if slot is None:
            raise ValueError(
                f"Unknown lesson {slot_key!r} — pick one from the "
                "library.")
        gate = self._gate("lesson_pack")
        if gate is not None:
            return gate
        language = (language or "en").lower()[:2]
        pack = run_generation(
            slot.topic_prompt(), language, "en", slot.level,
            client=self.client, model=self.model)
        slug = "".join(c if c.isalnum() else "-"
                       for c in slot.key.lower()).strip("-")
        base = f"{language}-{slug}"
        self.storage.save_artifact("lesson_packs", f"{base}.json", pack)
        try:
            from engines.language_lab.graders import verify_lesson_pack
            audit = verify_lesson_pack(pack, client=self.client,
                                       model=self.model)
            self.storage.save_artifact("verdicts", f"{base}-audit.json",
                                       audit)
        except Exception as exc:  # noqa: BLE001 — audit is advisory
            logger.warning("Slot fidelity audit skipped: %s", exc)
        audio_files: dict[str, str] = {}
        try:
            import base64
            from engines.language_lab.pack_audio import render_pack_audio
            exports_dir = Path(self.storage.root) / "exports"
            segments = render_pack_audio(
                pack, stem=base, output_path=str(exports_dir))
            for seg in segments:
                audio_files[seg.key] = (
                    "data:audio/wav;base64,"
                    + base64.b64encode(seg.wav_bytes).decode())
        except Exception as exc:  # noqa: BLE001 — audio is a bonus
            logger.warning("Slot audio skipped (%s); shipping silent "
                           "pack", exc)
        from engines.language_lab.renderer import render_lesson_pack_html
        path = self.storage.save_artifact(
            "exports", f"{base}.html",
            render_lesson_pack_html(pack,
                                   audio_files=audio_files or None))
        self._catalog().mark_generated(language, slot_key,
                                       f"{base}.json")
        self.licenses.consume("lesson_pack")
        logger.info("Curriculum slot %s/%s rendered -> %s", language,
                    slot_key, path)
        return FlowResult(True, payload={
            "path": str(path), "pack": f"{base}.json",
            "slot": slot_key, "language": language,
            "quota": self.licenses.quota("lesson_pack").as_dict()})

    @_flow
    def curriculum_mark_done(self, language: str, slot_key: str,
                             score_pct: int) -> FlowResult:
        """Mark a slot's lesson done (called by the UI when the user
        finishes the pack's final evaluation). Feeds SRS vocabulary."""
        from engines.language_lab.cefr import slot_for
        if slot_for(slot_key) is None:
            raise ValueError(f"Unknown lesson {slot_key!r}.")
        self._catalog().mark_done(language, slot_key, score_pct)
        return FlowResult(True, payload={
            "progress": self._catalog().level_progress(
                language, slot_key.split("-")[0]),
            "next": self._catalog().next_lesson(language)})

    # -- level exams + placement (L5, Project E.T. 2026-09-06) --------------

    def _exam_attempts(self) -> dict[str, Any]:
        return self.storage.get_preference("level_exam_attempts", {}) \
            or {}

    def _save_exam_attempts(self, data: dict[str, Any]) -> None:
        self.storage.set_preference("level_exam_attempts", data)

    @_flow
    def level_exam_start(self, language: str, level: str) -> FlowResult:
        """Generate + persist ONE complete exam (gated: 1 per level on
        the free tier; Pro retakes freely). The exam doc is stored
        under level_exams; the UI drives question delivery."""
        from engines.language_lab.level_exam import generate_level_exam
        level = (level or "").strip().lower()
        if level not in ("a1", "a2", "b1", "b2", "c1"):
            raise ValueError("Level must be a1, a2, b1, b2 or c1.")
        attempts = self._exam_attempts()
        key = f"{(language or 'en').lower()[:2]}:{level}"
        # Free tier: ONE shot per (language, level) — the lifetime
        # credit pool backs the five levels; retakes need Pro.
        if self.licenses.tier() == "free" and attempts.get(key, 0) >= 1:
            return FlowResult(
                False, error_kind="license",
                detail=(
                    "You've already taken the "
                    f"{level.upper()} exam on the free tier. Review "
                    "your result in the Exams list — or activate Pro "
                    "for unlimited retakes while you polish."),
                payload={"feature": "level_exam"})
        gate = self._gate("level_exam")
        if gate is not None:
            return gate
        exam = generate_level_exam(language, level,
                                   client=self.client, model=self.model)
        attempts[key] = int(attempts.get(key, 0)) + 1
        self._save_exam_attempts(attempts)
        name = f"{(language or 'en').lower()[:2]}-{level}-exam.json"
        self.storage.save_artifact("level_exams", name, exam)
        # listening audio rendered once, cached next to the exam
        audio_path = None
        try:
            import base64
            from engines.audio_engine.assembly import render_segments
            from engines.language_lab.pack_audio import (
                assign_speaker_voices,
            )
            script = exam.get("listening", {}).get("script") or []
            voices = assign_speaker_voices({"dialogue": script})
            segments = []
            for i, turn in enumerate(script):
                segments.append((turn["content"],
                                 voices[turn["speaker"]], 1.0))
                segments.append(("silence", 0.35))
            if segments:
                stem = f"{(language or 'en').lower()[:2]}-{level}-exam"
                exports_dir = Path(self.storage.root) / "exports"
                result = render_segments(segments,
                                         include_mp3=False,
                                         output_path=str(exports_dir),
                                         basename=stem)
                audio_path = self.storage.save_artifact(
                    "exports", f"{stem}-listening.wav",
                    result.wav_bytes)
        except Exception as exc:  # noqa: BLE001 — audio is a bonus
            logger.warning("Exam listening audio skipped: %s", exc)
        self.licenses.consume("level_exam")
        return FlowResult(True, payload={"exam": exam,
                                         "saved_as": name,
                                         "listening_wav": str(audio_path)
                                         if audio_path else None})

    @_flow
    def level_exam_submit(self, language: str, level: str,
                          exam: dict[str, Any],
                          answers: dict[str, Any],
                          writing_answer: str,
                          speaking_tasks: list[dict[str, Any]]
                          ) -> FlowResult:
        """Grade everything: objective sections deterministically,
        writing + free speaking through the rubric judge, repeat-task
        by STT similarity, then assemble the full result with
        recommendations and persist it."""
        from engines.language_lab.level_exam import (
            build_exam_result, grade_objective_sections,
            grade_speaking_repeat, judge_answer,
        )
        language = (language or "en").lower()[:2]
        objective = grade_objective_sections(exam, answers or {})
        writing = judge_answer(
            str((exam.get("writing") or {}).get("prompt") or ""),
            writing_answer or "", language=language, level=level,
            client=self.client, model=self.model) \
            if (writing_answer or "").strip() else \
            {"grammar": 3, "vocabulary": 3, "structure": 3,
             "register": 3,
             "feedback": "(no answer submitted — counted neutrally)",
             "band_estimate": level}
        speaking: list[dict[str, Any]] = []
        speaking_spec = exam.get("speaking") or []
        for i, task in enumerate(speaking_spec):
            entry = dict(speaking_tasks[i]) if i < len(speaking_tasks) \
                else {}
            if task.get("type") == "repeat":
                entry["score"] = grade_speaking_repeat(
                    str(task.get("text") or ""),
                    str(entry.get("transcript") or ""))
            elif not entry.get("score"):
                judged = judge_answer(
                    str(task.get("situation") or
                        task.get("prompt") or "speaking task"),
                    str(entry.get("transcript") or ""),
                    language=language, level=level,
                    client=self.client, model=self.model)
                entry["score"] = sum(
                    judged.get(k, 3) for k in
                    ("grammar", "vocabulary", "structure", "register")
                ) / 20.0
                entry["band"] = judged.get("band_estimate")
            speaking.append(entry)
        result = build_exam_result(exam, objective, writing, speaking,
                                   language=language, level=level)
        name = f"{language}-{level}-result.json"
        self.storage.save_artifact("level_exams", name, result)
        # record exam completion in the curriculum journey
        try:
            if result.get("passed"):
                level_slots = ["people_friends", "food_dining",
                               "transport_travel", "shopping_money",
                               "home_admin", "health_body"] \
                    if level == "a1" else None
                if level_slots is None:
                    from engines.language_lab.cefr import lesson_slots
                    level_slots = [s.key.split("-", 1)[1]
                                   for s in lesson_slots(level)]
                # a passed exam marks the level's slots reviewed-done
                # at the exam score (the library respects it; users may
                # still re-open packs)
                for slot in level_slots:
                    existing = self._catalog().slot_status(
                        language, f"{level}-{slot}")
                    if existing["status"] != "done":
                        self._catalog().mark_done(
                            language, f"{level}-{slot}",
                            result["overall"])
        except Exception as exc:  # noqa: BLE001 — journey bookkeeping
            logger.warning("Exam->curriculum bookkeeping skipped: %s",
                           exc)
        logger.info("Level exam %s %s: %d%% (%s)", language, level,
                    result["overall"],
                    "PASS" if result["passed"] else "retry")
        return FlowResult(True, payload=result)

    @_flow
    def level_exam_results(self, language: str) -> FlowResult:
        """Past exam results for the Exams panel."""
        language = (language or "en").lower()[:2]
        names = sorted(n for n in
                       self.storage.list_artifacts("level_exams")
                       if n.startswith(f"{language}-") and
                       n.endswith("-result.json"))
        results = []
        for name in names:
            try:
                results.append(
                    self.storage.load_artifact("level_exams", name))
            except Exception:  # noqa: BLE001 — skip corrupt rows
                logger.warning("Unreadable exam result %s", name)
        return FlowResult(True, payload=results)

    @_flow
    def placement_start(self, language: str) -> FlowResult:
        """Generate the 12-item placement quiz (never gated — the
        front door stays free)."""
        from engines.language_lab.placement import (
            generate_placement_quiz,
        )
        quiz = generate_placement_quiz(language, client=self.client,
                                       model=self.model)
        self.storage.save_artifact(
            "placement", f"{(language or 'en').lower()[:2]}.json",
            quiz)
        return FlowResult(True, payload=quiz)

    @_flow
    def placement_grade(self, language: str,
                        answers: list[int]) -> FlowResult:
        """Score the placement quiz, persist the result, and wire the
        recommendation into the curriculum (next-lesson pointer)."""
        from engines.language_lab.placement import grade_placement
        language = (language or "en").lower()[:2]
        try:
            quiz = self.storage.load_artifact(
                "placement", f"{language}.json")
        except FileNotFoundError:
            raise ValueError("Start the placement quiz first.")
        result = grade_placement(quiz, answers or [])
        self.storage.set_preference(
            f"placement_{language}", result)
        return FlowResult(True, payload=result)

    @_flow
    def placement_last(self, language: str) -> FlowResult:
        """The saved placement result (None when never taken)."""
        language = (language or "en").lower()[:2]
        return FlowResult(True, payload=self.storage.get_preference(
            f"placement_{language}"))

    # -- skills arena (L6, Project E.T. 2026-09-06) --------------------------
    #
    # The Playground's four-skills practice surfaces: reading packs
    # from imported documents, writing evaluation, listening packs
    # from imported audio (STT -> comprehension questions). Speaking
    # lives in the E.T. panel. Every flow is gated only where the
    # quotas say so (writing_eval: 3/week free).

    @_flow
    def skills_reading_from_file(self, path: str, language: str,
                                  level: str) -> FlowResult:
        """Reading pack from an imported txt/PDF/DOCX: cleaned text +
        glossary + 4 questions, saved as a shareable HTML pack."""
        from engines.language_lab.skills import (
            extract_document_text, generate_reading_pack,
        )
        text = extract_document_text(path)
        if not text.strip():
            raise ValueError(
                "Couldn't read that file (or it has no text — scans "
                "and images need OCR first). Try a .txt, .pdf with a "
                "text layer, or .docx.")
        pack = generate_reading_pack(text, language, level,
                                     client=self.client,
                                     model=self.model)
        import html as html_mod
        from pathlib import PurePath
        stem = PurePath(path).stem or "reading"
        name = unique_artifact_name(
            set(self.storage.list_artifacts("exports")),
            f"reading-{self._slug(stem, 'pack')}.html")
        document = _render_reading_pack_html(pack)
        path_out = self.storage.save_artifact("exports", name, document)
        return FlowResult(True, payload={"path": str(path_out),
                                          "pack": pack})

    @_flow
    def skills_writing_submit(self, task: str, text: str,
                              language: str, level: str) -> FlowResult:
        """Evaluate one piece of writing (3/week on free; unlimited
        Pro). The corrected version + highlights come back for the
        panel; everything is saved to exports for keeps."""
        from engines.language_lab.skills import evaluate_writing
        gate = self._gate("writing_eval")
        if gate is not None:
            return gate
        result = evaluate_writing(task, text, language, level,
                                  client=self.client, model=self.model)
        self.licenses.consume("writing_eval")
        # save the evaluation for the learner's records
        record = {"task": task, "original": text,
                  "evaluation": result,
                  "language": language, "level": level,
                  "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        name = unique_artifact_name(
            set(self.storage.list_artifacts("exports")),
            f"writing-{self._slug(task or 'practice', 'eval')}.json")
        self.storage.save_artifact("exports", name, record)
        return FlowResult(True, payload={
            "evaluation": result,
            "quota": self.licenses.quota("writing_eval").as_dict(),
            "saved_as": name})

    @_flow
    def skills_listening_from_file(self, path: str, language: str,
                                    level: str) -> FlowResult:
        """Listening pack from an imported audio file: transcribe via
        STT, then generate comprehension questions about the content.
        The transcript is shown with the questions — real practice on
        the user's own material (podcasts they like, meeting
        recordings, etc.)."""
        from pathlib import Path
        audio = Path(path).read_bytes() if Path(path).exists() else b""
        if not audio:
            raise ValueError("That audio file could not be read.")
        from engines.audio_engine.stt import transcribe
        transcript = transcribe(audio, (language or "en").lower()[:2])
        if not transcript.text.strip():
            raise ValueError(
                "No speech was detected in that audio — silence makes "
                "a short lesson. Try a file with talking in it.")
        # comprehension questions from the transcript via reading-pack
        # machinery (the transcript IS the text)
        from engines.language_lab.skills import generate_reading_pack
        pack = generate_reading_pack(
            "Transcript of the audio:\n" + transcript.text,
            language, level, client=self.client, model=self.model)
        document = _render_reading_pack_html(
            {**pack, "title": pack.get("title") or "Listening pack",
             "cleaned_text": transcript.text})
        stem = Path(path).stem or "listening"
        name = unique_artifact_name(
            set(self.storage.list_artifacts("exports")),
            f"listening-{self._slug(stem, 'pack')}.html")
        path_out = self.storage.save_artifact("exports", name, document)
        return FlowResult(True, payload={
            "path": str(path_out), "transcript": transcript.text,
            "questions": pack["questions"]})

    # -- E.T. conversations (Project E.T., 2026-09-06) ----------------------
    #
    # The voice conversation feature's entire app surface. Sessions live
    # in ONE in-memory slot (the UI runs one conversation at a time);
    # every completed turn persists the full transcript so nothing is
    # ever lost. Voice capture/STT run on worker threads via the UI's
    # run_async; failures degrade to typing mode, never a crash.

    _ET_STATE_KEY = "et_state"

    def _et_session(self) -> Optional[Any]:
        return getattr(self, "_et_active", None)

    @_flow
    def et_scenario_bank(self) -> FlowResult:
        """The catalog the E.T. panel picks from (no model call)."""
        from engines.language_lab.et_scenarios import scenario_bank
        return FlowResult(True, payload=[
            {"key": s.key, "title": s.title_en, "domain": s.domain,
             "goal": s.goal, "special": s.special}
            for s in scenario_bank()])

    @_flow
    def et_microphone_devices(self) -> FlowResult:
        """Autodetected input devices for the mic picker; empty list =
        typing mode (the panel adapts, never blocks)."""
        from engines.audio_engine.mic import list_input_devices
        return FlowResult(True, payload=[
            {"index": d.index, "name": d.name} for d in
            list_input_devices()])

    @_flow
    def et_start_session(self, language: str, level: str,
                         scenario_key: str, persona_key: str,
                         length: str, user_name: str = "",
                         device_index: Optional[int] = None
                         ) -> FlowResult:
        """Open a conversation. Consumes NO quota — turns are metered
        as spoken; starting is always free (browsing is not usage)."""
        from engines.language_lab.et_conversation import start_session
        session = start_session(
            language, level, scenario_key, persona_key, length,
            user_name=user_name, client=self.client, model=self.model,
            transcribe_fn=self._et_transcriber(),
            speak_fn=self._et_speaker())
        self._et_active = session
        self._et_device = device_index
        return FlowResult(True, payload={"scenario": scenario_key,
                                         "persona": persona_key,
                                         "length": length})

    def _et_transcriber(self):
        """Lazily resolved transcription callable; None when STT is
        unavailable (typing-only session)."""
        if getattr(self, "_et_transcribe_fn", None) is not None:
            return self._et_transcribe_fn
        from engines.audio_engine.stt import SttUnavailableError

        def transcribe(wav_bytes: bytes, language: str):
            from engines.audio_engine.stt import transcribe
            return transcribe(wav_bytes, language)
        self._et_transcribe_fn = transcribe
        return transcribe

    def _et_speaker(self):
        """Persona-aware TTS: Mr./Mrs. E.T. resolve through the voice
        pair table; single-voice languages pitch-shift the female
        persona. Returns WAV bytes or None if synthesis is impossible
        (text reply still works)."""
        from engines.audio_engine.assembly import pitch_shift
        from engines.audio_engine.voice_catalog import et_voice_pair

        def speak(text: str, persona, language: str):
            from engines.audio_engine.assembly import (
                _make_wav_header,
                synthesize as seam_synthesize,
            )
            from model_layer.tts import TtsBackend
            male, female, real_pair = et_voice_pair(language)
            voice = (male if persona.voice_role == "male" else female)
            speed = 1.0
            if not real_pair and persona.voice_role == "female":
                voice = male  # shift below from the single base voice
            try:
                pcm, rate = seam_synthesize(text, voice=voice,
                                            speed=speed,
                                            backend=TtsBackend.PIPER)
            except FileNotFoundError as exc:
                self._ensure_voice(exc)
                pcm, rate = seam_synthesize(text, voice=voice,
                                            speed=speed,
                                            backend=TtsBackend.PIPER)
            except Exception as exc:  # noqa: BLE001 — voice optional
                logger.warning("E.T. voice failed (%s); text-only reply",
                              exc)
                return None
            wav = _make_wav_header(len(pcm), rate) + pcm
            if (not real_pair) and persona.voice_role == "female":
                wav = pitch_shift(wav, 3.0)  # brighter: Mrs. E.T.
            return wav
        return speak

    @_flow
    def et_opening_line(self) -> FlowResult:
        """Generate + speak E.T.'s first line (async in the UI)."""
        session = self._et_session()
        if session is None:
            raise ValueError("Start a conversation first — pick a "
                             "scenario and press Start.")
        line = session.opening_line()
        audio = None
        speak = self._et_speaker()
        try:
            audio = speak(line, session.persona, session.config.language)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Opening voice failed: %s", exc)
        return FlowResult(True, payload={"line": line, "audio": audio})

    @_flow
    def et_submit_voice(self, wav_bytes: Optional[bytes] = None,
                        device_index: Optional[int] = None
                        ) -> FlowResult:
        """One voice turn. Pass wav_bytes when the UI already captured
        (its record button with pulse + stop); omit to let the
        controller capture from `device_index`. Clarity re-asks and
        quota refusals are typed results with actionable copy — the
        quota gate runs BEFORE any recording, always."""
        from engines.audio_engine.mic import (MicrophoneError,
                                              capture_speech)
        session = self._et_session()
        if session is None:
            raise ValueError("Start a conversation first.")
        gate = self._gate("et_turn")
        if gate is not None:
            return gate
        if wav_bytes is None:
            try:
                capture = capture_speech(
                    device=device_index if device_index is not None
                    else getattr(self, "_et_device", None),
                    max_seconds=90.0)
                wav_bytes = capture.wav_bytes
            except MicrophoneError as exc:
                return FlowResult(False, error_kind="device",
                                  detail=str(exc))
        event = session.submit_voice(wav_bytes)
        return self._et_turn_result(event)

    @_flow
    def et_submit_text(self, text: str) -> FlowResult:
        """One typed turn — always available, same pipeline."""
        session = self._et_session()
        if session is None:
            raise ValueError("Start a conversation first.")
        gate = self._gate("et_turn")
        if gate is not None:
            return gate
        event = session.submit_text(text)
        return self._et_turn_result(event)

    def _et_turn_result(self, event: dict[str, Any]) -> FlowResult:
        """Normalize an engine event: consumed turns persist + meter;
        repeat/error pass through with their copy intact."""
        kind = event.get("kind")
        if kind == "turn":
            self.licenses.consume("et_turn")
            self._et_persist()
            payload = dict(event)
            payload["quota"] = self.licenses.quota(
                "et_turn").as_dict()
            return FlowResult(True, payload=payload)
        if kind == "repeat":
            return FlowResult(False, error_kind="et_repeat",
                              detail=event.get("detail") or
                              "E.T. didn't catch that clearly — say "
                              "it once more. No turn lost.",
                              payload={"clarity": event.get("clarity")})
        if kind == "closed":
            return FlowResult(True, payload={"closed": True,
                                             "detail": event.get(
                                                 "detail")})
        # engine-level user-input problems (empty text, missing STT)
        detail = str(event.get("detail") or
                     "The turn went sideways. Try again.")
        if "Say something" in detail or "not available" in detail:
            return FlowResult(False, error_kind="input", detail=detail)
        return FlowResult(False, error_kind="unexpected", detail=detail)

    def _et_persist(self) -> None:
        """Write the full transcript after every completed turn."""
        session = self._et_session()
        if session is None:
            return
        name = (f"{self._slug(session.config.scenario_key, 'et')}-"
                f"{session.config.language}-"
                f"{self._slug(session.created_at, 'session')}.json")
        try:
            self.storage.save_artifact("et_sessions", name,
                                       session.to_dict())
        except Exception as exc:  # noqa: BLE001 — persistence is best-effort
            logger.warning("E.T. transcript save failed: %s", exc)

    @_flow
    def et_session_state(self) -> FlowResult:
        """Current conversation snapshot for panel restore."""
        session = self._et_session()
        if session is None:
            return FlowResult(True, payload={"active": False})
        return FlowResult(True, payload={
            "active": True,
            "turns_used": session.turns_used,
            "max_turns": session.max_turns,
            "persona": session.persona.name,
            "scenario": session.scenario.title_en,
            "language": session.config.language,
            "transcript": [t.to_dict() for t in session.turns]})

    @_flow
    def et_end_session(self) -> FlowResult:
        """Close the conversation (transcript is already persisted)."""
        self._et_active = None
        return FlowResult(True, payload=True)

    @_flow
    def et_play_line(self, text: str, persona_key: str = "mr",
                     language: str = "en") -> FlowResult:
        """Replay any E.T. line as audio (tap-a-bubble)."""
        from engines.language_lab.et_persona import persona_for
        speak = self._et_speaker()
        audio = speak(text, persona_for(persona_key), language)
        if audio is None:
            raise ValueError("E.T.'s voice is not ready on this "
                              "machine — check the Voices panel.")
        return FlowResult(True, payload={"audio": audio})

    def available_voices(self, models_dir=None) -> list[str]:
        """Installed Piper voices — the UI's voice pickers feed from this."""
        from model_layer.tts import get_available_voices
        return get_available_voices(models_dir=models_dir)

    @_flow
    def generate_audiobook(self, text: str, language: str = "en",
                           speed: float = 1.0,
                           voice: Optional[str] = None) -> FlowResult:
        """Narration engine -> WAV+MP3 saved under exports."""
        from engines.audio_engine import voice_catalog
        from engines.audio_engine.narration import narrate

        text = (text or "").strip()
        if not text:
            raise ValueError("Text must be non-empty")
        narrator = voice or voice_catalog.narrator_voice(language)
        try:
            result = narrate(text, voice=narrator,
                             include_mp3=True, speed=float(speed))
        except FileNotFoundError as exc:
            self._ensure_voice(exc)
            result = narrate(text, voice=narrator,
                             include_mp3=True, speed=float(speed))
        existing = set(self.storage.list_artifacts("exports"))
        base = unique_artifact_name(existing, f"{self._slug(text, 'audiobook')}.wav")
        base = base[:-4]  # strip .wav; we add per-format suffixes
        wav_path = self.storage.save_artifact("exports", f"{base}.wav",
                                              result.wav_bytes)
        payload: dict[str, Any] = {
            "wav": str(wav_path),
            "mp3": None,
            # WAV duration = PCM bytes / 2 / rate; subtract the 44-byte
            # RIFF header so the reported length matches the player.
            "duration_seconds": round(
                max(0, len(result.wav_bytes) - 44) / 2
                / max(result.sample_rate, 1), 1),
            "voice": result.voice_used,
            "chars": len(text),
            "words": len(text.split()),
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
                         host_name: str = "Alex",
                         co_host_name: str = "Maya",
                         voice_a: Optional[str] = None,
                         voice_b: Optional[str] = None) -> FlowResult:
        """Script generation (Guardrail Loop) + two-voice render -> WAV/MP3.

        Length contract: the script is word-budgeted for `duration_minutes`
        (see podcast_script.make_length_validator). After the first render,
        if actual audio is under 92% of the target we re-render once at a
        slower speed (floor 0.70×) so the file reaches the requested length.
        """
        from engines.audio_engine import voice_catalog
        from engines.audio_engine.podcast_audio import (
            render_podcast_to_audio,
        )
        from engines.audio_engine.podcast_script import (
            SHORT_RENDER_RATIO,
            MIN_STRETCH_SPEED,
            generate_script_from_topic,
        )

        topic = (topic or "").strip()
        if not topic:
            raise ValueError("Topic must be non-empty")
        host = (host_name or "Alex").strip() or "Alex"
        co_host = (co_host_name or "Maya").strip() or "Maya"
        if co_host == host:
            raise ValueError("Co-host needs a different name than the host")
        target_minutes = max(1, int(duration_minutes))
        script = generate_script_from_topic(
            topic,
            num_segments=int(num_segments),
            duration_minutes=target_minutes,
            host_name=host, co_host_name=co_host,
            language=voice_catalog.language_name(language),
            level=level,
            client=self.client, model=self.model,
        )
        voice_map = {}
        if voice_a:
            voice_map[host] = voice_a
        if voice_b:
            voice_map[co_host] = voice_b

        def _render(speed: float = 1.0):
            try:
                return render_podcast_to_audio(script, include_mp3=True,
                                               voice_map=voice_map or None,
                                               speed=speed)
            except FileNotFoundError as exc:
                self._ensure_voice(exc)
                return render_podcast_to_audio(script, include_mp3=True,
                                               voice_map=voice_map or None,
                                               speed=speed)

        audio = _render()
        target_seconds = float(target_minutes * 60)
        if target_seconds > 0 and audio.duration_seconds < (
                target_seconds * SHORT_RENDER_RATIO):
            # Slow narration stretches duration ~1/speed. Clamp so we never
            # go below the quality floor; report actual length honestly.
            stretch_speed = max(
                MIN_STRETCH_SPEED,
                min(1.0, audio.duration_seconds / target_seconds),
            )
            logger.info(
                "Podcast short (%.0fs < %.0fs target); re-render at %.2fx",
                audio.duration_seconds, target_seconds, stretch_speed)
            audio = _render(speed=stretch_speed)

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
            "target_minutes": target_minutes,
            "target_seconds": target_seconds,
            "title": script.title,
            "speakers": sorted({seg.speaker for seg in script.segments}),
        }
        if audio.mp3_bytes:
            payload["mp3"] = str(self.storage.save_artifact(
                "exports", f"{base}.mp3", audio.mp3_bytes))
        logger.info("Podcast generated: %s (%d segments, %.0fs / %.0fs target)",
                    script.title, len(script.segments),
                    audio.duration_seconds, target_seconds)
        return FlowResult(True, payload=payload)

    # -- campaign mode (Campaign tier, PROFIT_PLAN §2/§6) --------------------

    def _campaign(self) -> "CampaignStore":
        from engines.career_engine.campaign import CampaignStore
        return CampaignStore(self.storage)

    @_flow
    def campaign_status(self) -> FlowResult:
        """The campaign dashboard: counts per status + all tracked
        applications. The summary is readable on every tier — the
        user's own history is never hidden from them; the ADVANCE
        controls and interview prep are the Campaign-tier features."""
        return FlowResult(True, payload=self._campaign().summary())

    @_flow
    def campaign_advance(self, listing: dict[str, Any], status: str,
                         notes: str = "") -> FlowResult:
        """Move a tracked application along the ladder (Campaign tier).
        Tracking itself is free — the ladder tooling is the paid
        feature that makes the watchlist a campaign manager."""
        if not self.licenses.has("campaign_mode"):
            return FlowResult(
                False, error_kind="license",
                detail=(
                    "Career Campaign mode — status tracking, follow-up "
                    "letters, interview prep per listing — is the "
                    f"{TIER_PRICES['campaign']['price']} tier. Your "
                    "applications are still tracked and visible; "
                    "advancing them needs Campaign."),
                payload={"feature": "campaign_mode"})
        record = self._campaign().advance(listing, status, notes=notes)
        return FlowResult(True, payload=record.to_dict())

    @_flow
    def campaign_generate_interview_prep(
            self, listing: dict[str, Any],
            resume: dict[str, Any]) -> FlowResult:
        """Interview prep pack for ONE tracked listing, grounded in the
        resume (Campaign tier, PROFIT_PLAN §2). Saved under its own
        storage kind so the whole story travels together."""
        if not self.licenses.has("campaign_mode"):
            return FlowResult(
                False, error_kind="license",
                detail=(
                    "Interview prep packs are part of Career Campaign "
                    f"mode — {TIER_PRICES['campaign']['price']}. They "
                    "generate likely questions, story answers from your "
                    "real resume, and questions to ask, for each "
                    "listing you are tracking."),
                payload={"feature": "campaign_mode"})
        from engines.career_engine.campaign import (
            generate_interview_prep,
        )
        company = str(listing.get("company") or "").strip()
        title = str(listing.get("title") or "").strip()
        if not company or not title:
            raise ValueError("Listing must carry a company and title")
        prep = generate_interview_prep(
            resume, role=title, company=company,
            snippet=str(listing.get("snippet") or ""),
            client=self.client, model=self.model)
        slug = self._slug(f"{company}-{title}", "interview")[:60]
        name = unique_artifact_name(
            set(self.storage.list_artifacts("interview_preps")),
            f"{slug}.json")
        path = self.storage.save_artifact("interview_preps", name, prep)
        logger.info("Interview prep saved -> %s", path)
        return FlowResult(True, payload={"path": str(path),
                                         "prep": prep})

    @_flow
    def campaign_track(self, listing: dict[str, Any]) -> FlowResult:
        """Track a listing without preparing a package (e.g. found on
        the board, applied manually). Free on every tier — the user's
        own application history is never paywalled."""
        record = self._campaign().track(listing)
        return FlowResult(True, payload=record.to_dict())

    @_flow
    def campaign_untrack(self, listing: dict[str, Any]) -> FlowResult:
        self._campaign().untrack(listing)
        return FlowResult(True, payload=True)

    # -- career -------------------------------------------------------------

    _JOB_WATCH_KEY = "job_watch"
    _JOB_SOURCES_KEY = "job_sources"
    _CAREER_IDENTITY_KEY = "career_identity"

    def _job_watch(self) -> dict[str, Any]:
        return self.storage.get_preference(self._JOB_WATCH_KEY, {}) or {}

    def _save_job_watch(self, config: dict[str, Any]) -> None:
        self.storage.set_preference(self._JOB_WATCH_KEY, config)

    def _career_identity(self) -> dict[str, Any]:
        """The career memory: who the user is across sessions — GitHub
        username, imported projects, LinkedIn basics, last target role.
        Everything the app has EVER learned about the user's accounts,
        so connections survive restarts and offline days."""
        return (self.storage.get_preference(self._CAREER_IDENTITY_KEY, {})
                or {})

    def _save_career_identity(self, identity: dict[str, Any]) -> None:
        self.storage.set_preference(self._CAREER_IDENTITY_KEY, identity)

    @_flow
    def get_career_identity(self) -> FlowResult:
        """Offline read of the career memory (never touches the network)."""
        return FlowResult(True, payload=self._career_identity())

    @_flow
    def clear_career_identity(self) -> FlowResult:
        """Forget everything the app stored about the user's accounts."""
        self._save_career_identity({})
        logger.info("Career identity cleared")
        return FlowResult(True, payload=True)

    def _job_sources(self) -> dict[str, list[str]]:
        """Saved company rosters per board (job_sources preference), or
        the engine's contact-center/CX defaults when never configured.
        Empty lists mean "skip this board" — never a hidden default."""
        from engines.career_engine.job_boards import (
            ASHBY_DEFAULT_COMPANIES, GREENHOUSE_DEFAULT_COMPANIES,
            LEVER_DEFAULT_COMPANIES,
        )
        cfg = self.storage.get_preference(self._JOB_SOURCES_KEY, {}) or {}
        return {
            "greenhouse_companies": cfg.get("greenhouse_companies",
                                            GREENHOUSE_DEFAULT_COMPANIES),
            "lever_companies": cfg.get("lever_companies",
                                       LEVER_DEFAULT_COMPANIES),
            "ashby_companies": cfg.get("ashby_companies",
                                       ASHBY_DEFAULT_COMPANIES),
        }

    @_flow
    def save_job_sources(self, greenhouse: str = "", lever: str = "",
                         ashby: str = "") -> FlowResult:
        """Persist the company rosters for all future searches and
        watchlist runs (comma-separated board tokens per board)."""
        cfg = self.storage.get_preference(self._JOB_SOURCES_KEY, {}) or {}
        cfg.update({
            "greenhouse_companies": [c.strip() for c in
                                     greenhouse.split(",") if c.strip()],
            "lever_companies": [c.strip() for c in
                                lever.split(",") if c.strip()],
            "ashby_companies": [c.strip() for c in
                                ashby.split(",") if c.strip()],
        })
        self.storage.set_preference(self._JOB_SOURCES_KEY, cfg)
        logger.info("Job board rosters saved: %d greenhouse, %d lever, "
                    "%d ashby companies",
                    len(cfg["greenhouse_companies"]),
                    len(cfg["lever_companies"]),
                    len(cfg["ashby_companies"]))
        return FlowResult(True, payload=True)

    @_flow
    def search_jobs_now(self, role: str, location: str = "",
                        remote_only: bool = True,
                        greenhouse_companies: str = "",
                        lever_companies: str = "",
                        ashby_companies: str = "") -> FlowResult:
        """Hunt across keyless boards NOW; rank by role-keyword hits.
        Explicit comma-separated company args win; anything omitted falls
        back to the saved job_sources preference, then the engine's
        contact-center/CX defaults."""
        from engines.career_engine.job_boards import (
            match_listings,
            search_all,
        )
        role = (role or "").strip()
        if not role:
            raise ValueError("Role keywords must be non-empty")
        saved = self._job_sources()
        # _csv_or: explicit UI arg beats saved preference beats default —
        # an empty string is "not specified", never "no companies".
        def _csv_or(given: str, saved_list: list[str]) -> list[str]:
            return ([c.strip() for c in given.split(",") if c.strip()]
                    or saved_list)
        merged = search_all(
            greenhouse_companies=_csv_or(greenhouse_companies,
                                          saved["greenhouse_companies"]),
            lever_companies=_csv_or(lever_companies,
                                    saved["lever_companies"]),
            ashby_companies=_csv_or(ashby_companies,
                                    saved["ashby_companies"]),
            title_query=role,
            location_query=location.strip(),
            include_remote=not location.strip(),
        )
        listings = [l for src in merged.values() for l in src]
        scored = match_listings(listings, role.split())
        payload = [dict(l.to_dict(), score=score)
                   for l, score in scored[:30]]
        logger.info("Job search %r: %d matches", role, len(payload))
        return FlowResult(True, payload=payload)

    @_flow
    def check_job_watchlist(self) -> FlowResult:
        """Run the SAVED search and report only NEW listings (diffed by
        URL against the stored seen-set). The polling agent's tick."""
        from engines.career_engine.job_boards import (
            match_listings,
            search_all,
        )
        cfg = self._job_watch()
        if not cfg.get("role"):
            return FlowResult(True, payload={"new": [], "total": 0,
                                             "configured": False})
        # saved watchlist company lists fall back to the shared job_sources
        # preference, then the engine defaults — a watchlist armed before
        # rosters were configurable keeps hunting the live defaults.
        saved = self._job_sources()

        def _or_saved(given: Any, key: str) -> list[str]:
            if given is None:
                return saved[key]
            return list(given) if given else saved[key]

        merged = search_all(
            greenhouse_companies=_or_saved(cfg.get("greenhouse_companies"),
                                          "greenhouse_companies"),
            lever_companies=_or_saved(cfg.get("lever_companies"),
                                      "lever_companies"),
            ashby_companies=_or_saved(cfg.get("ashby_companies"),
                                      "ashby_companies"),
            title_query=cfg["role"],
            location_query=cfg.get("location", ""),
            include_remote=not cfg.get("location"),
        )
        listings = [l for src in merged.values() for l in src]
        scored = match_listings(listings, cfg["role"].split())
        seen: set[str] = set(cfg.get("seen_urls", []))
        fresh = [dict(l.to_dict(), score=score) for l, score in scored
                 if l.url not in seen]
        for l, _ in scored:
            seen.add(l.url)
        cfg["seen_urls"] = sorted(seen)[-500:]  # cap growth
        cfg["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_job_watch(cfg)
        logger.info("Watchlist %r: %d new of %d",
                    cfg["role"], len(fresh), len(scored))
        return FlowResult(True, payload={"new": fresh[:20],
                                         "total": len(scored),
                                         "configured": True})

    @_flow
    def save_job_watchlist(self, role: str, location: str = "",
                            greenhouse_companies: str = "",
                            lever_companies: str = "",
                            ashby_companies: str = "") -> FlowResult:
        cfg = self._job_watch()
        saved = self._job_sources()
        # empty string args mean "use whatever the rosters currently say",
        # not "watch zero companies" — a watchlist with no boards is a
        # silent no-op and the agent must never arm one silently.
        cfg.update({
            "role": (role or "").strip(),
            "location": location.strip(),
            "greenhouse_companies": (
                [c.strip() for c in greenhouse_companies.split(",")
                 if c.strip()] or saved["greenhouse_companies"]),
            "lever_companies": (
                [c.strip() for c in lever_companies.split(",")
                 if c.strip()] or saved["lever_companies"]),
            "ashby_companies": (
                [c.strip() for c in ashby_companies.split(",")
                 if c.strip()] or saved["ashby_companies"]),
        })
        if not cfg["role"]:
            raise ValueError("Role must be non-empty to arm a watchlist")
        self._save_job_watch(cfg)
        return FlowResult(True, payload=True)

    @_flow
    def prepare_application(self, listing: dict[str, Any],
                            resume: dict[str, Any]) -> FlowResult:
        """Package one application automatically: tailored resume variant,
        grounded cover letter, PDF + DOCX exports, listing reference file.
        SUBMITTING stays a human click on the board's own page.

        Free tier: 5 packages, ever (PROFIT_PLAN §2). Pro: unlimited."""
        gate = self._gate("application_package")
        if gate is not None:
            return gate
        from engines.export_engine.export import export as run_export
        from engines.career_engine.resume.generator import (
            enhance as run_enhance,
            generate_cover_letter,
        )

        company = str(listing.get("company") or "unknown")
        title = str(listing.get("title") or "role")
        url = str(listing.get("url") or "")
        base_dir = Path(self.storage.root) / "exports" / "applications" / (
            re.sub(r"[^A-Za-z0-9]+", "-", f"{company}-{title}").strip("-").lower()
        )[:60]
        base_dir.mkdir(parents=True, exist_ok=True)

        enhanced = run_enhance(resume, title, client=self.client,
                               model=self.model)["enhanced_resume"]
        letter = generate_cover_letter(enhanced, role=title, company=company,
                                       snippet=str(listing.get("snippet") or ""),
                                       client=self.client, model=self.model)

        pdf_bytes = run_export(enhanced, format="pdf")
        docx_bytes = run_export(enhanced, format="docx")
        (base_dir / "resume.pdf").write_bytes(pdf_bytes)
        (base_dir / "resume.docx").write_bytes(docx_bytes)
        (base_dir / "cover_letter.txt").write_text(letter, encoding="utf-8")
        (base_dir / "listing.txt").write_text(
            f"{title} @ {company}\n{url}\n\n{listing.get('snippet', '')}",
            encoding="utf-8")
        self.licenses.consume("application_package")
        logger.info("Application package ready: %s", base_dir)
        # Campaign tier: preparing an application auto-tracks it in the
        # campaign pipeline (status 'prepared'). Tracking is free — the
        # tier gates the pipeline VIEW and interview prep, never the
        # user's own history.
        campaign = self._campaign()
        record = campaign.track(listing, package_dir=str(base_dir))
        return FlowResult(True, payload={
            "dir": str(base_dir),
            "apply_url": url,
            "files": ["resume.pdf", "resume.docx", "cover_letter.txt",
                      "listing.txt"],
            "quota": self.licenses.quota("application_package").as_dict(),
            "campaign_status": record.status,
            "campaign_key": record.key,
        })

    @_flow
    def upload_resume(self, path: str) -> FlowResult:
        """Parse an existing PDF/DOCX/TXT resume; confidence flags surface
        exactly which fields the parser was unsure about.

        Uploading counts as one resume profile against the free tier."""
        gate = self._gate("resume_profile")
        if gate is not None:
            return gate
        try:
            from engines.career_engine.resume.parser import (
                parse_resume_file,
                parse_text,
            )
            suffix = Path(path).suffix.lower()
            if suffix == ".txt":
                resume, flags = parse_text(Path(path).read_text("utf-8",
                                                                errors="replace"))
            else:
                resume, flags = parse_resume_file(Path(path))
        except Exception as exc:  # noqa: BLE001 — surfaced as input error
            return FlowResult(False, error_kind="input",
                              detail=f"Could not parse that file: {exc}")
        name = unique_artifact_name(
            set(self.storage.list_artifacts("resumes")),
            f"uploaded-{Path(path).stem}.json")
        self.storage.save_artifact("resumes", name, resume)
        self.licenses.consume("resume_profile")
        flag_lines = [f"{f.field}: {f.confidence}" for f in flags]
        logger.info("Resume uploaded (%d confidence flags)", len(flags))
        return FlowResult(True, payload={"resume": resume,
                                         "saved_as": name,
                                         "flags": flag_lines,
                                         "quota": self.licenses.quota(
                                             "resume_profile").as_dict()})

    @_flow
    def import_github_projects(self, username: str,
                               resume: dict[str, Any]) -> FlowResult:
        """Pull public repos into the resume's projects list AND persist
        them in the career identity — the app remembers the account and
        the repos, so re-linking after a restart or an offline day is a
        cache hit, not a fresh import."""
        from engines.career_engine.integrations.github_client import (
            GitHubClient,
        )
        from storage.secrets import load_secret
        username = (username or "").strip()
        if not username:
            raise ValueError("GitHub username must be non-empty")
        identity = self._career_identity()
        try:
            client = GitHubClient(token=load_secret("GITHUB_TOKEN"))
            repos = client.get_user_repos(username, limit=10)
        except OSError as exc:
            # NOTE: urllib raises the BUILTIN ConnectionError (an OSError
            # subclass); the model-layer ConnectionError import shadows
            # that name here, so OSError is the deliberate catch.
            cached = identity.get("github_projects")
            if cached:
                logger.warning("GitHub unreachable; using %d cached "
                               "projects", len(cached))
                updated = {**resume, "projects":
                           resume.get("projects", []) + cached}
                return FlowResult(True, payload={
                    "resume": updated, "imported": len(cached),
                    "cached": True})
            raise ValueError(
                f"GitHub is unreachable right now ({exc}). Connect and "
                "try again — or import later; nothing is lost.") from exc
        except RuntimeError as exc:
            text = str(exc)
            if "404" in text:
                raise ValueError(
                    f"GitHub has no user named {username!r} — check the "
                    "spelling (it is the login name, not your display "
                    "name).") from exc
            if "403" in text or "rate limit" in text.lower():
                raise ValueError(
                    "GitHub rate limit reached (60 requests/hour without "
                    "a token). Add GITHUB_TOKEN=... to secrets/"
                    "github.secrets — create a read-only token at "
                    "github.com/settings/tokens — for 5000/hour.") from exc
            raise ValueError(f"GitHub connection failed: {text}") from exc
        projects = [{
            "name": repo.name,
            "description": repo.description or repo.full_name,
            "tech": ([repo.language] if repo.language else [])
                    + list(repo.topics)[:5],
        } for repo in repos]
        identity.update({
            "github_username": username,
            "github_projects": projects,
            "github_linked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save_career_identity(identity)
        updated = {**resume, "projects":
                   resume.get("projects", []) + projects}
        logger.info("GitHub identity saved: %s (%d projects)",
                    username, len(projects))
        return FlowResult(True, payload={"resume": updated,
                                         "imported": len(projects),
                                         "cached": False})

    @_flow
    def fetch_linkedin_profile(self, resume: dict[str, Any]) -> FlowResult:
        """Connect LinkedIn: read the user's own basic profile, fill the
        resume contact fields, and REMEMBER the connection in the career
        identity so it survives restarts."""
        from engines.career_engine.integrations.linkedin_client import (
            LinkedInClient,
        )
        from storage.secrets import load_secret
        token = load_secret("LINKEDIN_TOKEN")
        client = LinkedInClient(token=token)
        if not client.is_authenticated:
            cached = self._career_identity().get("linkedin")
            if cached:
                contact = {**resume.get("contact", {})}
                if cached.get("name") and not contact.get("name"):
                    contact["name"] = cached["name"]
                if cached.get("email") and not contact.get("email"):
                    contact["email"] = cached["email"]
                return FlowResult(True, payload={
                    "resume": {**resume, "contact": contact},
                    "who": cached.get("name") or "(cached LinkedIn)",
                    "cached": True})
            raise ValueError(
                "No LinkedIn token found. Create a token with the "
                "'Sign In with LinkedIn using OpenID Connect' product "
                "(linkedin.com/developers) and add LINKEDIN_TOKEN=<access "
                "token> to secrets/linkedin.secrets, then restart the "
                "app. Without it, LinkedIn stays disconnected — "
                "everything else keeps working.")
        try:
            profile = client.get_profile()
        except RuntimeError as exc:
            raise ValueError(f"LinkedIn rejected the token: {exc} "
                            "Refresh LINKEDIN_TOKEN in secrets/"
                            "linkedin.secrets and retry.") from exc
        except OSError as exc:
            # urllib's builtin ConnectionError is an OSError subclass
            raise ValueError(f"LinkedIn is unreachable right now ({exc}). "
                            "Try again later.") from exc
        contact = {**resume.get("contact", {})}
        if profile.name and not contact.get("name"):
            contact["name"] = profile.name
        if profile.email and not contact.get("email"):
            contact["email"] = profile.email
        identity = self._career_identity()
        identity["linkedin"] = {
            "name": profile.name, "email": profile.email,
            "sub": profile.sub,
            "linked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._save_career_identity(identity)
        who = profile.name or "(LinkedIn account)"
        logger.info("LinkedIn identity saved: %s", who)
        return FlowResult(True, payload={"resume": {**resume,
                                                    "contact": contact},
                                         "who": who, "cached": False})

    # -- journeys -----------------------------------------------------------

    @_flow
    def generate_resume(self, profile: str) -> FlowResult:
        from engines.career_engine.resume.generator import (
            generate as run_generate,
        )
        profile = (profile or "").strip()
        if not profile:
            raise ValueError("Profile must be non-empty")
        # Free tier: one resume profile (PROFIT_PLAN §2). Enhancing and
        # exporting that profile is always free — the cap is on profiles,
        # not on the work done with them.
        gate = self._gate("resume_profile")
        if gate is not None:
            return gate
        resume = run_generate(profile, client=self.client, model=self.model)
        slug = self._slug(profile[:60], "resume")
        self.storage.save_artifact("resumes", f"{slug}.json", resume)
        self.licenses.consume("resume_profile")
        logger.info("Resume generated and saved as %s.json", slug)
        return FlowResult(True, payload={"resume": resume,
                                         "saved_as": f"{slug}.json",
                                         "quota": self.licenses.quota(
                                             "resume_profile").as_dict()})

    @_flow
    def enhance_resume(self, resume: dict[str, Any],
                       target_role: str) -> FlowResult:
        """Rewrite toward a target role; the human-inspectable changes
        list always accompanies the artifact (CONSTITUTION §3). The
        target role is remembered in the career identity."""
        from engines.career_engine.resume.generator import (
            enhance as run_enhance,
        )
        role = (target_role or "").strip()
        if not role:
            raise ValueError("Target role must be non-empty")
        if not isinstance(resume, dict) or not resume:
            raise ValueError("Generate or load a resume first")
        result = run_enhance(resume, role, client=self.client,
                             model=self.model)
        enhanced = result["enhanced_resume"]
        changes = result.get("changes") or []
        identity = self._career_identity()
        identity["target_role"] = role
        identity["target_role_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_career_identity(identity)
        name = unique_artifact_name(
            set(self.storage.list_artifacts("resumes")),
            f"{self._slug(role[:40], 'resume')}-enhanced.json")
        self.storage.save_artifact("resumes", name, enhanced)
        logger.info("Resume enhanced for %s -> %s (%d changes)",
                    role[:40], name, len(changes))
        return FlowResult(True, payload={"resume": enhanced,
                                         "changes": changes,
                                         "saved_as": name})

    @_flow
    def draft_linkedin_post(self, resume: dict[str, Any],
                            goal: str) -> FlowResult:
        """Draft a human-sounding LinkedIn post grounded in the resume.
        The draft is SAVED locally — publishing is a separate,
        explicitly-confirmed flow (linkedInin_post_publish).

        Free tier gets one draft to try it (PROFIT_PLAN §2 puts the post
        studio in Pro); publishing anything you can write stays free and
        unmetered — we never meter a user's own voice."""
        from engines.career_engine.resume.generator import (
            generate_linkedin_post,
        )
        if not isinstance(resume, dict) or not resume:
            raise ValueError("Generate or load a resume first")
        gate = self._gate("linkedin_post")
        if gate is not None:
            return gate
        goal = (goal or "").strip()
        if not goal:
            raise ValueError("Describe what the post should achieve "
                             "(e.g. 'announce I am looking for senior "
                             "support roles')")
        draft = generate_linkedin_post(resume, goal=goal,
                                       client=self.client,
                                       model=self.model)
        name = unique_artifact_name(
            set(self.storage.list_artifacts("linkedin_posts")),
            f"{self._slug(goal, 'post')}.json")
        self.storage.save_artifact("linkedin_posts", name, draft)
        self.licenses.consume("linkedin_post")
        logger.info("LinkedIn post draft saved as %s", name)
        return FlowResult(True, payload={
            "draft": draft, "saved_as": name,
            "quota": self.licenses.quota("linkedin_post").as_dict()})

    @_flow
    def publish_linkedin_post(self, post_text: str,
                              confirm: bool = False) -> FlowResult:
        """Publish a reviewed post to the user's OWN LinkedIn profile.
        Requires the human's explicit confirm — there is no code path
        where a post fires without it (safety gate from the client)."""
        from engines.career_engine.integrations.linkedin_client import (
            LinkedInClient,
        )
        from storage.secrets import load_secret
        if not confirm:
            raise ValueError("Publishing requires an explicit review + "
                             "confirm step — drafts never auto-post.")
        token = load_secret("LINKEDIN_TOKEN")
        if not token:
            raise ValueError(
                "No LINKEDIN_TOKEN in secrets/linkedin.secrets — the "
                "draft is saved locally; add a token to publish.")
        client = LinkedInClient(token=token)
        try:
            result = client.post_to_profile((post_text or "").strip(),
                                            confirm=True)
        except (RuntimeError, OSError) as exc:
            raise ValueError(f"LinkedIn rejected the post: {exc}") from exc
        logger.info("LinkedIn post published: %s", result.get("id"))
        return FlowResult(True, payload={"post_id": result.get("id")})

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
                             known_language: str, level: str, *,
                             num_dialogue: Optional[int] = None,
                             num_vocab: Optional[int] = None,
                             num_grammar: Optional[int] = None,
                             num_eval: Optional[int] = None
                             ) -> FlowResult:
        """One guardrailed generation -> validated pack -> interactive
        HTML saved under exports. Returns the file path for the UI to
        open in a browser.

        Free tier: 3 packs per ISO week (PROFIT_PLAN §2). The gate runs
        before generation — a CPU model can spend minutes on a pack, and
        nobody should discover a quota at the end of that."""
        from engines.language_lab.lesson_pack import generate_lesson_pack as run_generation
        from engines.language_lab.renderer import render_lesson_pack_html

        topic = topic.strip()
        if not topic:
            raise ValueError("Topic must be non-empty")
        gate = self._gate("lesson_pack")
        if gate is not None:
            return gate
        pack = run_generation(
            topic, target_language.strip().lower(),
            known_language.strip().lower(), level.strip().lower(),
            client=self.client, model=self.model,
            **{k: v for k, v in {
                "num_dialogue": num_dialogue, "num_vocab": num_vocab,
                "num_grammar": num_grammar, "num_eval": num_eval,
            }.items() if v is not None},
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
        except Exception as exc:  # noqa: BLE001 — the audit is optional
            # A fidelity audit is a NICE-TO-HAVE artifact next to a pack
            # that already passed validation. Any failure here (model
            # drift, a proxy client without the full interface, TTS
            # environment gaps) must downgrade the audit, never the
            # flagship output the user waited minutes for.
            logger.warning("Pack fidelity audit skipped: %s", exc)

        # per-segment audio: EMBEDDED into the HTML as data URIs so no
        # browser file:// policy or moved file can silence it; disk WAVs
        # are also written next to the HTML (P7.5 artifact contract).
        audio_files: dict[str, str] = {}
        try:
            import base64
            from engines.language_lab.pack_audio import render_pack_audio
            exports_dir = Path(self.storage.root) / "exports"
            segments = render_pack_audio(
                pack, stem=base, output_path=str(exports_dir))
            for seg in segments:
                data_uri = ("data:audio/wav;base64,"
                            + base64.b64encode(seg.wav_bytes).decode())
                audio_files[seg.key] = data_uri
        except (RuntimeError, FileNotFoundError) as exc:
            logger.warning("Pack audio skipped (%s); shipping silent pack",
                           exc)

        path = self.storage.save_artifact(
            "exports", f"{base}.html",
            render_lesson_pack_html(pack, audio_files=audio_files or None))
        self.licenses.consume("lesson_pack")
        quota = self.licenses.quota("lesson_pack")
        logger.info("Lesson pack rendered -> %s (%d audio segments)",
                    path, len(audio_files))
        return FlowResult(True, payload={"path": str(path),
                                         "pack": f"{base}.json",
                                         "quota": quota.as_dict()})

    @_flow
    def share_lesson_pack(self, pack_name: str, destination: Optional[str] = None,
                          brand: str = "", brand_url: str = "",
                          note: str = "") -> FlowResult:
        """Write a shareable, self-contained copy of a saved pack.

        The growth loop (PROFIT_PLAN §3.1): every shared pack is a
        landing page — it carries the app credit, an optional sponsor
        brand line, and a one-click save/share button. Sharing is free
        on every tier; gating the loop would kill the funnel.

        When an already-rendered export exists, it is reused (it holds
        the dialogue audio as embedded data URIs); the footer is then
        attached in place so the audio survives.
        """
        from engines.language_lab.renderer import (
            PackFooter, attach_pack_footer, render_lesson_pack_html,
        )

        name = (pack_name or "").strip()
        if not name:
            raise ValueError("Choose a saved pack first")
        pack = self.storage.load_artifact("lesson_packs", name)
        if not isinstance(pack, dict):
            raise ValueError(f"{name} is not a lesson pack")

        footer = PackFooter(brand=brand, brand_url=brand_url, note=note)
        stem = name.rsplit(".", 1)[0]
        rendered = self.storage.root / "exports" / f"{stem}.html"
        if rendered.exists():
            document = attach_pack_footer(rendered.read_text(encoding="utf-8"),
                                          footer)
        else:  # pack JSON without an HTML export — render a silent copy
            logger.warning("No HTML export for %s; sharing without audio", name)
            document = render_lesson_pack_html(pack, footer=footer)

        target = (Path(destination) if destination
                  else self.storage.root / "exports" / f"share-{stem}.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        logger.info("Shareable pack written -> %s (%d bytes)", target,
                    len(document))
        return FlowResult(True, payload={"path": str(target),
                                         "bytes": len(document.encode("utf-8")),
                                         "brand": footer.brand})

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
