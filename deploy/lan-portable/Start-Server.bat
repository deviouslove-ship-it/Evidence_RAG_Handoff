@echo off
setlocal EnableExtensions
title Evidence RAG - Khoi dong may chu
if not exist "%~dp0tools\portable.ps1" (
    echo.
    echo [LOI] Khong thay tools\portable.ps1. Hay giai nen TOAN BO goi ZIP ra mot thu muc roi chay lai.
    if not defined EVR_NOPAUSE pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0tools\portable.ps1" -Action start
set "EVR_RC=%ERRORLEVEL%"
echo.
if "%EVR_RC%"=="0" (echo Co the dong cua so nay: may chu van chay nen. Dung may chu bang Stop-Server.bat.) else (echo KHOI DONG KHONG THANH CONG - xem thong bao [LOI] o tren va logs\launcher.log.)
if not defined EVR_NOPAUSE pause
exit /b %EVR_RC%
