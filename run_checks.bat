@echo off
setlocal
rem ---------------------------------------------------------------------------
rem run_checks.bat - Windows twin of run_checks.sh (P6.2 release gate).
rem
rem WHY THIS FILE EXISTS: run_checks.sh is a bash script that calls `python3`,
rem which does not exist on a stock Windows install - so the documented
rem "one command that must pass before any merge" could not run here at all.
rem This is the same gate, runnable from Explorer or cmd.exe.
rem
rem Gate = syntax check over every source file + full offline suite with a
rem 90%% coverage floor across engines / model-layer / storage / desktop_shell.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"

set "PY="
for %%P in (
  "%~dp0.venv\Scripts\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
  if not defined PY if exist %%P (
    %%P -c "import sys; sys.version_info >= (3, 10)" >nul 2>&1 && set "PY=%%~P"
  )
)

if not defined PY (
  python -c "import sys; sys.version_info >= (3, 10)" >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo ERROR: no Python 3.10+ interpreter found.
  pause
  exit /b 1
)

echo Using %PY%
echo == syntax gate ==

"%PY%" -c "import py_compile; from pathlib import Path; fs=[p for p in Path('.').rglob('*.py') if '.git' not in p.parts]; [py_compile.compile(str(f), doraise=True) for f in fs]; print('compiled', len(fs), 'files cleanly')"
if errorlevel 1 (
  echo.
  echo SYNTAX GATE FAILED
  pause
  exit /b 1
)

echo == offline suite, coverage floor 90%% ==

"%PY%" -m pytest --cov=engines --cov=model-layer --cov=storage --cov=desktop_shell --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=90
if errorlevel 1 (
  echo.
  echo QUALITY GATE FAILED
  pause
  exit /b 1
)

echo.
echo == ALL CHECKS PASSED ==
rem --no-pause lets CI / scripted runs finish without waiting for a keypress.
if /i not "%~1"=="--no-pause" if /i not "%~2"=="--no-pause" pause
endlocal
