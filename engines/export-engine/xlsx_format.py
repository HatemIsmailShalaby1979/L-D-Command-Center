# engines/export-engine/xlsx_format.py
#
# WHAT: Deterministic XLSX renderer for Journeys — one worksheet with a
#       metadata header and one row per Card.
# WHY:  MASTER_STORY promises XLSX among the export formats (P4.3).
#       Workbook properties are pinned so identical input yields
#       byte-identical output (exit criterion E4).
# BREAKS IF DELETED: Journeys can no longer be exported to spreadsheets.

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

_EPOCH = datetime(2000, 1, 1)


def export_journey_to_xlsx(journey: dict[str, Any]) -> bytes:
    """
    Contract: render a validated Journey dict to XLSX bytes.

    Sheet layout: topic/level rows, blank spacer, then a header row and
    one row per card (id, title, content, question, options joined with
    newlines, correct option, explanation).

    Raises:
        ValueError: missing topic/cards.
        ImportError: openpyxl not installed.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "xlsx export requires openpyxl: pip install openpyxl"
        ) from exc

    topic = journey.get("topic")
    level = journey.get("level", "beginner")
    cards = journey.get("cards", [])
    if not topic:
        raise ValueError("Journey must have a 'topic' field")
    if not cards:
        raise ValueError("Journey must contain at least one card")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Journey"

    ws.append(["Topic", topic])
    ws.append(["Level", level])
    ws.append([])
    ws.append(["#", "id", "Title", "Content", "Quiz",
               "Options", "Correct", "Explanation"])
    for i, card in enumerate(cards, start=1):
        ws.append([
            i,
            card.get("id", str(i)),
            card.get("title", ""),
            card.get("content", ""),
            card.get("question", ""),
            "\n".join(card.get("options", [])),
            str(card.get("correct_option", "")),
            card.get("explanation", ""),
        ])

    props = wb.properties
    props.creator = "L&D Command Center"
    props.created = _EPOCH
    props.modified = _EPOCH
    props.title = topic

    buf = BytesIO()
    wb.save(buf)
    logger.info("Rendered XLSX export for %r (%d cards)", topic, len(cards))
    return buf.getvalue()
