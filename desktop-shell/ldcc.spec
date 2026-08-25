# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the L&D Command Center desktop shell (P5.4).
#
# Build (from workspace root):
#   Linux/Windows:  pyinstaller desktop-shell/ldcc.spec --noconfirm
#
# WHY STAGING: source engines use HYPHENATED directory names
# (engines/journey-core) aliased at runtime by conftest.py — invisible to
# PyInstaller's static analysis. This spec mirrors every engine into
# build/pyinstaller-src under importable underscore names with __init__.py
# stubs, then analyzes THAT tree. Idempotent; safe to re-run.
#
# Data: voice models and secrets are NOT bundled — offline-first does not
# mean credentials-in-the-artifact.

import shutil
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
STAGE = ROOT / "build" / "pyinstaller-src"

_HYPHEN_MAP = {
    "engines": None,  # container only
    "engines/audio-engine": "engines/audio_engine",
    "engines/career-engine": "engines/career_engine",
    "engines/export-engine": "engines/export_engine",
    "engines/journey-core": "engines/journey_core",
    "engines/language-lab": "engines/language_lab",
    "engines/playground-bridge": "engines/playground_bridge",
    "model-layer": "model_layer",
    "desktop-shell": "desktop_shell",
    "storage": "storage",
}

if Path(STAGE).exists():
    shutil.rmtree(STAGE)

for src_rel, dst_rel in _HYPHEN_MAP.items():
    if dst_rel is None:
        continue
    src = ROOT / src_rel
    dst = STAGE / dst_rel
    dst.mkdir(parents=True, exist_ok=True)
    for py in src.glob("*.py"):
        if py.name.startswith("test_"):
            continue
        shutil.copy2(py, dst / py.name)
    init = dst / "__init__.py"
    if not init.exists():
        init.write_text("")

# engines container package
(STAGE / "engines" / "__init__.py").write_text("")
# app.py must live inside desktop_shell for its relative sys.path logic
shutil.copy2(ROOT / "desktop-shell" / "app.py",
             STAGE / "desktop_shell" / "app.py")

# Every module in the staged tree becomes a hidden import: the shell
# imports engines lazily inside controller methods, so static analysis
# alone would miss most of them.
hiddenimports = []
for pkg_rel in ("engines", "model_layer", "desktop_shell", "storage"):
    base = STAGE / pkg_rel
    for py in base.rglob("*.py"):
        dotted = ".".join(py.with_suffix("").relative_to(STAGE).parts)
        if dotted.endswith("__init__"):
            dotted = dotted[: -len(".__init__")]
        hiddenimports.append(dotted)

a = Analysis(
    [str(STAGE / "desktop_shell" / "app.py")],
    pathex=[str(STAGE)],
    binaries=[],
    datas=[],
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    runtime_hooks=[],
    excludes=["piper", "piper_tts"],  # optional TTS backend; provisioned at runtime
)

# Tcl/Tk support: standalone (uv/python-build-standalone) interpreters keep
# libtcl/libtk and the Tcl script library OUTSIDE site-packages, so
# PyInstaller's tkinter hook finds _tkinter.so but not its libraries.
# Collect them explicitly when present; system pythons need no extra help.
import os

_tk_binaries = []
_tk_datas = []
_base = sys.base_prefix
_libdir = Path(_base) / "lib"
if _libdir.is_dir():
    for soname in ("libtcl9.0.so", "libtcl9.0.so.0", "libtcl9tk9.0.so",
                   "libtcl9tk9.0.so.0", "libtk9.0.so", "libtcl8.6.so",
                   "libtk8.6.so"):
        candidate = _libdir / soname
        if candidate.exists():
            _tk_binaries.append((soname, str(candidate)))
    for treename in ("tcl9.0", "tk9.0", "tcl8", "tcl8.6", "tk8.6"):
        tree = _libdir / treename
        if tree.is_dir():
            for f in tree.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(_libdir)
                    _tk_datas.append((f"lib/{rel}", str(f)))

a.binaries += [(dest, src, "BINARY") for dest, src in _tk_binaries]
a.datas += [(dest, src, "DATA") for dest, src in _tk_datas]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="ldcc",
    console=False,
    upx=False,
)
