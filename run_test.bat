@echo off
:: ============================================================
::  GNSS AutoTest Launcher (Windows)
:: ============================================================
:: Usage:
::   run_test.bat                → launch GUI
::   run_test.bat -g             → launch GUI (explicit)
::   run_test.bat -c config.yaml → CLI mode with config
::   run_test.bat -s             → CLI simulation mode
::   run_test.bat --list-ports   → list COM ports
:: ============================================================

set PYTHONPATH=%~dp0

if "%1"=="" goto gui
if "%1"=="-g" goto gui

:: CLI mode — forward to main.py
python "%~dp0main.py" %*
goto end

:gui
:: GUI mode
python "%~dp0gui.py"
goto end

:end
pause
