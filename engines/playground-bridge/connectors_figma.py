# engines/playground-bridge/connectors_figma.py
#
# WHAT: Figma REST adapter — import designs/frames as PNG or SVG assets
#       using a free-account personal access token (P7.10).
# WHY:  Plan B3 v1 roster, auth "account". Design assets become first-
#       class Playground media without any paid plan: list frames from a
#       file, export one node per job, bytes land in the standard Result.
#       Transport is injectable; the token comes only from the secrets
#       seam (CONSTITUTION §3) and its absence is a failed job, not an
#       exception.
# BREAKS IF DELETED: The connector roster loses its design-import path.

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import httpx

from engines.playground_bridge.connectors_hub import (
    Capabilities,
    Capability,
    Connector,
    InputArtifact,
    Job,
    Result,
    new_job_id,
)
from storage.secrets import load_secret

logger = logging.getLogger(__name__)

__all__ = ["FigmaConnector", "FIGMA_TOKEN_NAME"]

FIGMA_TOKEN_NAME = "FIGMA_TOKEN"
DEFAULT_BASE_URL = "https://api.figma.com/v1"

Transport = Callable[..., Any]  # (method, url, headers=..., params=...) -> response


def _default_transport(method: str, url: str, *,
                       headers: dict[str, str],
                       params: Optional[dict[str, str]] = None) -> Any:
    return httpx.request(method, url, headers=headers, params=params,
                         timeout=60)


class FigmaConnector(Connector):
    """Contract: one Figma file node exported per job.

    send(op) expects op = {
        "file_key": str,
        "node_id": str,            # single node; UI loops for more
        "format": "png" | "svg",   # default png
        "scale": float,            # png only, default 1.0
    }

    list_frames(file_key) walks page->top-level frames so users can pick
    node ids without leaving the app. All failures — missing token, bad
    key, private file — arrive as failed Jobs with actionable messages.
    """

    name = "figma"

    def __init__(
        self,
        *,
        token_provider: Optional[Callable[[], Optional[str]]] = None,
        transport: Optional[Transport] = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._token_provider = token_provider or self._secrets_token
        self._transport = transport or _default_transport
        self._base_url = base_url.rstrip("/")
        self._results: dict[str, Result] = {}

    @staticmethod
    def _secrets_token() -> Optional[str]:
        return load_secret(FIGMA_TOKEN_NAME)

    # -- seam -------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(self.name, "account", (
            Capability(
                "design",
                "Import Figma frames/designs as PNG or SVG assets",
                "Free account token required; export API is rate-limited "
                "but generous for personal use"),
        ), file_types=("png", "svg"), ops=("export_frame",))

    def send(self, artifact: Optional[InputArtifact],
             op: dict[str, Any]) -> Job:
        # Figma's own semantics export FROM the user's file; an inbound
        # artifact is meaningless here and intentionally ignored.
        job_id = new_job_id()
        token = self._token_provider() or ""
        if not token:
            return self._fail(
                job_id, "no FIGMA_TOKEN configured — add it to a secrets "
                        "*.secrets file (free account at figma.com)")

        file_key = str(op.get("file_key", "")).strip()
        node_id = str(op.get("node_id", "")).strip()
        fmt = str(op.get("format", "png")).lower()
        if not file_key or not node_id:
            return self._fail(job_id,
                              "send() needs 'file_key' and 'node_id'")
        if fmt not in ("png", "svg"):
            return self._fail(job_id, f"unsupported format {fmt!r} "
                                      "(png or svg)")
        try:
            params: dict[str, Any] = {"ids": node_id, "format": fmt}
            if fmt == "png":
                params["scale"] = float(op.get("scale", 1.0))
            response = self._transport(
                "GET", f"{self._base_url}/images/{file_key}",
                headers=self._headers(token), params=params)
            if response.status_code != 200:
                return self._fail(job_id, f"Figma API returned HTTP "
                                          f"{response.status_code}")
            urls = response.json().get("images", {})
            media_url = urls.get(node_id)
            if not media_url:
                return self._fail(job_id,
                                  f"node {node_id!r} not found or not "
                                  "exportable in this file")
            media_response = self._transport("GET", media_url,
                                             headers={}, params=None)
            if media_response.status_code != 200:
                return self._fail(job_id,
                                  "asset download failed with HTTP "
                                  f"{media_response.status_code}")
            media_bytes = media_response.content
        except Exception as exc:  # noqa: BLE001 — failures are data here
            logger.warning("Figma job %s failed: %s", job_id, exc)
            return self._fail(job_id, f"{type(exc).__name__}: {exc}")

        self._results[job_id] = Result(job_id, True, media_bytes=media_bytes)
        logger.info("Figma export done (%d bytes, %s)", len(media_bytes), fmt)
        return Job(job_id, self.name, "done")

    def poll(self, job: Job) -> Result:
        result = self._results.pop(job.id, None)
        if result is None:
            return Result(job.id, False,
                          error=f"unknown or already-polled job {job.id}")
        return result

    # -- discovery ----------------------------------------------------------

    def list_frames(self, file_key: str) -> list[dict[str, str]]:
        """Top-level frames per page: [{"id","name","page"}]. Raises on
        transport errors — this is an interactive picker call."""
        token = self._token_provider() or ""
        if not token:
            raise ValueError(f"no {FIGMA_TOKEN_NAME} configured")
        response = self._transport(
            "GET", f"{self._base_url}/files/{file_key}?depth=2",
            headers=self._headers(token))
        if response.status_code != 200:
            raise ValueError(f"Figma API returned HTTP "
                             f"{response.status_code} for that file key")
        document = response.json().get("document", {})
        frames: list[dict[str, str]] = []
        for page in document.get("children", []):
            for child in page.get("children", []):
                if child.get("type") == "FRAME":
                    frames.append({"id": child["id"],
                                   "name": child.get("name", ""),
                                   "page": page.get("name", "")})
        return frames

    # -- internals ----------------------------------------------------------

    def _headers(self, token: str) -> dict[str, str]:
        return {"X-Figma-Token": token}

    def _fail(self, job_id: str, message: str) -> Job:
        self._results[job_id] = Result(job_id, False, error=message)
        return Job(job_id, self.name, "failed")


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload
