@echo off
set "TCLLIBRARY=C:\Users\Thomas\AppData\Local\Programs\Python\Python312\tcl\tcl8.6"
echo L&D Command Center starting — do not close this window.
python -c "import sys; sys.path.insert(0,'.'); import desktop_shell.app as app; print('APP RUNNING ON DESKTOP'); app.run()"
