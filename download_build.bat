@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo =====================================
echo   GitHub Actions Auto Downloader
echo =====================================
echo.
echo Этот скрипт запустит PowerShell версию
echo которая автоматически скачает готовый .exe
echo.
echo Нажмите любую клавишу для запуска...
pause >nul

powershell.exe -ExecutionPolicy Bypass -File "%~dp0download_build.ps1"

pause
