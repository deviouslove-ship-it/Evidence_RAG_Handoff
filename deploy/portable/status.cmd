@echo off
rem Shows what is running and the addresses other computers can use.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0evidence.ps1" -Action status %*
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
