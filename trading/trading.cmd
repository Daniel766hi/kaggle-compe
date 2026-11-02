@echo off
rem Paper-trading bot (Freqtrade): double-click for the menu.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0trading.ps1" %*
pause
