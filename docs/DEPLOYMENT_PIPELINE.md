# DEPLOYMENT_PIPELINE.md — Windows desktop release pipeline

How `dist\ldcc.exe` gets from source to a shipped, verifiable, reversible
artifact. The pipeline is one command locally (
`desktop_shell\build_release.bat`) and mirrors exactly in GitHub Actions
(`.github/workflows/windows-build.yml`), so what worked on a laptop is what
CI ships.

## Stages (fail-fast)

Every stage must pass before the next runs; a failure stops the release and
leaves the previous build untouched in `dist\archive`.

| # | Stage | Command | Fails when |
|---|-------|---------|------------|
| 1 | Offline suite gate | `python -m pytest -q` | any non-green test (baseline 1041 passed / 7 live deselected) |
| 2 | Secrets/artifacts policy gate | `desktop_shell\check_deployment_policy.py` | staged tree contains `secrets/`, `models/`, `.env`, `*.secrets`, voice model binaries, or the spec references forbidden paths |
| 3 | Archive | copies `dist\ldcc.exe` → `dist\archive\ldcc-<ts>.exe` | (best effort; first build skips) |
| 4 | Build | `python -m PyInstaller desktop_shell\ldcc.spec --noconfirm --distpath dist --workpath build\release_work` | PyInstaller error |
| 5 | Manifest | `desktop_shell\write_build_manifest.py dist\ldcc.exe` | artifact missing |
| 6 | Windowed-launch smoke gate | `powershell -File desktop_shell\verify_build.ps1 -ExePath dist\ldcc.exe` | app does not render its main window, or shows an error dialog |

Stage 6 is the crash guard: it launches the artifact, waits for the window
titled **L&D Command Center** to appear, and probes every matching process
for modal error dialogs. It exits 0 on pass, 1 on fail, 2 on invocation
error, and by design leaves the app running on a PASS (the caller —
`build_release.bat` — owns cleanup).

## Local usage

```
desktop_shell\build_release.bat                 # full gated pipeline (~5 min)
desktop_shell\build_release.bat --no-gate       # skip pytest (dev iteration)
desktop_shell\build_release.bat --no-policy     # skip secrets gate
desktop_shell\build_release.bat --no-verify     # skip smoke, launch manually
```

The interpreter is auto-selected: Python 3.10 with PyInstaller first, then
`.venv\Scripts\python.exe`, then any 3.10+ `python`. The build baseline is
**CPython 3.10.11 + PyInstaller 6.22.2** — the version pair the artifact is
verified against.

Escape hatch: set `LDCC_SKIP_SMOKE=1` to make the smoke gate pass-through
without launching (used where a GUI session is unavailable).

## Rollback

`dist\archive\` keeps every previous build, so a bad release is reversible.

```
desktop_shell\rollback_release.bat              # restore the newest archived release
desktop_shell\rollback_release.bat 20260913     # restore latest archive matching a fragment
```

Rollback returns the last-known-good artifact to `dist\ldcc.exe`; the new
release simply becomes the next entry in the archive. Nothing is ever
deleted — only superseded.

## Verification protocol

After any install or manual copy, confirm the binary matches its manifest:

```
Get-FileHash dist\ldcc.exe -Algorithm SHA256        # compare to dist\ldcc-build.json "sha256"
```

`dist\ldcc-build.txt` is the one-line human form (short sha, size, build
UTC, python/pyinstaller versions, spec sha, upstream commit) for pasting
into release notes or handoffs.

## Monitoring / observability

- `dist\ldcc-build.json` is the operational record: hash, bytes, build time,
  toolchain, spec fingerprint, upstream commit (`no-git-tree` when the
  workspace is not a git checkout).
- Every rebuild archives the prior artifact, so `dist\archive` is a full
  release history even on machines with broken or no git.
- Test a copied build before relying on it: launch, expect the main window,
  check an export renders. If the window never appears the build is broken
  and `rollback_release.bat` is the fix.

## Secrets policy

The bundle is offline-first and **never** contains credentials or voice
models. Stage 2 enforces this mechanically: forbidden names
(`secrets/`, `models/`, `.env`, `*.secrets`, `*.onnx`, `*.gguf`, `*.bin`)
are rejected in the staged tree *and* as spec `datas`/`binaries`
references. If you ever need a genuinely standalone runtime voice, it ships
as a separate opt-in download — not inside the artifact.

## CI behavior

- **`windows-build.yml`** runs the identical six stages on
  `windows-latest`/Python 3.10 after every push/PR to `desktop_shell`, and
  uploads `dist\ldcc.exe` + manifest as an artifact (60-day retention).
- **`release.yml`** is `workflow_dispatch` only and targets the `release`
  GitHub environment — a mandatory human-approval gate at the repository's
  Environment settings — then runs the same gated build and publishes a
  GitHub Release with the exe and manifest. Nothing reaches end users
  without that deliberate, logged human step.
- **`python-app.yml` / `pylint.yml`** keep the Linux story green; their
  compile step uses `desktop_shell` (real directory), matching a fixed
  path typo that previously broke them.
- Local `python-app.yml`-style gates (compile, lint) are run under 3.10;
  CI additionally tests 3.14 as the portable next target.

## Runbook (small)

1. **New build fails the smoke gate.** Do not hand the exe out. Fix the
   code, re-run `build_release.bat`. Distro a prior release from
   `dist\archive` if a user already got the broken one.
2. **User's installed exe crashes.** Ask for `ldcc-build.txt` (or hash the
   exe) to identify the exact build, compare with the runbook copy of
   `dist\archive`, and roll them forward to a passing build.
3. **A shipped build is wrong but CI is green.** Every stage ran; treat it
   as a gate gap — reproduce locally with the same manifest's toolchain
   (Python + PyInstaller versions, spec sha) before reworking the stage.
4. **Secrets gate trips.** `check_deployment_policy.py` names the offender.
   Move the file out of the staged tree (or the reference out of the spec)
   and re-run. Never "fix" it by widening the skip flags in a release.
---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.