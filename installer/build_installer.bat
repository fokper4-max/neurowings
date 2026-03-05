@echo off
REM Простой BAT скрипт для запуска сборки инсталлятора
REM Автоматически запрашивает права администратора

setlocal

echo ====================================
echo НейроКрылья Installer Build
echo ====================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [!] Требуются права администратора!
    echo [*] Запрос прав администратора...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [OK] Права администратора получены
echo.

REM Запуск PowerShell скрипта
echo [*] Запуск PowerShell скрипта сборки...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================
    echo [OK] Сборка завершена успешно!
    echo ====================================
) else (
    echo.
    echo ====================================
    echo [ERROR] Ошибка при сборке!
    echo ====================================
)

echo.
pause
