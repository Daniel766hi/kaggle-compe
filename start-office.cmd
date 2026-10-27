@echo off
rem Open the AI Office: double-click this file. (Windows blocks .ps1 scripts by default; this runs it anyway.)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-office.ps1" %*
if errorlevel 1 pause
