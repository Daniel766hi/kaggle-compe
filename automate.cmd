@echo off
rem Turn on the daily automation: double-click this file (after setup and the logins).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m automate
pause
