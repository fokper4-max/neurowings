@echo off
setlocal EnableDelayedExpansion

echo =====================================
echo   GitHub Actions Auto Downloader
echo =====================================
echo.
echo Starting PowerShell script...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0download_build.ps1"

echo.
echo Press any key to exit...
pause >nul
