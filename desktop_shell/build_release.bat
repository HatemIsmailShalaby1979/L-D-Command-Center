@echo off
setlocal
rem ===========================================================================
rem  build_release.bat - L&D Command Center Windows release pipeline.
rem
rem  Gates and stages (fail-fast, each must pass before the next runs):
rem
rem    [1] OFFLINE SUITE  run_checks baseline (pytest, live deselected)
rem    [2] POLICY GATE    check_deployment_policy.py (no secrets/voices bundled)
rem    [3] ARCHIVE        previous dist\ldcc.exe -> dist\archive\ldcc-<ts>.exe
rem    [4] BUILD          PyInstaller desktop_shell\ldcc.spec (windowed)
rem    [5] MANIFEST       write_build_manifest.py -> dist\ldcc-build.json
rem    [6] SMOKE GATE     verify_build.ps1 launches exe, asserts window renders
rem
rem  A failing stage stops the pipeline (nothing ships broken) and leaves the
rem  previous release intact in dist\archive for rollback_release.bat.
rem
rem  Usage:   build_release.bat [--no-gate] [--no-policy] [--no-verify]
rem    --no-gate    skip the pytest gate (dev iteration only)
rem    --no-policy  skip the secrets policy gate
rem    --no-verify  skip the windowed-launch smoke gate
rem ===========================================================================

cd /d "%~dp0.."

set "PY="
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
  "%CD%\.venv\Scripts\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) do (
  if not defined PY if exist %%P (
    %%P -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1 && set "PY=%%~P"
  )
)
if not defined PY (
  python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo RELEASE FAIL: no Python 3.10+ interpreter found.
  exit /b 1
)

set "GATE=1"
set "POLICY=1"
set "VERIFY=1"
:args
if /i "%~1"=="--no-gate"   set "GATE=0"   & shift & goto args
if /i "%~1"=="--no-policy" set "POLICY=0" & shift & goto args
if /i "%~1"=="--no-verify" set "VERIFY=0" & shift & goto args

echo =========================================================================
echo  L^&D Command Center release pipeline  (interpreter: %PY%)
echo =========================================================================

if "%GATE%"=="1" (
  echo.
  echo == [1/6] offline suite gate ==
  "%PY%" -m pytest -q
  if errorlevel 1 (
    echo RELEASE FAIL: offline suite not green - fix before shipping.
    exit /b 1
  )
) else (
  echo.
  echo == [1/6] offline suite gate -- SKIPPED, --no-gate given ==
)

if "%POLICY%"=="1" (
  echo.
  echo == [2/6] secrets/artifacts policy gate ==
  "%PY%" desktop_shell\check_deployment_policy.py
  if errorlevel 1 (
    echo RELEASE FAIL: policy violation - nothing may bundle secrets or voices.
    exit /b 1
  )
) else (
  echo.
  echo == [2/6] policy gate -- SKIPPED, --no-policy given ==
)

echo.
echo == [3/6] archive previous artifact ==
if not exist "dist" mkdir "dist"
if not exist "dist\archive" mkdir "dist\archive"
for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%T"
if exist "dist\ldcc.exe" (
  copy /y "dist\ldcc.exe" "dist\archive\ldcc-%TS%.exe" >nul
  echo   archived dist\ldcc.exe  -^>  dist\archive\ldcc-%TS%.exe
) else (
  echo   no previous build to archive (first build)
)

echo.
echo == [4/6] PyInstaller build (windowed) ==
"%PY%" -m PyInstaller desktop_shell\ldcc.spec --noconfirm --distpath dist --workpath build\release_work
if errorlevel 1 (
  echo RELEASE FAIL: PyInstaller build failed - previous build still in dist\archive.
  exit /b 1
)

echo.
echo == [5/6] write build manifest ==
"%PY%" desktop_shell\write_build_manifest.py "dist\ldcc.exe"
if errorlevel 1 (
  echo RELEASE FAIL: manifest write failed.
  exit /b 1
)

if "%VERIFY%"=="1" (
  echo.
  echo == [6/6] windowed-launch smoke gate ==
  powershell -NoProfile -ExecutionPolicy Bypass -File desktop_shell\verify_build.ps1 -ExePath "dist\ldcc.exe"
  if errorlevel 1 (
    echo RELEASE FAIL: smoke gate failed - artifact did not render; roll back with rollback_release.bat.
    exit /b 1
  )
) else (
  echo.
  echo == [6/6] smoke gate -- SKIPPED, --no-verify given; launch dist\ldcc.exe manually ==
)

echo.
echo =========================================================================
echo  RELEASE OK: dist\ldcc.exe built, verified, manifest at dist\ldcc-build.json
echo =========================================================================
endlocal