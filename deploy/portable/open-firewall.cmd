@echo off
rem Allows other computers on the same subnet to reach the web port. Needs Administrator.
net session >nul 2>&1
if errorlevel 1 (
  echo This needs Administrator. Right-click open-firewall.cmd and choose "Run as administrator".
  if not "%EVIDENCE_NO_PAUSE%"=="1" pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0evidence.ps1" -Action open-firewall
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
