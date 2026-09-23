# engines/language-lab/flagship_batch.py
#
# WHAT: One-shot batch generator for the curated flagship packs —
#       generates, renders, and foots every curated topic for the
#       focus languages, producing the shareable marketing artifacts
#       (PROFIT_PLAN §6 Days 31-60: "10 curated flagship packs per
#       top-3 language, each footered with the app").
# WHY:  The marketing funnel needs artifacts the owner can post to
#       communities TODAY. Running the app by hand 30 times is not a
#       workflow; this is. Skips anything already generated (safe to
#       re-run), isolates per-pack failures (one bad topic never kills
#       the batch), and reports exactly what landed where.
#       NOT wired into the UI: a marketing tool, run on demand via
#       `python -m engines.language_lab.flagship_batch` next to a live
#       LM Studio.
# BREAKS IF DELETED: The funnel's artifacts go back to being generated
#       by hand.

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any, Optional

from model_layer.client import LmStudioClient
from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)

__all__ = ["generate_flagship_batch", "batch_report"]


def generate_flagship_batch(
    *,
    languages: Optional[list[str]] = None,
    known_language: str = "en",
    level: str = "beginner",
    client: Optional[LmStudioClient] = None,
    storage: Optional[Storage] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Generate every curated flagship pack that does not exist yet.

    Returns the report the caller (CLI or owner) reads::

        {
          "generated": [{language, key, title, path, seconds}],
          "skipped":  [{language, key, title, reason}],
          "failed":   [{language, key, title, error}],
        }

    Idempotent: an existing lesson_packs/<key>...json for the language
    is skipped, never regenerated (stable marketing links, no drift).
    `limit` caps total new generations — the first run can smoke-test
    with 1-2 packs before committing the whole batch.
    """
    from engines.language_lab.flagship_packs import (
        FLAGSHIP_PACKS, FOCUS_LANGUAGES,
    )
    from engines.language_lab.lesson_pack import (
        generate_lesson_pack as run_generation,
    )
    from engines.language_lab.renderer import (
        PackFooter, render_lesson_pack_html,
    )

    client = client or LmStudioClient()
    storage = storage or default_storage()
    langs = [l for l in (languages or list(FOCUS_LANGUAGES))
             if l in FLAGSHIP_PACKS]

    report: dict[str, Any] = {"generated": [], "skipped": [], "failed": []}
    made = 0
    for lang in langs:
        for topic in FLAGSHIP_PACKS[lang]:
            stem = f"flagship-{topic.key}-{lang}"
            if any(n.startswith(f"{stem}") for n in
                   storage.list_artifacts("lesson_packs")):
                report["skipped"].append({
                    "language": lang, "key": topic.key,
                    "title": topic.title, "reason": "already generated"})
                continue
            if limit is not None and made >= limit:
                report["skipped"].append({
                    "language": lang, "key": topic.key,
                    "title": topic.title, "reason": "limit reached"})
                continue
            started = time.monotonic()
            try:
                pack = run_generation(
                    topic.prompt, lang, known_language, level,
                    client=client, model=_loaded_model(client),
                )
            except Exception as exc:  # noqa: BLE001 — isolate per pack
                logger.warning("Flagship %s/%s failed: %s",
                               lang, topic.key, exc)
                report["failed"].append({
                    "language": lang, "key": topic.key,
                    "title": topic.title, "error": f"{type(exc).__name__}: "
                                                   f"{exc}"})
                continue
            storage.save_artifact("lesson_packs", f"{stem}.json", pack)
            document = render_lesson_pack_html(pack, footer=PackFooter())
            path = storage.save_artifact("exports", f"{stem}.html",
                                         document)
            made += 1
            seconds = round(time.monotonic() - started, 1)
            report["generated"].append({
                "language": lang, "key": topic.key, "title": topic.title,
                "path": str(path), "seconds": seconds})
            logger.info("Flagship pack %s (%s) -> %s in %.1fs",
                        topic.key, lang, path, seconds)
    return report


def _loaded_model(client: LmStudioClient) -> str:
    models = client.list_models()
    if not models:
        raise RuntimeError(
            "LM Studio has no model loaded — start it and load a model "
            "before running the flagship batch.")
    return models[0]


def batch_report(report: dict[str, Any]) -> str:
    """One human paragraph summarizing a batch run."""
    lines = [
        f"Generated {len(report['generated'])}, "
        f"skipped {len(report['skipped'])}, "
        f"failed {len(report['failed'])}.",
    ]
    for row in report["generated"]:
        lines.append(f"  [+] {row['language']}/{row['key']} — "
                     f"{row['title']} ({row['seconds']}s)")
    for row in report["failed"]:
        lines.append(f"  [!] {row['language']}/{row['key']} — "
                     f"{row['error'][:90]}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: generate the marketing batch against a live LM Studio.

        python -m engines.language_lab.flagship_batch            # all 30
        python -m engines.language_lab.flagship_batch --limit 2  # smoke
        python -m engines.language_lab.flagship_batch --languages ja
    """
    parser = argparse.ArgumentParser(
        prog="flagship_batch",
        description="Generate the curated flagship packs (marketing "
                    "artifacts) for the focus languages.")
    parser.add_argument("--languages", nargs="*", default=None,
                        help="subset of es/ja/de (default: all three)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap new generations (smoke-test first)")
    parser.add_argument("--level", default="beginner",
                        help="pack level for the batch")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    report = generate_flagship_batch(
        languages=args.languages, level=args.level, limit=args.limit)
    print(batch_report(report))
    return 1 if report["failed"] and not report["generated"] else 0


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    raise SystemExit(main())
