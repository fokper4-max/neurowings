@echo off
REM Simple Installer Builder - requires NSIS

setlocal

echo ====================================
echo НейроКрылья Simple Installer Builder
echo ====================================
echo.

REM Check if NSIS is installed
set "NSIS_PATH=C:\Program Files (x86)\NSIS\makensis.exe"

if exist "%NSIS_PATH%" (
    echo [OK] NSIS found
    goto :build
)

echo [!] NSIS not found!
echo.
echo Please install NSIS 3.x from:
echo https://nsis.sourceforge.io/Download
echo.
echo After installation, run this script again.
echo.
pause
exit /b 1

:build
echo [*] Building installer...
echo.

"%NSIS_PATH%" "%~dp0installer_simple.nsi"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================
    echo [OK] Installer created successfully!
    echo ====================================
    echo.
    echo Output: dist\*-2.0-Setup.exe
    echo.

    REM Check if file exists
    if exist "%~dp0..\dist\*-2.0-Setup.exe" (
        for %%A in ("%~dp0..\dist\*-2.0-Setup.exe") do (
            set size=%%~zA
            set /a sizeMB=!size! / 1048576
            echo Size: !sizeMB! MB
        )
    )
) else (
    echo.
    echo ====================================
    echo [ERROR] Build failed!
    echo ====================================
)

echo.
pause
