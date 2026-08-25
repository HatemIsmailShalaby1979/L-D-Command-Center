# Desktop Shell

The desktop-shell engine is responsible for packaging and installing the application as a desktop-native executable. It owns the build pipeline that produces a distributable, installable desktop app (not a web app served from the cloud) and ensures it runs offline on low-spec hardware per the Core Engine Philosophy. If this engine is deleted, the app cannot be packaged or installed as a desktop application; all engines continue to exist but have no distribution surface.

## Running & packaging

```bash
python desktop-shell/app.py                 # run from source
# build (see ldcc.spec header for what staging does):
python3 -m venv ~/.venvs/ldcc-build          # needs a Python WITH tkinter:
                                             #   uv python install 3.14 && uv venv --python 3.14
                                             #   (system ubuntu python3 lacks python3-tk)
uv pip install --python ~/.venvs/ldcc-build/bin/python -r requirements.txt pyinstaller
~/.venvs/ldcc-build/bin/pyinstaller desktop-shell/ldcc.spec --noconfirm
```

The UI is deliberately thin: every behavior lives in
`desktop-shell/controller.py` (headless-tested); widgets only map
`FlowResult.error_kind` to dialogs.
