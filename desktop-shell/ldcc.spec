# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the L&D Command Center desktop shell (P5.4).
# Build (from workspace root):
#   Linux:  pyinstaller desktop-shell/ldcc.spec --noconfirm
#   Windows: pyinstaller desktop-shell/ldcc.spec --noconfirm
#
# Data: voice models (models/tts) and secrets are NOT bundled — the app is
# offline-first but credentials must never ship inside an artifact.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "desktop-shell" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "engines.journey_core.generator",
        "engines.journey_core.renderer",
        "engines.export_engine.export",
        "engines.audio_engine.assembly",
        "storage.persistence",
        "storage.secrets",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="ldcc",
    console=False,
    upx=False,
)
