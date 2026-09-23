"""check_deployment_policy.py -- pre-build secrets/artifacts policy gate.

Part of the release pipeline (build_release.bat / CI). Fails with a clear
reason when a build would package anything it must not:

  * secrets/ (CONSTITUTION.md section 3: credentials never enter the bundle)
  * model weights / voices (runtime-provisioned, never shipped)
  * .env / *.secrets files anywhere in the staged tree

Checks are intentionally structural (no data dirs are ever configured for the
artifact), so a future spec edit that turns bundling on is caught here.

Exit code 0 = policy clean, 1 = violation, 2 = usage/missing input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "build" / "pyinstaller-src"
SPEC = ROOT / "desktop_shell" / "ldcc.spec"

FORBIDDEN_DIRS = ("secrets", "models")
FORBIDDEN_SUFFIXES = (".env", ".secrets", ".onnx", ".gguf", ".bin")
FORBIDDEN_NAMES = (".env", "secrets", "credentials")
FORBIDDEN_TOKENS = ("secrets/", "models/", ".secrets", ".onnx", ".gguf")


def _scan(stage: Path) -> list[str]:
    hits: list[str] = []
    if not stage.is_dir():
        return hits
    for f in stage.rglob("*"):
        rel = f.relative_to(stage)
        parts = rel.parts
        if any(p in FORBIDDEN_DIRS for p in parts):
            hits.append(f"staged path contains forbidden dir: {rel}")
            continue
        if f.is_file() and (
            f.name in FORBIDDEN_NAMES
            or f.name.endswith(FORBIDDEN_SUFFIXES)
        ):
            hits.append(f"staged file matches forbidden pattern: {rel}")
    return hits


def _spec_baseline(spec_path: Path) -> list[str]:
    hits: list[str] = []
    if not spec_path.is_file():
        return ["ldcc.spec missing — cannot vet the bundle definition"]
    text = spec_path.read_text(encoding="utf-8", errors="replace")
    for token in FORBIDDEN_TOKENS:
        if token in text:
            hits.append(
                f"ldcc.spec mentions '{token}' — datas/binaries "
                "referencing it are disallowed"
            )
    # The Analysis() call must declare empty datas/binaries so the only
    # data shipped is the (whitelisted) Tcl/Tk runtime tree appended later.
    if "datas=[]" not in text or "binaries=[]" not in text:
        hits.append(
            "ldcc.spec Analysis() no longer declares datas=[]/binaries=[] "
            "— nothing but the whitelisted Tcl/Tk tree may be bundled"
        )
    if "secrets" in text and "NOT bundled" not in text:
        hits.append("ldcc.spec references a secrets path outside a denial comment")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        type=Path,
        default=STAGE,
        help="staged PyInstaller source tree to scan (default: build/pyinstaller-src)",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=SPEC,
        help="PyInstaller spec to vet (default: desktop_shell/ldcc.spec)",
    )
    args = parser.parse_args(argv)

    violations: list[str] = _scan(args.stage)
    violations += _spec_baseline(args.spec)

    if violations:
        print("POLICY FAIL")
        for v in violations:
            print(f"  - {v}")
        print("Fix the violation (or remove the offending file) before building.")
        return 1

    print("POLICY PASS")
    print(f"  staged tree      : {args.stage}")
    print(f"  spec baseline    : {args.spec.name} datas=[] binaries=[] intact")
    print("  mandatory dirs   : secrets/ models/ kept out of the bundle")
    return 0


if __name__ == "__main__":
    sys.exit(main())