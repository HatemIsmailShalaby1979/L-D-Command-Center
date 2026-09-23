@echo off
rem Thin alias for RUN_LDCC.bat - kept so existing shortcuts keep working.
rem The real startup logic (interpreter detection, error reporting) lives in
rem RUN_LDCC.bat; do not duplicate it here.
call "%~dp0RUN_LDCC.bat"
