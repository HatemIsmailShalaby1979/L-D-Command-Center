"""write_build_manifest.py -- versioning/observability record for dist\\ldcc.exe.

Produced as the artifact-management stage of build_release.bat and CI.
Writes dist/ldcc-build.json (machine-readable: sha256, build time, tool
versions, upstream source) plus a human one-liner dist/ldcc-build.txt so a
downloaded binary can always be traced back to its build and spec.

Exit code 0 on success; 2 on usage/problem.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "desktop_shell" / "ldcc.spec"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool_versions() -> dict[str, str]:
    info = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        out = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=30,
        )
        info["pyinstaller"] = out.stdout.strip().splitlines()[-1].strip()
    except Exception:  # noqa: BLE001 — informational only
        info["pyinstaller"] = "unknown"
    return info


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=10, cwd=ROOT,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "no-git-tree"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path, help="path to the built dist exe")
    parser.add_argument(
        "--name",
        default="ldcc",
        help="artifact base name (default: ldcc)",
    )
    args = parser.parse_args(argv)

    exe = args.exe.resolve()
    if not exe.is_file():
        print(f"MANIFEST FAIL: artifact not found: {exe}")
        return 2

    dist = exe.parent
    digest = _sha256(exe)
    versions = _tool_versions()
    spec_digest = _sha256(SPEC) if SPEC.is_file() else "missing"

    record = {
        "artifact": exe.name,
        "sha256": digest,
        "sha256_short": digest[:8],
        "bytes": exe.stat().st_size,
        "built_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "tools": versions,
        "spec": str(SPEC),
        "spec_sha256": spec_digest,
        "upstream_commit": _git_commit(),
    }

    json_path = dist / f"{args.name}-build.json"
    txt_path = dist / f"{args.name}-build.txt"
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    txt_path.write_text(
        "{artifact} {sha256_short} {bytes}B built {built_utc} "
        "{tools[python]} pyinstaller={tools[pyinstaller]} "
        "spec={spec_sha256} upstream={upstream_commit}\n".format_map(record),
        encoding="utf-8",
    )

    print(f"MANIFEST OK: {json_path}")
    print(f"  sha256={record['sha256']}")
    print(f"  size={record['bytes']} bytes")
    print(f"  python={versions['python']} pyinstaller={versions['pyinstaller']}")
    print(f"  spec={record['spec_sha256']} upstream={record['upstream_commit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())