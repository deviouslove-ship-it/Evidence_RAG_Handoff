@echo off
setlocal EnableExtensions
title Evidence RAG - Khoi phuc du lieu
rem Dung: Restore-Data.bat [thu-muc-sao-luu]   (khong tham so: chon trong backups\)
if not exist "%~dp0tools\portable.ps1" (
    echo [LOI] Khong thay tools\portable.ps1.
    if not defined EVR_NOPAUSE pause
    exit /b 1
)
set "EVR_FLAGS="
if "%EVR_YES%"=="1" set "EVR_FLAGS=-Yes"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\portable.ps1" -Action restore -Path "%~1" %EVR_FLAGS%
set "EVR_RC=%ERRORLEVEL%"
echo.
if not defined EVR_NOPAUSE pause
exit /b %EVR_RC%
