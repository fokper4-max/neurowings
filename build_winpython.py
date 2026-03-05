#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings WinPython Portable Bundle Builder

Создаёт portable версию на основе WinPython.
Это САМЫЙ надёжный способ - работает даже на Windows 7!
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

# Конфигурация
WINPYTHON_VERSION = "3.11.5.0"  # Стабильная версия
WINPYTHON_URL = f"https://github.com/winpython/winpython/releases/download/7.0.20230930final/Winpython64-{WINPYTHON_VERSION}.exe"
# Альтернатива: используем уже готовый WinPython Zero (portable, ~150MB)
WINPYTHON_ZERO_URL = "https://github.com/winpython/winpython/releases/download/7.1.20231216final/Winpython64-3.11.6.0Zero.exe"

BUILD_DIR = Path(__file__).parent / "build_winpython"
DIST_DIR = Path(__file__).parent / "dist_winpython"
APP_NAME = "NeuroWings"


def log(message: str) -> None:
    """Лог с префиксом"""
    print(f"[BUILD] {message}")


def download_file_curl(url: str, dest: Path) -> None:
    """Скачать файл через curl"""
    log(f"Downloading {url}")

    import platform
    if platform.system() in ['Darwin', 'Linux']:
        result = subprocess.run(['curl', '-L', '-o', str(dest), url], capture_output=True)
        if result.returncode == 0:
            log(f"Downloaded to {dest}")
            return

    # Fallback для Windows или если curl не сработал
    log("Using Python urllib for download")
    import urllib.request
    urllib.request.urlretrieve(url, dest)
    log(f"Downloaded to {dest}")


def create_simple_portable_structure() -> None:
    """
    Создаём простую portable структуру БЕЗ автоматической загрузки WinPython.
    Пользователь скачает WinPython отдельно или мы используем GitHub Actions.
    """
    log("=" * 60)
    log(f"Building {APP_NAME} Portable Bundle (WinPython)")
    log("=" * 60)

    # 1. Подготовка
    log("Step 1: Preparing directories")
    BUILD_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)

    bundle_dir = DIST_DIR / APP_NAME
    if bundle_dir.exists():
        log(f"Cleaning {bundle_dir}")
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    # 2. Копируем файлы проекта
    log("Step 2: Copying project files")
    source_dir = Path(__file__).parent

    # Копируем neurowings
    neurowings_dst = bundle_dir / "neurowings"
    shutil.copytree(
        source_dir / "neurowings",
        neurowings_dst,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo')
    )
    log(f"Copied neurowings package")

    # Копируем run.py
    shutil.copy2(source_dir / "run.py", bundle_dir / "run.py")
    log(f"Copied run.py")

    # Копируем requirements
    shutil.copy2(source_dir / "requirements.txt", bundle_dir / "requirements.txt")

    # 3. Создаём launcher скрипты
    log("Step 3: Creating launcher scripts")
    create_launchers(bundle_dir)

    # 4. Создаём инструкцию по установке
    log("Step 4: Creating installation instructions")
    create_installation_guide(bundle_dir)

    # 5. Создаём ZIP
    log("Step 5: Creating ZIP archive")
    output_zip = DIST_DIR / f"{APP_NAME}-WinPython-Portable.zip"
    create_zip(bundle_dir, output_zip)

    log("=" * 60)
    log("BUILD COMPLETE!")
    log("=" * 60)
    log(f"Output: {output_zip}")
    log(f"Size: {output_zip.stat().st_size / (1024 * 1024):.1f} MB")
    log("")
    log("IMPORTANT: User needs to:")
    log("1. Download WinPython from the link in INSTALL.txt")
    log("2. Extract WinPython to NeuroWings folder")
    log("3. Run INSTALL.bat to install dependencies")
    log("4. Run NeuroWings.bat to start")


def create_launchers(bundle_dir: Path) -> None:
    """Создать launcher скрипты для WinPython"""

    # 1. Установочный скрипт
    install_bat = bundle_dir / "INSTALL.bat"
    install_content = f'''@echo off
REM NeuroWings Installation Script for WinPython
REM This script installs all required dependencies

echo ====================================
echo NeuroWings Installation
echo ====================================
echo.

REM Check if WinPython exists
if not exist "WPy64-31160" (
    echo ERROR: WinPython not found!
    echo.
    echo Please follow INSTALL.txt instructions first:
    echo 1. Download WinPython from the link in INSTALL.txt
    echo 2. Extract it to this folder
    echo 3. Run this script again
    echo.
    pause
    exit /b 1
)

REM Find python.exe
set PYTHON_EXE=WPy64-31160\\python-3.11.6.amd64\\python.exe

if not exist "%PYTHON_EXE%" (
    echo ERROR: Python executable not found at %PYTHON_EXE%
    echo Please check your WinPython installation.
    pause
    exit /b 1
)

echo Installing dependencies...
echo This may take 5-10 minutes (PyTorch is large)
echo.

REM Install dependencies
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies
    echo Check the output above for details
    pause
    exit /b 1
)

echo.
echo ====================================
echo Installation Complete!
echo ====================================
echo.
echo You can now run {APP_NAME}.bat to start the application
echo.
pause
'''
    install_bat.write_text(install_content, encoding='utf-8')

    # 2. Launcher скрипт
    launcher_bat = bundle_dir / f"{APP_NAME}.bat"
    launcher_content = f'''@echo off
REM NeuroWings Launcher (WinPython)

REM Find WinPython Python
set PYTHON_EXE=WPy64-31160\\python-3.11.6.amd64\\python.exe

if not exist "%PYTHON_EXE%" (
    echo ERROR: WinPython not found!
    echo.
    echo Please run INSTALL.bat first
    pause
    exit /b 1
)

REM Run application
echo Starting {APP_NAME}...
"%PYTHON_EXE%" run.py %*

if errorlevel 1 (
    echo.
    echo {APP_NAME} exited with error code %errorlevel%
    echo Check neurowings.log for details
    pause
)
'''
    launcher_bat.write_text(launcher_content, encoding='utf-8')

    log(f"Created INSTALL.bat and {APP_NAME}.bat")


