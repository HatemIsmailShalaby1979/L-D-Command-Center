"""Point Tkinter at the Tcl/Tk libraries bundled by the Windows build."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
os.environ["TCL_LIBRARY"] = str(_root / "tcl" / "tcl8.6")
os.environ["TK_LIBRARY"] = str(_root / "tcl" / "tk8.6")
