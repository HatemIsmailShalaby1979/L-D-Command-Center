# engines/playground-bridge/connectors_pollinations.py
#
# WHAT: Keyless Pollinations image-generation adapter — plain GET with
#       the prompt in the path, zero accounts, zero keys (P7.11).
# WHY:  Plan B0 principle 1 ("keyless before keys"): this is the lowest-
#       friction generation path in the roster. One HTTP GET returns the
#       image bytes; failures are data on the standard Job/Result seam.
#       Transport injectable so tests never touch the network.
# BREAKS IF DELETED: The roster loses its zero-account image generator.

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from urllib.parse import quote_plus

import httpx

from engines.playground_bridge.connectors_hub import (
    Capabilities,
    Capability,
    Connector,
    Job,
    Result,
    new_job_id,
)

logger = logging.getLogger(__name__)

__all__ = ["PollinationsConnector"]

DEFAULT_BASE_URL = "https://image.pollinations.ai"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024

Transport = Callable[..., Any]


def _default_transport(method: str, url: str) -> Any:
    return httpx.request(method, url, timeout=120)


class PollinationsConnector(Connector):
    """
    Contract: send(op) expects op = {
        "prompt": str (required),
        "width": int (default 1024), "height": int (default 1024),
        "seed": int (optional — omit for random),
        "model": str (optional, e.g. "flux"),
        "nologo": bool (default True),
    } and returns the raw image bytes via poll().
    """

    name = "pollinations"

    def __init__(self, *,
                 transport: Optional[Transport] = None,
                 base_url: str = DEFAULT_BASE_URL) -> None:
        self._transport = transport or _default_transport
        self._base_url = base_url.rstrip("/")
        self._results: dict[str, Result] = {}

    # -- seam -------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(self.name, "none", (
            Capability(
                "image",
                "Keyless text-to-image generation",
                "No account at all; prompts are public and queued "
                "best-effort — retry if it times out"),
        ))

    def send(self, op: dict[str, Any]) -> Job:
        job_id = new_job_id()
        prompt = str(op.get("prompt", "")).strip()
        if not prompt:
            return self._fail(job_id,
                              "send() needs a non-empty 'prompt'")
        width = int(op.get("width", DEFAULT_WIDTH))
        height = int(op.get("height", DEFAULT_HEIGHT))
        query = f"width={width}&height={height}&nologo=true"
        if op.get("model"):
            query += f"&model={quote_plus(str(op['model']))}"
        if op.get("seed") is not None:
            query += f"&seed={int(op['seed'])}"
        url = f"{self._base_url}/prompt/{quote_plus(prompt)}?{query}"
        try:
            response = self._transport("GET", url)
            status = getattr(response, "status_code", 0)
            if status != 200:
                return self._fail(job_id,
                                  f"Pollinations returned HTTP {status}")
            content = response.content
            media_type = str(getattr(response, "headers", {})
                             .get("content-type", ""))
            if not content:
                return self._fail(job_id, "empty response body")
            if media_type and not media_type.startswith("image/"):
                return self._fail(
                    job_id,
                    f"unexpected content-type {media_type!r} — service "
                    "may be rate-limiting or erroring in-band")
        except Exception as exc:  # noqa: BLE001 — failures are data here
            logger.warning("Pollinations job %s failed: %s", job_id, exc)
            return self._fail(job_id, f"{type(exc).__name__}: {exc}")
        self._results[job_id] = Result(job_id, True, media_bytes=content)
        logger.info("Pollinations image ready (%d bytes)", len(content))
        return Job(job_id, self.name, "done")

    def poll(self, job: Job) -> Result:
        result = self._results.pop(job.id, None)
        if result is None:
            return Result(job.id, False,
                          error=f"unknown or already-polled job {job.id}")
        return result

    def _fail(self, job_id: str, message: str) -> Job:
        self._results[job_id] = Result(job_id, False, error=message)
        return Job(job_id, self.name, "failed")


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "image/png"}
