@echo off
rem Stops Evidence RAG (web/API server and database). Data stays in the data folder.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0evidence.ps1" -Action stop %*
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
