@echo off
setlocal EnableExtensions
title Evidence RAG - Dung may chu
if not exist "%~dp0tools\portable.ps1" (
    echo [LOI] Khong thay tools\portable.ps1.
    if not defined EVR_NOPAUSE pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0tools\portable.ps1" -Action stop
set "EVR_RC=%ERRORLEVEL%"
echo.
if not defined EVR_NOPAUSE pause
exit /b %EVR_RC%
