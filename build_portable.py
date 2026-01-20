#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings Portable Bundle Builder

Creates a standalone portable version with embedded Python.
No system Python installation required on target machine.
"""

import os
import sys
import shutil
import zipfile
import urllib.request
import subprocess
from pathlib import Path

# Configuration
PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Directories
SCRIPT_DIR = Path(__file__).parent.resolve()
DIST_DIR = SCRIPT_DIR / "dist_portable"
BUNDLE_DIR = DIST_DIR / "NeuroWings-Portable"
APP_DIR = BUNDLE_DIR / "NeuroWings"


def log(msg: str):
    """Print log message"""
    print(f"[BUILD] {msg}")


def download_file(url: str, dest: Path) -> bool:
    """Download file with progress"""
    log(f"Downloading {url}")
    try:
        if sys.platform != "win32" and shutil.which("curl"):
            subprocess.run(["curl", "-L", "-o", str(dest), url], check=True)
        else:
            urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        log(f"Download error: {e}")
        return False


def setup_python():
    """Configure embedded Python"""
    log("Configuring embedded Python...")

    # Find ._pth file
    pth_files = list(APP_DIR.glob("python*._pth"))
    if not pth_files:
        log("ERROR: ._pth file not found")
        return False

    pth_file = pth_files[0]
    log(f"Modifying {pth_file.name}")

    # Enable site-packages
    content = pth_file.read_text()
    content = content.replace("#import site", "import site")
    if "import site" not in content:
        content += "\nimport site\n"
    pth_file.write_text(content)

    # Install pip
    get_pip = APP_DIR / "get-pip.py"
    if not download_file(GET_PIP_URL, get_pip):
        return False

    python_exe = APP_DIR / "python.exe"
    log("Installing pip...")
    result = subprocess.run(
        [str(python_exe), str(get_pip), "--no-warn-script-location"],
        cwd=str(APP_DIR),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        log(f"pip install error: {result.stderr}")
        return False

    get_pip.unlink()
    return True


def install_dependencies():
    """Install Python packages"""
    log("Installing dependencies...")

    python_exe = APP_DIR / "python.exe"

    # Install PyTorch CPU first (smaller size)
    log("Installing PyTorch CPU...")
    result = subprocess.run([
        str(python_exe), "-m", "pip", "install",
        "torch==2.3.1+cpu", "torchvision==0.18.1+cpu",
        "--index-url", "https://download.pytorch.org/whl/cpu",
        "--no-warn-script-location"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        log(f"PyTorch install error: {result.stderr}")
        return False

    # Install other dependencies
    packages = [
        "PyQt5>=5.15.0",
        "numpy>=1.24.0",
        "opencv-python>=4.8.0",
        "ultralytics>=8.0.0",
        "psutil>=5.9.0",
        "openai>=1.14.0",
    ]

    for pkg in packages:
        log(f"Installing {pkg}...")
        result = subprocess.run([
            str(python_exe), "-m", "pip", "install", pkg,
            "--no-warn-script-location"
        ], capture_output=True, text=True)

        if result.returncode != 0:
            log(f"Warning: {pkg} install issue: {result.stderr[:200]}")

    # Verify PyTorch
    log("Verifying PyTorch...")
    result = subprocess.run([
        str(python_exe), "-c", "import torch; print(f'PyTorch {torch.__version__}')"
    ], capture_output=True, text=True)
    log(result.stdout.strip() if result.returncode == 0 else "PyTorch verification failed")

    return True


def copy_project_files():
    """Copy project files to bundle"""
    log("Copying project files...")

    # Copy neurowings package
    src_neurowings = SCRIPT_DIR / "neurowings"
    dst_neurowings = APP_DIR / "neurowings"

    if dst_neurowings.exists():
        shutil.rmtree(dst_neurowings)

    shutil.copytree(
        src_neurowings, dst_neurowings,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")
    )

    # Copy run.py
    shutil.copy2(SCRIPT_DIR / "run.py", APP_DIR / "run.py")

    # Create models directory with README
    models_dir = APP_DIR / "models"
    models_dir.mkdir(exist_ok=True)

    readme_content = """Neural network models for NeuroWings v2.0

Required models (place in this folder):
  - yolo_detect_best.pt     YOLO Detection model
  - yolo_pose_best.pt       YOLO Pose estimation model
  - stage2_best.pth         Stage2 Refinement model
  - stage2_portable.pth     Stage2 Portable model
  - subpixel_best.pth       SubPixel Refinement model

Download models from the project releases page.

Without models the application will start but neural network
processing will not be available.
"""
    (models_dir / "README.txt").write_text(readme_content, encoding="utf-8")

    log("Project files copied")
    return True


def create_launchers():
    """Create launcher scripts"""
    log("Creating launchers...")

    # Main batch launcher
    bat_content = '''@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "APP_DIR=%~dp0NeuroWings"
set "PATH=%APP_DIR%;%APP_DIR%\\Lib\\site-packages\\torch\\lib;%PATH%"
set "PYTHONPATH=%APP_DIR%"
set "PYTHONIOENCODING=utf-8"

echo Starting NeuroWings...
"%APP_DIR%\\python.exe" "%APP_DIR%\\run.py" %*

if errorlevel 1 (
    echo.
    echo Application exited with error. Check NeuroWings\\neurowings.log
    pause
)
'''
    (BUNDLE_DIR / "NeuroWings.bat").write_text(bat_content, encoding="utf-8")

    # README
    readme_content = """NeuroWings Portable for Windows

QUICK START:
1. Double-click NeuroWings.bat to start
2. If models are missing, download them and place in NeuroWings/models/

REQUIREMENTS:
- Windows 10/11 (64-bit)
- Visual C++ Redistributable 2015-2022
  (if app doesn't start, install from: https://aka.ms/vs/17/release/vc_redist.x64.exe)

TROUBLESHOOTING:
- Check NeuroWings/neurowings.log for errors
- Ensure models folder contains all required .pt and .pth files
"""
    (BUNDLE_DIR / "README.txt").write_text(readme_content, encoding="utf-8")

    log("Launchers created")
    return True


def create_zip_archive():
    """Create ZIP archive"""
    log("Creating ZIP archive...")

    zip_path = DIST_DIR / "NeuroWings-Portable-Windows.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in BUNDLE_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f"Archive created: {zip_path.name} ({size_mb:.1f} MB)")
    return True


def build_portable():
    """Main build function"""
    log("=" * 60)
    log("NeuroWings Portable Builder")
    log("=" * 60)

    # Clean previous build
    if DIST_DIR.exists():
        log("Cleaning previous build...")
        shutil.rmtree(DIST_DIR)

    # Create directories
    APP_DIR.mkdir(parents=True, exist_ok=True)

    # Download Python
    python_zip = DIST_DIR / "python-embed.zip"
    if not download_file(PYTHON_EMBED_URL, python_zip):
        log("ERROR: Failed to download Python")
        return False

    # Extract Python
    log("Extracting Python...")
    with zipfile.ZipFile(python_zip, "r") as zf:
        zf.extractall(APP_DIR)
    python_zip.unlink()

    # Setup and install
    if not setup_python():
        return False

    if not install_dependencies():
        return False

    if not copy_project_files():
        return False

    if not create_launchers():
        return False

    if not create_zip_archive():
        return False

    log("=" * 60)
    log("BUILD COMPLETE!")
    log(f"Output: {DIST_DIR}")
    log("=" * 60)
    return True


if __name__ == "__main__":
    success = build_portable()
    sys.exit(0 if success else 1)
