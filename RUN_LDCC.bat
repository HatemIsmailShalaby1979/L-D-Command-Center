@echo off
setlocal
cd /d "E:\LD_Command_Center"

rem ---------------------------------------------------------------------------
rem L&D Command Center launcher
rem
rem Run this from Windows Explorer (double-click) or cmd.exe. Do NOT run the
rem python command directly from PowerShell: PowerShell injects null bytes into
rem command-line arguments and Python fails with
rem   ValueError: source code string cannot contain null bytes
rem
rem Why the interpreter detection below: a bare `python` on PATH can resolve to
rem an unrelated install that has none of this project's dependencies (no
rem tkinter, no httpx, ...), which makes the app die at import time with a
rem confusing "No module named ...". We probe candidate interpreters and use
rem the first one that can actually import the runtime deps.
rem ---------------------------------------------------------------------------

set "PY="
for %%P in (
  "%~dp0.venv\Scripts\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
  if not defined PY if exist %%P (
    %%P -c "import tkinter, httpx" >nul 2>&1 && set "PY=%%~P"
  )
)

if not defined PY (
  python -c "import tkinter, httpx" >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo.
  echo ERROR: no Python installation with the L^&D Command Center
  echo dependencies was found. Install them with:
  echo.
  echo     python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Starting L^&D Command Center with %PY%
"%PY%" -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"

if errorlevel 1 (
  echo.
  echo The app exited with an error - see the message above.
  pause
)

endlocal
