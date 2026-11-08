@echo off
setlocal EnableExtensions
title Evidence RAG - Kiem tra toan ven goi
rem So SHA-256 cua moi tep runtime, model, ung dung, tai lieu goc voi checksums.sha256 cua ban phat hanh.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0portable.ps1" -Action verify
set "EVR_RC=%ERRORLEVEL%"
echo.
if not defined EVR_NOPAUSE pause
exit /b %EVR_RC%
