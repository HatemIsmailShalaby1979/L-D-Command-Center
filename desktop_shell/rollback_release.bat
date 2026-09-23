@echo off
setlocal
rem ===========================================================================
rem  rollback_release.bat - restore the newest archived release to dist\ldcc.exe
rem
rem  build_release.bat keeps every previous artifact in dist\archive\ldcc-*.exe
rem  before overwriting dist\ldcc.exe. If a shipped build turns out broken on a
rem  user machine, restore the last-known-good quickly:
rem
rem    rollback_release.bat              -> restore newest archive
rem    rollback_release.bat <fragment>   -> restore latest archive whose name
rem                                          contains <fragment> (e.g. a date)
rem ===========================================================================

cd /d "%~dp0.."

set "ARCHIVE=dist\archive"
if not exist "%ARCHIVE%" (
  echo ROLLBACK FAIL: no %ARCHIVE% directory - nothing to roll back to.
  exit /b 1
)

if "%~1"=="" (
  for /f "delims=" %%F in ('dir /b /o-d "%ARCHIVE%\ldcc-*.exe" 2^>nul') do if not defined BEST set "BEST=%%F"
) else (
  for /f "delims=" %%F in ('dir /b /o-d "%ARCHIVE%\ldcc-*%~1*.exe" 2^>nul') do if not defined BEST set "BEST=%%F"
)

if not defined BEST (
  echo ROLLBACK FAIL: no matching archive. Contents of %ARCHIVE%:
  if exist "%ARCHIVE%" dir /b "%ARCHIVE%"
  exit /b 1
)

copy /y "%ARCHIVE%\%BEST%" "dist\ldcc.exe" >nul
if errorlevel 1 (
  echo ROLLBACK FAIL: copy failed.
  exit /b 1
)
echo ROLLBACK OK: restored dist\ldcc.exe from %ARCHIVE%\%BEST%
echo Next: launch dist\ldcc.exe and confirm the window renders.
endlocal