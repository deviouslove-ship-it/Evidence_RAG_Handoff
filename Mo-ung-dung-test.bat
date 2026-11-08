@echo off
rem Mo Evidence RAG de test giao dien: bam doi file nay. Dong cua so nay khong tat ung dung.
rem De tat ung dung: Dung-ung-dung-test.bat. Dat EVIDENCE_NO_PAUSE=1 de bo qua buoc cho nhan phim.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ung-dung-test.ps1" -Action start %*
set "EVIDENCE_EXIT=%ERRORLEVEL%"
if not "%EVIDENCE_NO_PAUSE%"=="1" pause
exit /b %EVIDENCE_EXIT%
