@echo off
setlocal EnableExtensions
title Evidence RAG - Trang thai
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0portable.ps1" -Action status
set "EVR_RC=%ERRORLEVEL%"
echo.
if not defined EVR_NOPAUSE pause
exit /b %EVR_RC%
