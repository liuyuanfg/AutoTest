@echo off

:: ============================================================
::  GNSS AutoTest — Offline Dependency Installer
:: ============================================================
:: No internet connection required.
:: Usage: install_deps.bat  [optional: path\to\python.exe]
:: ============================================================

set "WHEELS_DIR=%~dp0wheels"

:: Accept custom Python path, or use default
if "%~1"=="" (
    set "PYTHON=python"
) else (
    set "PYTHON=%~1"
)

echo ============================================================
echo   GNSS AutoTest - Offline Dependency Installer
echo ============================================================
echo.
echo Python: %PYTHON%
echo Wheels: %WHEELS_DIR%
echo.

:: Verify Python works
%PYTHON% --version 2>nul
if errorlevel 1 (
    echo ERROR: Python not found at '%PYTHON%'
    echo.
    echo Try specifying the full path:
    echo   install_deps.bat "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
    echo.
    pause
    exit /b 1
)

:: Verify wheels directory exists
if not exist "%WHEELS_DIR%\pyserial-*.whl" (
    echo ERROR: wheels folder not found at:
    echo   %WHEELS_DIR%
    echo.
    echo This script must be run from the autotest\ folder.
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Installing dependencies from wheels\ ...
echo.

%PYTHON% -m pip install --no-index --find-links="%WHEELS_DIR%" pyserial reportlab pyyaml --quiet --disable-pip-version-check
set PIP_EXIT=%errorlevel%

if %PIP_EXIT% neq 0 (
    echo.
    echo ERROR: Installation failed ^(exit code %PIP_EXIT%^).
    echo.
    echo Troubleshooting:
    echo   1. Run as Administrator
    echo   2. Check Python version matches wheels
    echo   3. Verify wheels folder contains .whl files
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Dependencies installed successfully!
echo ============================================================
echo.
echo You can now run:
    echo   %PYTHON% gui.py
    echo   %PYTHON% main.py -s
echo.
pause
