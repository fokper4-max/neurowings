# PyInstaller runtime hook to fix PyTorch DLL loading on Windows.
#
# Problem: PyTorch 2.x calls LoadLibraryExW(dll, None, 0x1100) which uses
# LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR.
# This does NOT search PATH — only system dirs, the DLL's own directory,
# and directories registered via AddDllDirectory().
#
# c10.dll depends on MSVCP140.dll / VCRUNTIME140.dll which PyInstaller
# places into _MEIPASS root (not torch/lib/), so they are invisible to
# the restricted search unless we register _MEIPASS via AddDllDirectory.
#
# We MUST keep every AddDllDirectory handle alive (prevent GC) for the
# entire process lifetime, otherwise RemoveDllDirectory is called.

import os
import sys

# --- handles that MUST survive until process exit ---
_dll_dir_handles = []

if hasattr(sys, '_MEIPASS'):
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

torch_lib_dir = os.path.join(base_dir, 'torch', 'lib')

if os.path.isdir(torch_lib_dir):
    # 1. Register BOTH directories via AddDllDirectory (Python 3.8+):
    #    - base_dir (_MEIPASS root) : MSVCP140, VCRUNTIME140, VCOMP140, etc.
    #    - torch_lib_dir           : c10, torch_cpu, torch, etc.
    if hasattr(os, 'add_dll_directory'):
        for _dir in (base_dir, torch_lib_dir):
            if os.path.isdir(_dir):
                try:
                    _dll_dir_handles.append(os.add_dll_directory(_dir))
                except OSError:
                    pass

    # 2. Legacy PATH fallback (for subprocesses and native code)
    os.environ['PATH'] = (
        torch_lib_dir + os.pathsep +
        base_dir + os.pathsep +
        os.environ.get('PATH', '')
    )

    # 3. Pre-load MSVC runtime DLLs first (c10.dll depends on them),
    #    then torch DLLs in dependency order.  Using winmode=0 so that
    #    LoadLibraryW uses the classic search order (which includes PATH).
    import ctypes
    _preload_order = [
        # MSVC runtime (from _MEIPASS root)
        ('VCRUNTIME140.dll',      base_dir),
        ('VCRUNTIME140_1.dll',    base_dir),
        ('MSVCP140.dll',          base_dir),
        ('VCOMP140.DLL',          base_dir),
        # Torch DLLs (from torch/lib)
        ('c10.dll',               torch_lib_dir),
        ('torch_cpu.dll',         torch_lib_dir),
        ('torch_global_deps.dll', torch_lib_dir),
        ('torch.dll',             torch_lib_dir),
    ]
    for _dll_name, _dll_dir in _preload_order:
        _dll_path = os.path.join(_dll_dir, _dll_name)
        if os.path.isfile(_dll_path):
            try:
                ctypes.CDLL(_dll_path, winmode=0)
            except OSError:
                pass
