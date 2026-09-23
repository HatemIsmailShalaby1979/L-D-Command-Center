# engines/playground-bridge/connectors_hub.py
#
# WHAT: The Connector Hub seam — ONE adapter interface (capabilities/
#       send/poll) plus a registry, per Plan B0 principle 3 ("one seam,
#       N services"). The Hub never learns about individual vendors;
#       adapters never learn about each other.
# WHY:  Free-tier/keyless generation is the Playground's reach model.
#       Without one seam every UI panel and export flow would special-
#       case vendors; with it, adding Pollinations/Figma/HF Spaces is a
#       file drop and a register call.
# BREAKS IF DELETED: Vendor knowledge leaks into shell UI and engines;
#       quota/auth notes stop being inspectable in one place.

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "Capability", "Capabilities", "InputArtifact", "Job", "Result",
    "Connector", "ConnectorHub",
]


@dataclass(frozen=True)
class Capability:
    """One thing a connector can do, with the free-tier honesty note
    the UI must surface."""
    kind: str            # "image" | "audio" | "video" | "upscale" | ...
    description: str
    quota_note: str


@dataclass(frozen=True)
class Capabilities:
    connector: str
    auth: str            # "none" | "account" | "token"
    items: tuple[Capability, ...]
    # Plan B3 contract fields: what media the connector accepts and what
    # operations it exposes, so the UI never offers impossible flows.
    file_types: tuple[str, ...] = ()   # e.g. ("png", "wav", "mp4")
    ops: tuple[str, ...] = ()          # e.g. ("text_to_image", "upscale")


@dataclass(frozen=True)
class InputArtifact:
    """Media handed TO a connector when the operation consumes inputs
    (image-to-image, upscale, remix). None for pure prompt generators."""
    name: str
    data: bytes
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class Job:
    id: str
    connector: str
    status: str          # "queued" | "running" | "done" | "failed"


@dataclass(frozen=True)
class Result:
    job_id: str
    ok: bool
    media_bytes: Optional[bytes] = None
    error: Optional[str] = None


class Connector(ABC):
    """Contract: one external service adapter.

    send(artifact, op) submits a generation request and returns a Job
    immediately; synchronous backends finish inside send and hold their
    result until polled. `artifact` carries INPUT media for operations
    that consume it (image-to-image, upscale); adapters that cannot use
    one MUST fail the job with an actionable message instead of silently
    ignoring it — except where the service's own semantics make the
    artifact meaningless (e.g. Figma exports FROM its own files).
    poll() resolves any Job to exactly one Result — success carries
    media bytes, failure carries an actionable message. Adapters must
    not raise past poll(); failures are data, so the UI can show them
    as quota notes.
    """
    name: str = ""

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def send(self, artifact: Optional[InputArtifact],
             op: dict[str, Any]) -> Job: ...

    @abstractmethod
    def poll(self, job: Job) -> Result: ...


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


class ConnectorHub:
    """Contract: registry + uniform access for the shell UI."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        name = getattr(connector, "name", "")
        if not name:
            raise ValueError("connector must define a non-empty name")
        if name in self._connectors:
            raise ValueError(f"connector {name!r} already registered")
        self._connectors[name] = connector
        logger.info("Registered connector: %s", name)

    def names(self) -> list[str]:
        return sorted(self._connectors)

    def get(self, name: str) -> Connector:
        if name not in self._connectors:
            raise KeyError(
                f"Unknown connector {name!r}; available: {self.names()}")
        return self._connectors[name]

    def all_capabilities(self) -> list[Capabilities]:
        return [c.capabilities() for c in
                (self._connectors[n] for n in self.names())]
