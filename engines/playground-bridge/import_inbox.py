# engines/playground-bridge/import_inbox.py
#
# WHAT: The Import Inbox — a watch-folder that turns dropped files from
#       ANY no-API service (Suno/Udio/Runway web exports, phone record-
#       ings, anything) into storage artifacts under media/<subkind>
#       (P7.8).
# WHY:  Plan B2: "This single feature makes 'any service with a free
#       quota' true even where APIs don't exist." Scanning is a pure
#       one-shot function so the shell can drive it from a timer (and
#       tests can drive it deterministically); no background threads,
#       no filesystem watchers to leak.
# BREAKS IF DELETED: Drag-and-drop citizenship for web-tier services
#       disappears; the Playground only reaches what its adapters reach.

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from storage.persistence import Storage

logger = logging.getLogger(__name__)

__all__ = ["ImportRecord", "scan_inbox", "DEFAULT_MEDIA_SUBKIND",
           "unique_artifact_name"]

DEFAULT_MEDIA_SUBKIND = "inbox"


@dataclass(frozen=True)
class ImportRecord:
    source_name: str
    artifact_kind: str
    artifact_name: Optional[str]
    size_bytes: int
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def unique_artifact_name(kind_dir_files: set[str], name: str) -> str:
    """Collision-safe name inside one kind dir: song.wav, song-1.wav…"""
    if name not in kind_dir_files:
        return name
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    counter = 1
    while True:
        candidate = f"{stem}-{counter}{('.' + suffix) if suffix else ''}"
        if candidate not in kind_dir_files:
            return candidate
        counter += 1


def scan_inbox(
    inbox_path: str | Path,
    storage: Storage,
    *,
    media_subkind: str = DEFAULT_MEDIA_SUBKIND,
    allowed_extensions: Optional[list[str]] = None,
    delete_after: bool = True,
) -> list[ImportRecord]:
    """
    Contract: process every file currently sitting in the inbox folder.

    - Non-recursive; directories are ignored.
    - allowed_extensions filters by suffix (case-insensitive, with dot);
      None accepts everything. Rejected files stay untouched.
    - Imported bytes land under storage kind "media/<media_subkind>"
      under a collision-safe name.
    - delete_after removes the source on success (watch-folder
      semantics). Failures leave the source in place and are reported
      per-file — never raised past the caller.

    Returns:
        One ImportRecord per considered file.
    """
    inbox = Path(inbox_path)
    if not inbox.is_dir():
        logger.info("Import inbox %s absent — nothing to scan", inbox)
        return []

    wanted = None
    if allowed_extensions is not None:
        wanted = {ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                  for ext in allowed_extensions}

    existing = set(storage.list_artifacts(f"media/{media_subkind}"))
    records: list[ImportRecord] = []
    kind = f"media/{media_subkind}"

    for entry in sorted(inbox.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        if wanted is not None and entry.suffix.lower() not in wanted:
            records.append(ImportRecord(entry.name, kind, None,
                                        entry.stat().st_size,
                                        error="extension not accepted"))
            continue
        try:
            data = entry.read_bytes()
            name = unique_artifact_name(existing, entry.name)
            storage.save_artifact(kind, name, data)
            existing.add(name)
            if delete_after:
                entry.unlink()
            records.append(ImportRecord(entry.name, kind, name,
                                        len(data)))
            logger.info("Inbox import %s -> %s/%s (%d bytes)",
                        entry.name, kind, name, len(data))
        except (OSError, ValueError) as exc:
            # Storage refused or the file vanished mid-scan: report,
            # keep the source so nothing is lost silently.
            records.append(ImportRecord(entry.name, kind, None,
                                        entry.stat().st_size
                                        if entry.exists() else 0,
                                        error=str(exc)))
            logger.warning("Inbox import failed for %s: %s", entry.name, exc)

    return records
