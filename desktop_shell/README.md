# Desktop Shell

The desktop-shell engine is responsible for packaging and installing the application as a desktop-native executable. It owns the build pipeline that produces a distributable, installable desktop app (not a web app served from the cloud) and ensures it runs offline on low-spec hardware per the Core Engine Philosophy. If this engine is deleted, the app cannot be packaged or installed as a desktop application; all engines continue to exist but have no distribution surface.

## Running & packaging

```bash
python desktop_shell/app.py                 # run from source
# build (see ldcc.spec header for what staging does):
python3 -m venv ~/.venvs/ldcc-build          # needs a Python WITH tkinter:
                                             #   uv python install 3.14 && uv venv --python 3.14
                                             #   (system ubuntu python3 lacks python3-tk)
uv pip install --python ~/.venvs/ldcc-build/bin/python -r requirements.txt pyinstaller
~/.venvs/ldcc-build/bin/pyinstaller desktop_shell/ldcc.spec --noconfirm
```

The UI is deliberately thin: every behavior lives in
`desktop_shell/controller.py` (headless-tested); widgets only map
`FlowResult.error_kind` to dialogs.

## Endpoint pickers

The header carries two dropdowns, both driven by the controller:

- **Server** — every local inference runtime the machine answered on
  (Ollama `11434`, LM Studio `1234`, or any other OpenAI-compatible server),
  labelled with its base URL and model count. Detection runs off the UI thread
  on startup and on **Reload**; `controller.list_local_servers()` caches the
  result so choosing a server never re-probes the machine. Selecting a server
  calls `controller.select_endpoint(kind)` and refills the model list.
- **Model** — the selected server's own listing. **Probe model** grades that
  model and the health bar names the active provider (`Ollama: ready`,
  `LM Studio: ready`, …).

`select_endpoint()` never replaces a client that a caller injected — that seam
is what keeps the headless controller tests honest.

---

UPDATE 2026-10-03 — Header gains a Server dropdown for Ollama / LM Studio /
OpenAI-compatible runtimes; health bar and error dialogs name the active
provider instead of hardcoding LM Studio. Additive only — the existing Model
dropdown, Reload, and Probe model buttons keep working unchanged.
