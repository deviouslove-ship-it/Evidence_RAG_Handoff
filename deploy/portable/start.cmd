@echo off
rem Starts Evidence RAG. Double-click, or run from a command prompt. Set EVIDENCE_NO_PAUSE=1 to skip the final pause.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0evidence.ps1" -Action start %*
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
