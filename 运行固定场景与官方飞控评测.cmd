@echo off
chcp 65001 >nul
cd /d "%~dp0"
"runtime\python\python.exe" -X utf8 -B tools\evaluate.py
pause
