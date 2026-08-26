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
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path(__file__).resolve().parent / "data"


def default_data_root() -> Path:
    """
    Contract: where artifacts live by default. Source checkout keeps the
    historical <repo>/storage/data; a FROZEN (PyInstaller) build must
    never write into its read-only extraction dir (_MEIPASS), so it uses
    the platform data home instead. LDCC_DATA_DIR always wins.
    """
    env = os.environ.get("LDCC_DATA_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base = os.environ.get("APPDATA") or str(Path.home())
            return Path(base) / "LDCC"
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "ldcc"
    return DEFAULT_ROOT

ALLOWED_KINDS = {
    "journeys", "resumes", "podcast_scripts", "bilingual_pairs",
    "lesson_packs", "narrations", "exports", "preferences",
    "capabilities", "verdicts",
}

# Media kinds are namespaced rather than enumerated: "media/<subkind>"
# with a filesystem-safe subkind (P7.8 Import Inbox / Playground).
MEDIA_KIND_PREFIX = "media/"
_MEDIA_SUBKIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


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
        self.root = Path(root) if root is not None else default_data_root()

    # -- internals ------------------------------------------------------

    def _kind_dir(self, kind: str) -> Path:
        if kind.startswith(MEDIA_KIND_PREFIX):
            subkind = kind[len(MEDIA_KIND_PREFIX):]
            if not _MEDIA_SUBKIND_RE.match(subkind):
                raise ValueError(
                    f"Invalid media subkind {subkind!r}; must match "
                    f"{_MEDIA_SUBKIND_RE.pattern}"
                )
            path = self.root / "media" / subkind
            path.mkdir(parents=True, exist_ok=True)
            return path
        if kind not in ALLOWED_KINDS:
            raise ValueError(
                f"Unknown artifact kind {kind!r}; allowed: {sorted(ALLOWED_KINDS)} "
                f"or 'media/<subkind>'"
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
        """Persist a single preference key to disk.

        Known preference schemas:

        * ``"job_watch"`` — Career agent watchlist config (dict).
          Schema::

              {
                "role": str,                  # e.g. "Python developer"
                "location": str,              # e.g. "remote" or ""
                "greenhouse_companies": [str],# e.g. ["stripe", "figma"]
                "lever_companies": [str],
                "ashby_companies": [str],
              }

          Accessed via controller._job_watch() / _save_job_watch().
          The auto-check timer (every 10 min) reads this key to decide
          whether to run search_jobs_now().
        """
        prefs = {}
        prefs_file = self._prefs_file()
        if prefs_file.exists():
            prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
        prefs[key] = value
        prefs_file.write_text(json.dumps(prefs, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Read a single preference key from disk, returning default when absent."""
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