def create_installation_guide(bundle_dir: Path) -> None:
    """Создать инструкцию по установке"""

    guide = bundle_dir / "INSTALL.txt"
    guide_content = f'''╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              {APP_NAME} - Installation Instructions              ║
║                      (WinPython Portable)                        ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

ВАЖНО: Эта версия работает на Windows 7/8/10/11 (32/64 bit)!


╔══════════════════════════════════════════════════════════════════╗
║ ШАГ 1: Скачайте WinPython                                       ║
╚══════════════════════════════════════════════════════════════════╝

Перейдите по ссылке и скачайте WinPython:

https://github.com/winpython/winpython/releases/download/7.1.20231216final/Winpython64-3.11.6.0.exe

Размер: ~450 MB

АЛЬТЕРНАТИВА (меньше размер):
https://github.com/winpython/winpython/releases/download/7.1.20231216final/Winpython64-3.11.6.0Zero.exe
Размер: ~150 MB (но нужен интернет для установки пакетов)


╔══════════════════════════════════════════════════════════════════╗
║ ШАГ 2: Установите WinPython В ЭТУ ПАПКУ                         ║
╚══════════════════════════════════════════════════════════════════╝

1. Запустите скачанный Winpython64-3.11.6.0.exe
2. В окне установщика нажмите "..." и выберите ТЕКУЩУЮ ПАПКУ:
   {bundle_dir.absolute()}
3. Нажмите "Extract"
4. Дождитесь окончания распаковки

После этого в этой папке должна появиться папка "WPy64-31160"


╔══════════════════════════════════════════════════════════════════╗
║ ШАГ 3: Установите зависимости                                   ║
╚══════════════════════════════════════════════════════════════════╝

Двойной клик на:  INSTALL.bat

Дождитесь окончания установки (5-10 минут)


╔══════════════════════════════════════════════════════════════════╗
║ ШАГ 4: Запустите приложение                                     ║
╚══════════════════════════════════════════════════════════════════╝

Двойной клик на:  {APP_NAME}.bat

Готово! 🎉


╔══════════════════════════════════════════════════════════════════╗
║ TROUBLESHOOTING                                                  ║
╚══════════════════════════════════════════════════════════════════╝

❌ "WinPython not found"
   → Вы не установили WinPython или установили в другую папку
   → Решение: Повторите Шаг 2, выберите ТЕКУЩУЮ папку

❌ "Failed to install dependencies"
   → Проблемы с интернет-соединением
   → Решение: Проверьте интернет и запустите INSTALL.bat снова

❌ Приложение не запускается
   → Проверьте файл neurowings.log в этой папке
   → Создайте issue на GitHub с содержимым лога


╔══════════════════════════════════════════════════════════════════╗
║ СТРУКТУРА ПАПОК (после установки)                               ║
╚══════════════════════════════════════════════════════════════════╝

{APP_NAME}/
├── WPy64-31160/                    ← WinPython (устанавливается вами)
│   └── python-3.11.6.amd64/
│       ├── python.exe
│       └── Lib/site-packages/      ← Зависимости (PyTorch, etc.)
├── neurowings/                     ← Код приложения
├── run.py                          ← Точка входа
├── {APP_NAME}.bat                  ← ЗАПУСК ПРИЛОЖЕНИЯ
├── INSTALL.bat                     ← Установка зависимостей
├── INSTALL.txt                     ← Эта инструкция
└── requirements.txt                ← Список зависимостей


╔══════════════════════════════════════════════════════════════════╗
║ ПРЕИМУЩЕСТВА WinPython                                          ║
╚══════════════════════════════════════════════════════════════════╝

✅ Работает на Windows 7/8/10/11
✅ Не требует прав администратора
✅ Полностью portable (можно на USB флешке)
✅ Не конфликтует с другими Python установками
✅ Включает Jupyter, Spyder и другие инструменты


╔══════════════════════════════════════════════════════════════════╗
║ ПОМОЩЬ И ПОДДЕРЖКА                                              ║
╚══════════════════════════════════════════════════════════════════╝

GitHub: https://github.com/fokper4-max/neurowings/issues
Логи: neurowings.log (в этой папке)


═══════════════════════════════════════════════════════════════════

Приятного использования! 🦋
'''
    guide.write_text(guide_content, encoding='utf-8')
    log("Created INSTALL.txt")


def create_zip(source_dir: Path, output_zip: Path) -> None:
    """Создать ZIP архив"""
    log(f"Creating ZIP: {output_zip}")

    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=5) as zipf:
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir.parent)
                zipf.write(file_path, arcname)
                if len(zipf.namelist()) % 50 == 0:
                    sys.stdout.write(f"\r  Added {len(zipf.namelist())} files...")
                    sys.stdout.flush()

    print()
    file_count = len(zipfile.ZipFile(output_zip, 'r').namelist())
    size_mb = output_zip.stat().st_size / (1024 * 1024)
    log(f"Archive created: {file_count} files, {size_mb:.1f} MB")


if __name__ == "__main__":
    try:
        create_simple_portable_structure()
    except KeyboardInterrupt:
        log("\nBuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        log(f"\nBUILD FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
