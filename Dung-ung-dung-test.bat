@echo off
rem Tat Evidence RAG (may chu web, Ollama, PostgreSQL). Du lieu duoc giu nguyen.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ung-dung-test.ps1" -Action stop %*
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
