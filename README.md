# NeuroWings

Source repository for the NeuroWings desktop application.

This repository is intentionally kept source-only so the program can be edited
from any PC, while heavy build artifacts stay on the build machine.

## Included in Git

- Application source code in `neurowings/`
- Entry point `run.py`
- Python dependencies in `requirements.txt`
- Packaging scripts in `installer/`
- Model placement instructions in `models/README.txt`

## Excluded from Git

- Trained model weights from `models/`
- Built executables and archives from `dist/` and `build/`
- Local caches, logs, IDE folders, and machine-specific files
- `drivers/` research/download artifacts

## Local development

1. Clone the repository on any PC.
2. Create a virtual environment.
3. Install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

4. Run the application:

```powershell
python run.py
```

If you need neural processing locally, copy the trained model files into
`models/` according to `models/README.txt`.

## Building EXE on the build PC

Make sure the build PC has:

- Python installed
- all dependencies from `requirements.txt`
- trained models in a local folder outside Git, preferably `C:\ProgramData\NeuroWingsBuilder\models-source`

Build commands:

```powershell
python -m PyInstaller installer/NeuroWings.spec
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -ModelsDir "C:\ProgramData\NeuroWingsBuilder\models-source"
```

The automated Windows build server uses `ModelsSourceDir` from
`installer/setup_windows_builder.ps1` and passes that directory directly to
PyInstaller. This keeps heavy model weights off GitHub while still producing a
self-contained EXE for end users.

## Versioning workflow

Use Git for source history and Git tags for releases:

- `v2.0.0` for the initial imported source release
- `v2.0.1` for fixes
- `v2.1.0` for backward-compatible features
- `v3.0.0` for breaking changes

For each release:

1. Update the user-visible version where needed.
2. Add notes to `CHANGELOG.md`.
3. Commit changes.
4. Create a Git tag.
5. Push commit and tag to GitHub.

Keep these version markers synchronized when publishing a new release:

- `neurowings/core/constants.py`
- `installer/installer.nsi`
- `installer/installer_simple.nsi`

## Notes

Without the model files, the application can still start, and non-neural parts
of the workflow remain available. Full neural processing requires the local
model files on the machine where you run or build the app.
# Документация по схеме релизов и автообновлений

- Основная схема: [docs/RELEASE_SYSTEM.md](docs/RELEASE_SYSTEM.md)
- Инструкция по обновлениям: [installer/UPDATE_GUIDE.md](installer/UPDATE_GUIDE.md)
