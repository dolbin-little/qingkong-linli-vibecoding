@echo off
cd /d "%~dp0"
"runtime\python\python.exe" -B tools\launch.py
if errorlevel 1 pause
