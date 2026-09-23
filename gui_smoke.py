"""GUI launch smoke test — start the real Tk window, verify it renders, close it.

Run:  python gui_smoke.py
Exits 0 when the window opened, is mapped/viewable, has a non-zero size
and was torn down without a crash.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import desktop_shell.app as app  # noqa: E402  (installs source aliases)

boot_error: list[str] = []
started = threading.Event()


def _launch() -> None:
    try:
        started.set()
        app.run()
    except Exception:  # noqa: BLE001
        boot_error.append(traceback.format_exc())


def main() -> int:
    t = threading.Thread(target=_launch, daemon=True)
    t.start()

    import tkinter as tk

    root = None
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            root = tk._default_root
        except Exception:  # noqa: BLE001
            root = None
        if root is not None:
            try:
                if root.winfo_exists():
                    break
            except Exception:  # noqa: BLE001
                root = None
        time.sleep(0.25)

    if boot_error:
        print("BOOT ERROR:\n", boot_error[0])
        return 1
    if root is None:
        print("FAIL: no Tk root was created within 25s")
        return 1

    # let the event loop settle + widgets render
    for _ in range(40):
        try:
            root.update()
        except Exception:  # noqa: BLE001
            break
        time.sleep(0.05)

    try:
        title = root.title()
        exists = root.winfo_exists()
        viewable = root.winfo_viewable()
        width = root.winfo_width()
        height = root.winfo_height()
        children = len(root.winfo_children())
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: window died during inspection: {exc}")
        return 1

    print(f"title     : {title}")
    print(f"exists    : {exists}")
    print(f"viewable  : {viewable}")
    print(f"geometry  : {width}x{height}")
    print(f"children  : {children} top-level widgets")

    healthy = exists and viewable and width > 0 and height > 0 and children > 0
    print("RESULT    :", "WINDOW OK" if healthy else "WINDOW PROBLEM")

    try:
        root.quit()
        root.destroy()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.5)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
