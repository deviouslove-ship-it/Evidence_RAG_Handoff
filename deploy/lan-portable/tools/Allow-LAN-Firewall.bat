@echo off
setlocal EnableExtensions
title Evidence RAG - Mo cong tuong lua cho mang LAN
rem Tao (hoac go) mot quy tac Windows Firewall cho cong web cua Evidence RAG.
rem Chi chay khi ban chu dong bam file nay. Dung: Allow-LAN-Firewall.bat [remove]
set "EVR_MODE=add"
if /I "%~1"=="remove" set "EVR_MODE=remove"
fltmc >nul 2>&1
if errorlevel 1 (
    echo Can quyen Administrator de thay doi Windows Firewall.
    echo Quy tac chi cho phep cong web, tu mang con noi bo, tren mang Private/Domain.
    choice /C YN /M "Mo hop thoai xin quyen Administrator ngay bay gio"
    if errorlevel 2 exit /b 1
    "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%EVR_MODE%' -Verb RunAs"
    exit /b 0
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable.ps1" -Action firewall -Path "%EVR_MODE%"
echo.
pause
