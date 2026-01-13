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
try:
    # Собираем все динамические библиотеки torch, torchvision, cv2
    binaries += collect_dynamic_libs('torch')
    binaries += collect_dynamic_libs('torchvision')
    binaries += collect_dynamic_libs('cv2')
except Exception as e:
    print(f"Warning: Failed to collect some dynamic libs: {e}")

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
