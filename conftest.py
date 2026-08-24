# conftest.py
#
# WHAT: root pytest bootstrap - makes every engine importable as a package
#       despite hyphenated directory names, via underscore aliases registered
#       in sys.modules (engines.journey_core -> engines/journey-core, etc).
# WHY:  P0.1 of docs/PRODUCTION_PLAN.md - one import convention instead of
#       ~30 per-file sys.path hacks. Hyphenated dirs cannot be Python package
#       names, so each gets an alias whose __path__ points at the real dir.
# BREAKS IF DELETED: `python -m pytest` from the root cannot collect any
#       suite; canonical dotted import paths (model_layer.*, engines.*_.*)
#       stop resolving everywhere.

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _alias(dotted_name: str, real_dir: Path) -> None:
    """Register dotted_name as a package backed by real_dir."""
    if dotted_name in sys.modules:
        return
    init = real_dir / "__init__.py"
    if init.exists():
        spec = importlib.util.spec_from_file_location(
            dotted_name, init, submodule_search_locations=[str(real_dir)]
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = types.ModuleType(dotted_name)
        module.__path__ = [str(real_dir)]
    module.__package__ = dotted_name
    sys.modules[dotted_name] = module


_alias("engines", ROOT / "engines")
_alias("model_layer", ROOT / "model-layer")
_alias("desktop_shell", ROOT / "desktop-shell")
for _dir_name, _alias_name in [
    ("audio-engine", "audio_engine"),
    ("career-engine", "career_engine"),
    ("export-engine", "export_engine"),
    ("journey-core", "journey_core"),
    ("language-lab", "language_lab"),
    ("playground-bridge", "playground_bridge"),
]:
    _alias(f"engines.{_alias_name}", ROOT / "engines" / _dir_name)
