# storage/secrets.py
#
# WHAT: The one secrets-file adapter — parses git-ignored KEY=VALUE
#       secrets files and resolves a credential by name.
# WHY:  CONSTITUTION.md §3 requires every third-party connection to read
#       credentials from a secrets file, never code. Before P5.1 three
#       near-identical parsers lived in the career-engine integrations;
#       this module concentrates parsing, comment handling, and
#       scan-order policy in one place (two-adapters-plus rule: GitHub,
#       LinkedIn, YouTube already proved the seam real).
# BREAKS IF DELETED: Credential parsing scatters again; placeholder and
#       format rules drift per integration.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"


def parse_secrets_file(path: Path) -> dict[str, str]:
    """
    Contract: parse one secrets file into {KEY: value}.

    Rules: UTF-8 text; `#` starts a comment line; blank lines skipped;
    `KEY=VALUE` split on the FIRST '='; whitespace trimmed from key and
    value; keys keep the rest of the value verbatim (tokens may contain
    '=', padding, or special characters).
    """
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        entries[key.strip()] = value.strip()
    return entries


def load_secret(
    name: str,
    *,
    secrets_path: Optional[Path] = None,
    secrets_dir: Optional[Path] = None,
) -> Optional[str]:
    """
    Contract: resolve credential `name` (e.g. GITHUB_TOKEN).

    Lookup order: explicit `secrets_path` file first; otherwise every
    `*.secrets` file in `secrets_dir` (default /secrets), sorted by
    filename for deterministic precedence. Never logs or returns the
    value in errors; missing/empty yields None.

    Placeholder values are the CALLER's policy — this layer returns what
    the file says.
    """
    if not name:
        return None

    if secrets_path is not None:
        value = parse_secrets_file(Path(secrets_path)).get(name)
        if value:
            logger.info("Secret %s resolved from %s", name, Path(secrets_path).name)
            return value
        return None

    directory = Path(secrets_dir) if secrets_dir else DEFAULT_SECRETS_DIR
    if not directory.exists():
        logger.debug("Secrets dir not found: %s", directory)
        return None

    for file in sorted(directory.glob("*.secrets")):
        value = parse_secrets_file(file).get(name)
        if value:
            logger.info("Secret %s resolved from %s", name, file.name)
            return value
    return None
