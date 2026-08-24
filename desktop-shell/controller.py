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
from typing import Any, Optional

from model_layer.client import ApiError, ConnectionError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL
from model_layer.schema import SchemaValidationError
from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.client = client if client is not None else LmStudioClient()
        self.storage = storage if storage is not None else default_storage()
        self.model = model

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
