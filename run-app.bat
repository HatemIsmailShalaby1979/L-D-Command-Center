@echo off
setlocal
rem Launches the L&D Command Center desktop app from source with no console
rem window (pythonw). Requires the repo's Python environment (deps per
rem requirements.txt) already installed.
rem
rem Two fixes vs. the original version:
rem   1. the package directory is "desktop_shell" (underscore), not
rem      "desktop-shell" - the old path never existed on disk.
rem   2. probe for an interpreter that actually has the deps instead of
rem      trusting a bare `pythonw` on PATH.

set "PYW="
for %%P in (
  "%~dp0.venv\Scripts\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
) do (
  if not defined PYW if exist %%P (
    %%P -c "import tkinter, httpx" >nul 2>&1 && set "PYW=%%~P"
  )
)

if not defined PYW (
  pythonw -c "import tkinter, httpx" >nul 2>&1 && set "PYW=pythonw"
)

if not defined PYW (
  echo ERROR: no Python installation with the L^&D Command Center
  echo dependencies was found. Install them with:
  echo     python -m pip install -r requirements.txt
  pause
  exit /b 1
)

start "" "%PYW%" "%~dp0desktop_shell\app.py"
endlocal
