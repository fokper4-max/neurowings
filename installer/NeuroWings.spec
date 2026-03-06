# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller спецификация для НейроКрылья
Создает один исполняемый файл с внедренными зависимостями
"""

import sys
import os
from pathlib import Path
import importlib.util as _ilu

# Базовая директория проекта
base_dir = Path(os.path.abspath(SPECPATH)).parent

REQUIRED_MODEL_FILES = [
    'yolo_detect_best.pt',
    'yolo_pose_best.pt',
    'stage2_best.pth',
    'stage2_portable.pth',
    'subpixel_best.pth',
]


def resolve_models_dir():
    override = os.environ.get('NEUROWINGS_MODELS_DIR', '').strip()
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Папка моделей не найдена: {candidate}")
        print(f"Using external models directory: {candidate}")
        return candidate
    return base_dir / 'models'


def validate_models_dir(models_path):
    allow_missing = os.environ.get('NEUROWINGS_ALLOW_MISSING_MODELS', '').strip().lower() in {'1', 'true', 'yes'}
    if allow_missing:
        return
    missing = [name for name in REQUIRED_MODEL_FILES if not (models_path / name).exists()]
    if missing:
        raise FileNotFoundError(
            "В папке моделей отсутствуют обязательные файлы: "
            + ", ".join(missing)
            + f". Проверенный путь: {models_path}"
        )


# Пути к важным папкам
models_dir = resolve_models_dir()
validate_models_dir(models_dir)
neurowings_dir = base_dir / 'neurowings'

# Определение скрытых импортов для PyTorch и других зависимостей
hiddenimports = [
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'torch',
    'torchvision',
    'cv2',
    'numpy',
    'ultralytics',
    'openai',
    'psutil',
    # PyTorch зависимости
    'torch.nn',
    'torch.nn.functional',
    'torch.optim',
    'torch.utils.data',
    # OpenCV зависимости
    'cv2.data',
    # YOLO зависимости
    'ultralytics.models',
    'ultralytics.nn',
    'ultralytics.utils',
]

# Данные приложения (модели, конфиги и т.д.)
datas = [
    (str(models_dir), 'models'),         # Папка с моделями
    (str(neurowings_dir), 'neurowings'), # Папка с кодом проекта
]

# Бинарные файлы (для PyTorch и других библиотек)
binaries = []
_torch_spec = _ilu.find_spec('torch')
if _torch_spec and _torch_spec.submodule_search_locations:
    _torch_lib = Path(list(_torch_spec.submodule_search_locations)[0]) / 'lib'
    if _torch_lib.is_dir():
        for _dll in _torch_lib.glob('*.dll'):
            binaries.append((str(_dll), 'torch/lib'))

# Анализ основного скрипта
a = Analysis(
    [str(base_dir / 'run.py')],
    pathex=[str(base_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(base_dir / 'installer' / 'runtime_hook_torch_dll.py')],
    excludes=[
        'PIL.AvifImagePlugin',
        'PIL._avif',
        'matplotlib',  # Если не используется
        'scipy',       # Если не используется
        'pandas',      # Если не используется
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Удаление дубликатов
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Создание одного исполняемого файла
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='НейроКрылья',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Отключено для совместимости с PyTorch DLL
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # С консолью для отладки
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(neurowings_dir / 'assets' / 'app_icon.ico'),
)

# Для отладочной версии с консолью раскомментируйте:
# console=True в exe выше
