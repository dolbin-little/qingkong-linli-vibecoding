@echo off
cd /d "%~dp0"
"runtime\python\python.exe" -B tools\launch.py --web-only
if errorlevel 1 pause
