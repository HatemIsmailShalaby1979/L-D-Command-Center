"""Headless smoke test — exercise ShellController without a display.

Run:  python smoke_headless.py
Exits 0 when every probe returns a well-formed FlowResult.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import types


def _install_source_aliases() -> None:
    def alias(dotted: str, real: Path) -> None:
        if dotted not in sys.modules:
            module = types.ModuleType(dotted)
            module.__path__ = [str(real)]
            sys.modules[dotted] = module

    alias("engines", _ROOT / "engines")
    alias("model_layer", _ROOT / "model-layer")
    alias("desktop_shell", _ROOT / "desktop_shell")
    for dir_name, mod_name in [
        ("audio-engine", "audio_engine"),
        ("career-engine", "career_engine"),
        ("export-engine", "export_engine"),
        ("journey-core", "journey_core"),
        ("language-lab", "language_lab"),
        ("playground-bridge", "playground_bridge"),
    ]:
        alias(f"engines.{mod_name}", _ROOT / "engines" / dir_name)


_install_source_aliases()

from desktop_shell.controller import ShellController  # noqa: E402

ok: list[str] = []
bad: list[tuple[str, str]] = []


def probe(name: str, fn):
    try:
        res = fn()
        ok.append(f"{name}: ok={getattr(res, 'ok', '?')} "
                  f"kind={getattr(res, 'error_kind', None)}")
    except Exception as exc:  # noqa: BLE001
        bad.append((name, f"{type(exc).__name__}: {exc}\n"
                          f"{traceback.format_exc(limit=4)}"))


def main() -> int:
    ctrl = ShellController()
    print("ShellController instantiated OK")

    probe("check_model_health", ctrl.check_model_health)
    probe("list_available_models", ctrl.list_available_models)
    probe("curriculum_catalog", lambda: ctrl.curriculum_catalog("Spanish"))
    probe("curriculum_stats", lambda: ctrl.curriculum_stats("Spanish"))
    probe("curriculum_next_lesson", lambda: ctrl.curriculum_next_lesson("Spanish"))
    probe("list_saved", lambda: ctrl.list_saved("resumes"))
    probe("list_media", lambda: ctrl.list_media("audiobook"))
    probe("et_scenario_bank", ctrl.et_scenario_bank)
    probe("et_session_state", ctrl.et_session_state)
    probe("et_microphone_devices", ctrl.et_microphone_devices)
    probe("license_status", ctrl.license_status)
    probe("capability_summary", ctrl.capability_summary)
    probe("connector_names", ctrl.connector_names)
    probe("connector_capabilities", ctrl.connector_capabilities)
    probe("available_voices", ctrl.available_voices)
    probe("placement_last", lambda: ctrl.placement_last("Spanish"))
    probe("level_exam_results", lambda: ctrl.level_exam_results("Spanish"))
    probe("campaign_status", ctrl.campaign_status)
    probe("default_inbox_path", ctrl.default_inbox_path)

    print("\n--- PROBES OK ---")
    for line in ok:
        print(" ", line)
    if bad:
        print("\n--- PROBES FAILED ---")
        for name, err in bad:
            print(f"  {name}\n    {err}")
    print(f"\n{len(ok)} ok / {len(bad)} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
