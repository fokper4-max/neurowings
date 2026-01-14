#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings Portable Bundle Builder

Создаёт portable-версию приложения с embedded Python.
Это самый надёжный способ распространения, так как:
- Не зависит от установленного Python на машине пользователя
- Все DLL находятся в правильных относительных путях
- Нет проблем с PyInstaller и распаковкой во временные папки
"""

import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# Конфигурация
PYTHON_VERSION = "3.11.9"  # Embedded Python версия
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
BUILD_DIR = Path(__file__).parent / "build_portable"
DIST_DIR = Path(__file__).parent / "dist_portable"
APP_NAME = "NeuroWings"


def log(message: str) -> None:
    """Лог с префиксом"""
    print(f"[BUILD] {message}")


def download_file(url: str, dest: Path) -> None:
    """Скачать файл с прогресс-баром"""
    log(f"Downloading {url}")

    # Try using curl on macOS/Linux (avoids SSL certificate issues)
    import platform
    if platform.system() in ['Darwin', 'Linux']:
        log("Using curl for download (avoids SSL issues on macOS)")
        result = subprocess.run(['curl', '-L', '-o', str(dest), url], capture_output=True)
        if result.returncode == 0:
            log(f"Downloaded to {dest}")
            return
        else:
            log("curl failed, falling back to urllib")

    # Fallback to urllib (Windows or if curl failed)
    def reporthook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100, downloaded * 100 / total_size)
            sys.stdout.write(f"\r  Progress: {percent:.1f}% ({downloaded}/{total_size} bytes)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, reporthook=reporthook)
    print()  # Новая строка после прогресс-бара
    log(f"Downloaded to {dest}")


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Распаковать ZIP архив"""
    log(f"Extracting {zip_path} to {dest_dir}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(dest_dir)
    log(f"Extracted {len(zip_ref.namelist())} files")


def setup_python(python_dir: Path) -> None:
    """Настроить embedded Python для поддержки pip"""
    log("Setting up embedded Python")

    # 1. Разблокировать импорт из site-packages
    # По умолчанию embedded Python не может импортировать из site-packages
    pth_file = python_dir / f"python{PYTHON_VERSION.replace('.', '')[:3]}._pth"

    if pth_file.exists():
        log(f"Modifying {pth_file.name}")
        content = pth_file.read_text()
        # Раскомментируем строку import site
        content = content.replace('#import site', 'import site')
        # Добавляем Lib/site-packages если ещё нет
        if 'Lib/site-packages' not in content:
            content += '\nLib/site-packages\n'
        pth_file.write_text(content)
        log("Modified ._pth file to enable site-packages")
    else:
        log(f"Warning: {pth_file.name} not found, skipping...")

    # 2. Скачать get-pip.py
    get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
    get_pip_path = python_dir / "get-pip.py"

    if not get_pip_path.exists():
        download_file(get_pip_url, get_pip_path)

    # 3. Установить pip
    python_exe = python_dir / "python.exe"
    log("Installing pip...")
    subprocess.run(
        [str(python_exe), str(get_pip_path), "--no-warn-script-location"],
        check=True,
        cwd=python_dir
    )
    log("pip installed successfully")


def install_dependencies(python_dir: Path, requirements_file: Path) -> None:
    """Установить зависимости из requirements.txt"""
    python_exe = python_dir / "python.exe"

    log(f"Installing dependencies from {requirements_file}")

    # Используем pip напрямую с verbose выводом
    cmd = [
        str(python_exe),
        "-m", "pip",
        "install",
        "--no-warn-script-location",
        "--verbose",  # Добавляем verbose для отладки
        "-r", str(requirements_file)
    ]

    log(f"Running: {' '.join(cmd)}")
    log("This may take 5-10 minutes for PyTorch installation...")

    # Запускаем без capture_output чтобы видеть весь процесс
    result = subprocess.run(cmd, cwd=python_dir)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to install dependencies (exit code: {result.returncode})")

    log("Dependencies installed successfully")

    # Проверяем что PyTorch установился корректно
    log("Verifying PyTorch installation...")
    verify_cmd = [str(python_exe), "-c", "import torch; print(f'PyTorch {torch.__version__} installed at {torch.__file__}')"]
    verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
    if verify_result.returncode == 0:
        log(f"PyTorch verification: {verify_result.stdout.strip()}")
    else:
        log(f"WARNING: PyTorch verification failed: {verify_result.stderr}")


def copy_project_files(dest_dir: Path) -> None:
    """Копировать файлы проекта"""
    log("Copying project files")

    source_dir = Path(__file__).parent

    # Копируем neurowings пакет
    neurowings_src = source_dir / "neurowings"
    neurowings_dst = dest_dir / "neurowings"

    if neurowings_dst.exists():
        shutil.rmtree(neurowings_dst)

    shutil.copytree(
        neurowings_src,
        neurowings_dst,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.DS_Store')
    )
    log(f"Copied {neurowings_src} -> {neurowings_dst}")

    # Копируем run.py
    run_src = source_dir / "run.py"
    run_dst = dest_dir / "run.py"
    shutil.copy2(run_src, run_dst)
    log(f"Copied {run_src} -> {run_dst}")

    # Копируем models/ (нейросетевые модели)
    models_src = source_dir / "models"
    models_dst = dest_dir / "models"
    if models_src.exists() and any(models_src.iterdir()):
        if models_dst.exists():
            shutil.rmtree(models_dst)
        shutil.copytree(models_src, models_dst)
        total_size = sum(f.stat().st_size for f in models_dst.rglob('*') if f.is_file())
        log(f"Copied {models_src} -> {models_dst} ({total_size / (1024*1024):.1f} MB)")
    else:
        log(f"WARNING: models/ folder not found or empty - app will show 'models not found' error")

    # Копируем requirements.txt для справки
    req_src = source_dir / "requirements.txt"
    req_dst = dest_dir / "requirements.txt"
    if req_src.exists():
        shutil.copy2(req_src, req_dst)


def create_launchers(dest_dir: Path) -> None:
    """Создать launcher скрипты"""
    log("Creating launcher scripts")

    # Windows Batch launcher
    batch_launcher = dest_dir / f"{APP_NAME}.bat"
    batch_content = f'''@echo off
REM NeuroWings Portable Launcher
REM This launcher runs the application using embedded Python

setlocal

REM Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check if Python exists
if not exist "python.exe" (
    echo ERROR: python.exe not found!
    echo Please make sure you extracted the complete {APP_NAME} archive.
    pause
    exit /b 1
)

REM CRITICAL: Add PyTorch DLL paths to system PATH
REM This fixes "DLL load failed" errors
set "PATH=%SCRIPT_DIR%Lib\\site-packages\\torch\\lib;%PATH%"
set "PATH=%SCRIPT_DIR%Lib\\site-packages\\torchvision;%PATH%"

REM Set Python to find DLLs
set "PYTHONPATH=%SCRIPT_DIR%"

REM Run application
echo Starting {APP_NAME}...
python.exe run.py %*

REM If application crashed, keep window open
if errorlevel 1 (
    echo.
    echo {APP_NAME} exited with error code %errorlevel%
    echo Check neurowings.log for details.
    pause
)

endlocal
'''
    batch_launcher.write_text(batch_content, encoding='utf-8')
    log(f"Created {batch_launcher}")

    # PowerShell launcher (более современный)
    ps_launcher = dest_dir / f"{APP_NAME}.ps1"
    ps_content = f'''# NeuroWings Portable Launcher (PowerShell)
# This launcher runs the application using embedded Python

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check if Python exists
if (-not (Test-Path "python.exe")) {{
    Write-Host "ERROR: python.exe not found!" -ForegroundColor Red
    Write-Host "Please make sure you extracted the complete {APP_NAME} archive."
    Read-Host "Press Enter to exit"
    exit 1
}}

# Run application
Write-Host "Starting {APP_NAME}..." -ForegroundColor Green
& .\\python.exe run.py $args

# Check exit code
if ($LASTEXITCODE -ne 0) {{
    Write-Host ""
    Write-Host "{APP_NAME} exited with error code $LASTEXITCODE" -ForegroundColor Yellow
    Write-Host "Check neurowings.log for details."
    Read-Host "Press Enter to exit"
}}
'''
    ps_launcher.write_text(ps_content, encoding='utf-8')
    log(f"Created {ps_launcher}")

    # README для пользователей
    readme = dest_dir / "README.txt"
    readme_content = f'''{APP_NAME} - Portable Version
{"=" * 60}

This is a portable (standalone) version of {APP_NAME}.
It includes its own Python interpreter and all dependencies.
No installation required!

HOW TO RUN:
-----------
1. Extract this entire folder to any location
2. Double-click "{APP_NAME}.bat" to start the application
   (Or run "{APP_NAME}.ps1" in PowerShell)

REQUIREMENTS:
------------
- Windows 10/11 (64-bit)
- Visual C++ Redistributable 2015-2022
  (usually already installed)

  If the application fails to start, download and install:
  https://aka.ms/vs/17/release/vc_redist.x64.exe

TROUBLESHOOTING:
---------------
1. If nothing happens when you run the launcher:
   - Check "neurowings.log" file for errors
   - Make sure you extracted ALL files from the archive
   - Try running {APP_NAME}.ps1 instead of .bat

2. If you see "python.exe not found":
   - You didn't extract the complete archive
   - Re-extract everything from the ZIP file

3. If you see DLL errors:
   - Install Visual C++ Redistributable (link above)
   - Make sure Windows is up to date

FOLDER STRUCTURE:
----------------
{APP_NAME}/
├── python.exe           (Embedded Python interpreter)
├── python311.dll        (Python runtime)
├── Lib/                 (Python standard library)
├── Lib/site-packages/   (Dependencies: PyQt5, PyTorch, etc.)
├── neurowings/          (Application code)
├── run.py               (Main entry point)
├── {APP_NAME}.bat       (Windows launcher)
├── {APP_NAME}.ps1       (PowerShell launcher)
└── README.txt           (This file)

LOGS:
-----
The application creates "neurowings.log" in this folder.
If you encounter problems, check this file for error messages.

ABOUT:
------
{APP_NAME} - Neural Network based Wing Analysis Tool
Version: Portable Build
Python: {PYTHON_VERSION} (embedded)

For support and updates, visit:
[Your repository URL here]

{"=" * 60}
'''
    readme.write_text(readme_content, encoding='utf-8')
    log(f"Created {readme}")


def create_zip_archive(source_dir: Path, output_zip: Path) -> None:
    """Создать ZIP архив"""
    log(f"Creating ZIP archive: {output_zip}")

    # Удаляем старый архив если существует
    if output_zip.exists():
        output_zip.unlink()

    # Создаём архив
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=5) as zipf:
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir.parent)
                zipf.write(file_path, arcname)
                # Прогресс каждые 100 файлов
                if len(zipf.namelist()) % 100 == 0:
                    sys.stdout.write(f"\r  Added {len(zipf.namelist())} files...")
                    sys.stdout.flush()

    print()  # Новая строка
    file_count = len(zipfile.ZipFile(output_zip, 'r').namelist())
    size_mb = output_zip.stat().st_size / (1024 * 1024)
    log(f"Archive created: {file_count} files, {size_mb:.1f} MB")


