# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

# Собираем все подмодули neurowings
hiddenimports = collect_submodules('neurowings') + [
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.sip',
]

# Данные (если есть файлы ресурсов)
datas = []

# Собираем все DLL библиотеки PyTorch (КРИТИЧНО!)
binaries = []
datas_torch = []

try:
    import torch
    import torchvision
    import cv2

    # Находим пути к библиотекам
    torch_path = os.path.dirname(torch.__file__)
    torchvision_path = os.path.dirname(torchvision.__file__)
    cv2_path = os.path.dirname(cv2.__file__)

    print(f"PyInstaller: Collecting torch from {torch_path}")
    print(f"PyInstaller: Collecting torchvision from {torchvision_path}")
    print(f"PyInstaller: Collecting cv2 from {cv2_path}")

    # Собираем динамические библиотеки
    binaries += collect_dynamic_libs('torch')
    binaries += collect_dynamic_libs('torchvision')
    binaries += collect_dynamic_libs('cv2')

    # ВАЖНО: Собираем ВСЕ файлы из torch/lib (включая .dll на Windows)
    torch_lib = os.path.join(torch_path, 'lib')
    if os.path.exists(torch_lib):
        for file in os.listdir(torch_lib):
            if file.endswith(('.dll', '.so', '.dylib', '.pyd')):
                src = os.path.join(torch_lib, file)
                binaries.append((src, 'torch/lib'))
                print(f"  Added: {file}")

    # Также собираем данные PyTorch (могут быть конфиги)
    datas_torch += collect_data_files('torch', include_py_files=False)

except Exception as e:
    print(f"Warning: Failed to collect torch libs: {e}")
    import traceback
    traceback.print_exc()

# Объединяем данные
datas += datas_torch

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем ненужные модули для уменьшения размера и ускорения
        'torch.testing',
        'torch.utils.benchmark',
        'torch.utils.bottleneck',
        'torch.utils.tensorboard',
        'torch.distributed',
        'torchaudio.datasets',
        'torchaudio.pipelines',
        'torchvision.datasets',
        'torchvision.models',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NeuroWings',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # ОТКЛЮЧАЕМ UPX - ломает PyTorch DLL!
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # С консольным окном для отладки
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
