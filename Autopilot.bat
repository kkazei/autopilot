@echo off
rem Starts the local Autopilot app and opens it in its own window. Close this console window to stop it.
cd /d "%~dp0"
title Autopilot
if not exist ".venv\Scripts\python.exe" (
  echo .venv was not found. See "Running it at $0" in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ui.app --open
if errorlevel 1 pause