def build_portable() -> None:
    """Основная функция сборки"""
    log("=" * 60)
    log(f"Building {APP_NAME} Portable Bundle")
    log("=" * 60)

    # 1. Подготовка директорий
    log("Step 1: Preparing directories")
    BUILD_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)

    python_zip = BUILD_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    python_dir = DIST_DIR / APP_NAME

    # 2. Скачать Embedded Python
    if not python_zip.exists():
        log("Step 2: Downloading Embedded Python")
        download_file(PYTHON_URL, python_zip)
    else:
        log(f"Step 2: Using cached Python: {python_zip}")

    # 3. Распаковать Python
    log("Step 3: Extracting Embedded Python")
    if python_dir.exists():
        log(f"Cleaning existing directory: {python_dir}")
        shutil.rmtree(python_dir)
    python_dir.mkdir(parents=True)
    extract_zip(python_zip, python_dir)

    # 4. Настроить Python для pip
    log("Step 4: Setting up Python for pip")
    setup_python(python_dir)

    # 5. Установить зависимости
    log("Step 5: Installing dependencies")
    # Используем requirements-portable.txt если существует, иначе requirements.txt
    requirements_portable = Path(__file__).parent / "requirements-portable.txt"
    requirements_file = requirements_portable if requirements_portable.exists() else Path(__file__).parent / "requirements.txt"
    log(f"Using requirements file: {requirements_file.name}")
    install_dependencies(python_dir, requirements_file)

    # 6. Копировать проект
    log("Step 6: Copying project files")
    copy_project_files(python_dir)

    # 7. Создать launchers
    log("Step 7: Creating launchers")
    create_launchers(python_dir)

    # 8. Создать ZIP архив
    log("Step 8: Creating ZIP archive")
    output_zip = DIST_DIR / f"{APP_NAME}-Portable-Windows.zip"
    create_zip_archive(python_dir, output_zip)

    # 9. Готово!
    log("=" * 60)
    log("BUILD COMPLETE!")
    log("=" * 60)
    log(f"Portable folder: {python_dir}")
    log(f"ZIP archive: {output_zip}")
    log(f"Size: {output_zip.stat().st_size / (1024 * 1024):.1f} MB")
    log("")
    log("To test locally:")
    log(f"  cd {python_dir}")
    log(f"  {APP_NAME}.bat")
    log("")
    log("To distribute:")
    log(f"  Share {output_zip}")


if __name__ == "__main__":
    try:
        build_portable()
    except KeyboardInterrupt:
        log("\nBuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        log(f"\nBUILD FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
