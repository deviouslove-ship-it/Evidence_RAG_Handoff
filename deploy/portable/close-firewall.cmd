@echo off
rem Removes the firewall rule created by open-firewall.cmd. Needs Administrator.
net session >nul 2>&1
if errorlevel 1 (
  echo This needs Administrator. Right-click close-firewall.cmd and choose "Run as administrator".
  if not "%EVIDENCE_NO_PAUSE%"=="1" pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0evidence.ps1" -Action close-firewall
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
