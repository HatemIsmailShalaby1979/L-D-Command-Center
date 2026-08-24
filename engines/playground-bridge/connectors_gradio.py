# engines/playground-bridge/connectors_gradio.py
#
# WHAT: Keyless Hugging Face Spaces adapter over gradio_client — the
#       Hub's biggest unlock (thousands of Spaces: image gen, music,
#       video, upscalers, TTS) with zero accounts (P7.9).
# WHY:  Plan B3 v1 roster, auth "none". Space churn is a known risk
#       (plan §Risks): Space ids are pinned constants and every failure
#       mode — missing library, dead Space, unexpected output shape —
#       becomes a FAILED JOB with a readable message, never an exception
#       past poll(). Tests inject a client factory; gradio_client is
#       never imported at module load.
# BREAKS IF DELETED: The Playground loses its keyless generation roster.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from engines.playground_bridge.connectors_hub import (
    Capabilities,
    Capability,
    Connector,
    Job,
    Result,
    new_job_id,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GradioSpaceConnector",
    "IMAGE_SPACE",
    "MUSIC_SPACE",
    "UPSCALER_SPACE_PLACEHOLDER",
]

# Pinned v1 roster (plan §Risks: churn -> pin + fail-soft).
IMAGE_SPACE = "black-forest-labs/FLUX.1-schnell"
MUSIC_SPACE = "ACE-Step/ACE-Step-v1-3.5B"
UPSCALER_SPACE_PLACEHOLDER = ""  # no upscaler pinned yet; hidden from capabilities

ClientFactory = Callable[[str], Any]


def _default_client_factory(space_id: str) -> Any:
    """Lazy import so gradio_client stays optional."""
    from gradio_client import Client  # noqa: deferred by design
    return Client(space_id)


class GradioSpaceConnector(Connector):
    """
    Contract: one pinned Space exposed as one capability. send(op)
    expects op = {"prompt": str, **extra params}; the call is
    synchronous, so send() returns a terminal Job and holds the bytes
    for poll().
    """

    def __init__(
        self,
        *,
        name: str,
        space_id: str,
        kind: str,
        description: str,
        quota_note: str,
        fn_name: str = "/infer",
        extra_params: Optional[dict[str, Any]] = None,
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        self.name = name
        self._space_id = space_id
        self._kind = kind
        self._description = description
        self._quota_note = quota_note
        self._fn_name = fn_name
        self._extra_params = dict(extra_params or {})
        self._factory: ClientFactory = (
            client_factory if client_factory is not None
            else _default_client_factory)
        self._results: dict[str, Result] = {}

    # -- seam -------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        if not self._space_id:
            return Capabilities(self.name, "none", ())
        return Capabilities(self.name, "none", (
            Capability(self._kind, self._description, self._quota_note),
        ))

    def send(self, op: dict[str, Any]) -> Job:
        job_id = new_job_id()
        prompt = str(op.get("prompt", "")).strip()
        if not prompt:
            return self._fail(job_id, "send() needs a non-empty 'prompt'")
        try:
            client = self._factory(self._space_id)
            output = client.predict(
                prompt=prompt, **{**self._extra_params,
                                  **{k: v for k, v in op.items()
                                     if k != "prompt"}},
                api_name=self._fn_name,
            )
            media_path = _extract_file(output)
            if media_path is None:
                return self._fail(
                    job_id,
                    f"Space returned {type(output).__name__}, expected a "
                    "media file — the Space's output contract changed.")
            media_bytes = Path(media_path).read_bytes()
        except Exception as exc:  # noqa: BLE001 — failures are data here
            logger.warning("Gradio connector %s failed: %s", self.name, exc)
            return self._fail(job_id, f"{type(exc).__name__}: {exc}")
        result = Result(job_id, True, media_bytes=media_bytes)
        self._results[job_id] = result
        logger.info("Gradio job %s done (%d bytes)", job_id, len(media_bytes))
        return Job(job_id, self.name, "done")

    def poll(self, job: Job) -> Result:
        result = self._results.pop(job.id, None)
        if result is None:
            return Result(job.id, False,
                          error=f"unknown or already-polled job {job.id}")
        return result

    # -- internals ----------------------------------------------------------

    def _fail(self, job_id: str, message: str) -> Job:
        self._results[job_id] = Result(job_id, False, error=message)
        return Job(job_id, self.name, "failed")


def _extract_file(output: Any) -> Optional[Path]:
    """Pull one file path out of gradio's many output shapes."""
    if isinstance(output, (str, Path)):
        candidate = Path(output)
        return candidate if candidate.is_file() else None
    if isinstance(output, dict):
        for value in output.values():
            found = _extract_file(value)
            if found is not None:
                return found
        return None
    if isinstance(output, (list, tuple)):
        for value in output:
            found = _extract_file(value)
            if found is not None:
                return found
    return None


def default_image_connector(**kwargs) -> GradioSpaceConnector:
    kwargs.setdefault("name", "hf-flux-schnell")
    kwargs.setdefault("space_id", IMAGE_SPACE)
    kwargs.setdefault("kind", "image")
    kwargs.setdefault("description",
                      "Keyless text-to-image via FLUX.1-schnell on HF Spaces")
    kwargs.setdefault("quota_note",
                      "Free GPU quota per IP; busy queues possible")
    return GradioSpaceConnector(**kwargs)


def default_music_connector(**kwargs) -> GradioSpaceConnector:
    kwargs.setdefault("name", "hf-ace-step-music")
    kwargs.setdefault("space_id", MUSIC_SPACE)
    kwargs.setdefault("kind", "audio")
    kwargs.setdefault("description",
                      "Keyless music generation via ACE-Step on HF Spaces")
    kwargs.setdefault("quota_note",
                      "Zero-account; long generations may time out")
    return GradioSpaceConnector(**kwargs)
