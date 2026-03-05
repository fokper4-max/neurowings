@echo off
setlocal

echo ====================================
echo NeuroWings Build and Publish
echo ====================================
echo.

net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [!] Требуются права администратора!
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

powershell -ExecutionPolicy Bypass -File "%~dp0build_and_publish.ps1"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Сборка и публикация завершены.
) else (
    echo.
    echo [ERROR] Сборка или публикация завершились с ошибкой.
)

echo.
pause
