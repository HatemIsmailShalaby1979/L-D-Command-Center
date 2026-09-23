# engines/export-engine/zip_stability.py
#
# WHAT: One stabilizer for every OOXML (ZIP) export — XLSX, PPTX, DOCX.
# WHY:  Exit criterion E4 (deterministic exports): exporting the SAME
#       artifact twice must yield IDENTICAL bytes, or caching/dedup/hashing
#       downstream silently breaks. Two independent sources of
#       non-determinism survive even when an adapter pins core properties:
#
#         1. ZIP member timestamps — every library stamps members with the
#            wall clock at save time.
#         2. docProps/core.xml timestamps — openpyxl (among others) writes
#            <dcterms:modified> as the wall clock regardless of what the
#            caller assigned to properties.modified beforehand.
#
#       (1) alone makes exports differ; (2) alone does too. Both were
#       observed in production runs: XLSX drifted on core.xml, PPTX drifted
#       on member timestamps, and the byte-stability test failed roughly
#       1 run in 8 purely on whether the two exports straddled a second
#       boundary.
#
# BREAKS IF DELETED: exports stop being reproducible and
#       test_byte_stability.py becomes a flaky gate.

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

_EPOCH = datetime(2000, 1, 1)
_EPOCH_STAMP = b"2000-01-01T00:00:00Z"

# Matches <dcterms:created ...>VALUE</dcterms:created> (and :modified).
_DCTERMS_RE = re.compile(
    rb"(<dcterms:(?:created|modified)\b[^>]*>)(.*?)"
    rb"(</dcterms:(?:created|modified)>)",
    re.DOTALL,
)


def pin_core_timestamps(data: bytes) -> bytes:
    """Rewrite every dcterms created/modified value to the pinned epoch."""
    return _DCTERMS_RE.sub(
        lambda m: m.group(1) + _EPOCH_STAMP + m.group(3), data
    )


def stabilize_zip(payload: bytes) -> bytes:
    """Re-emit an OOXML package with wall-clock metadata removed.

    Preserves each member's compression and attributes; only the
    non-deterministic parts (member timestamps, core.xml timestamps) change.
    """
    source = ZipFile(BytesIO(payload), "r")
    out = BytesIO()
    with source, ZipFile(out, "w", compression=ZIP_DEFLATED) as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename.endswith("core.xml"):
                data = pin_core_timestamps(data)
            normalized = ZipInfo(
                entry.filename,
                date_time=(_EPOCH.year, _EPOCH.month, _EPOCH.day, 0, 0, 0),
            )
            normalized.compress_type = entry.compress_type
            normalized.create_system = entry.create_system
            normalized.external_attr = entry.external_attr
            normalized.flag_bits = entry.flag_bits
            normalized.comment = entry.comment
            target.writestr(normalized, data)
    return out.getvalue()
