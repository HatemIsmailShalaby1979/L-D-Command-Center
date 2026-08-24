# storage/persistence.py
#
# WHAT: Local artifact persistence — file-based save/load/list/delete for
#       every artifact kind the app produces, plus key-value preferences.
# WHY:  P5.1 of docs/PRODUCTION_PLAN.md. Until now generated content only
#       existed in memory; the desktop shell (P5.2) and any revisit/
#       extend flows need durable storage that works fully offline.
#       Layout is plain files under one root so users can back it up by
#       copying a folder.
# BREAKS IF DELETED: Journeys/resumes/audio have no home; the app forgets
#       everything between sessions and preferences reset.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path(__file__).resolve().parent / "data"

ALLOWED_KINDS = {
    "journeys", "resumes", "podcast_scripts", "bilingual_pairs",
    "narrations", "exports", "preferences", "capabilities", "verdicts",
}


class Storage:
    """
    Contract: file-backed persistence for artifacts and preferences.

    One instance owns a root directory (default: storage/data, override
    with `root` or LDCC_DATA_DIR). Artifacts live at <root>/<kind>/<name>
    — JSON for dict/list/str payloads, raw bytes otherwise (a suffix hint
    may be embedded in `name`). Preferences are a single JSON file.

    All methods are synchronous and offline.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        import os
        env = os.environ.get("LDCC_DATA_DIR")
        self.root = Path(root or env or DEFAULT_ROOT)

    # -- internals ------------------------------------------------------

    def _kind_dir(self, kind: str) -> Path:
        if kind not in ALLOWED_KINDS:
            raise ValueError(
                f"Unknown artifact kind {kind!r}; allowed: {sorted(ALLOWED_KINDS)}"
            )
        path = self.root / kind
        path.mkdir(parents=True, exist_ok=True)
        return path

    # On-disk containers are tagged so str / bytes / JSON survive
    # roundtrips exactly: T=text, B=binary, J=json document.
    _TAG_TEXT, _TAG_BIN, _TAG_JSON = b"T", b"B", b"J"

    @classmethod
    def _encode(cls, data: Any) -> bytes:
        if isinstance(data, bytes):
            return cls._TAG_BIN + data
        if isinstance(data, str):
            return cls._TAG_TEXT + data.encode("utf-8")
        return cls._TAG_JSON + json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    @classmethod
    def _decode(cls, raw: bytes) -> Any:
        tag, body = raw[:1], raw[1:]
        if tag == cls._TAG_TEXT:
            return body.decode("utf-8")
        if tag == cls._TAG_JSON:
            return json.loads(body.decode("utf-8"))
        if tag == cls._TAG_BIN:
            return body
        return raw  # untagged legacy file: return as-is

    # -- artifacts ------------------------------------------------------

    def save_artifact(self, kind: str, name: str, data: Any) -> Path:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError(f"Invalid artifact name: {name!r}")
        dest = self._kind_dir(kind) / name
        dest.write_bytes(self._encode(data))
        logger.info("Saved %s/%s (%d bytes)", kind, name, dest.stat().st_size)
        return dest

    def load_artifact(self, kind: str, name: str) -> Any:
        src = self._kind_dir(kind) / name
        if not src.exists():
            raise FileNotFoundError(f"No such artifact: {kind}/{name}")
        return self._decode(src.read_bytes())

    def list_artifacts(self, kind: str) -> list[str]:
        return sorted(p.name for p in self._kind_dir(kind).iterdir() if p.is_file())

    def delete_artifact(self, kind: str, name: str) -> None:
        dest = self._kind_dir(kind) / name
        if dest.exists():
            dest.unlink()
            logger.info("Deleted %s/%s", kind, name)

    # -- preferences ------------------------------------------------------

    def _prefs_file(self) -> Path:
        return self._kind_dir("preferences") / "preferences.json"

    def set_preference(self, key: str, value: Any) -> None:
        prefs = {}
        prefs_file = self._prefs_file()
        if prefs_file.exists():
            prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
        prefs[key] = value
        prefs_file.write_text(json.dumps(prefs, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def get_preference(self, key: str, default: Any = None) -> Any:
        prefs_file = self._prefs_file()
        if not prefs_file.exists():
            return default
        prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
        return prefs.get(key, default)


_default_storage: Optional[Storage] = None


def default_storage() -> Storage:
    """Process-wide shared instance (respects LDCC_DATA_DIR once)."""
    global _default_storage
    if _default_storage is None:
        _default_storage = Storage()
    return _default_storage
