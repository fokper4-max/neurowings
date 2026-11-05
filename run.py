#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
НейроКрылья - RUN (v2.2.0)

Точка входа десктопного приложения:
- Ротируемое логирование (RotatingFileHandler, 2 МБ, 3 файла резервных копий)
- Предзагрузка PyTorch до инициализации Qt
- Перехват необработанных исключений в слотах/событиях Qt (SafeApplication)
- Поддержка пакетного CLI режима (--recognize)
"""

import sys
import os
import logging
from logging.handlers import RotatingFileHandler
import traceback
import platform
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "state"))) / "NeuroWings"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "neurowings.log"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Настройка логирования с ротацией и обработкой ошибок
try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RotatingFileHandler(
                LOG_FILE,
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
except (PermissionError, OSError) as e:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    print(f"Предупреждение: не удалось создать лог-файл {LOG_FILE}: {e}")

logger = logging.getLogger("NeuroWings")


def _resolve_app_icon() -> Path | None:
    candidates = [
        BASE_DIR / "neurowings" / "assets" / "app_icon.png",
        BASE_DIR / "neurowings" / "assets" / "app_icon.ico",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _log_startup():
    logger.info("=" * 100)
    logger.info("НейроКрылья START")
    logger.info(f"Time: {datetime.now().isoformat(sep=' ', timespec='seconds')}")
    logger.info(f"Python: {sys.version.replace(os.linesep, ' ')}")
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Executable: {sys.executable}")
    logger.info(f"CWD: {os.getcwd()}")
    logger.info(f"BASE_DIR: {BASE_DIR}")
    logger.info(f"ARGS: {sys.argv}")
    logger.info("-" * 100)
    logger.info("sys.path:")
    for p in sys.path:
        logger.info(f"  - {p}")
    logger.info("=" * 100)


def _install_excepthook():
    def _hook(exc_type, exc, tb):
        logger.critical("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc, tb))
    sys.excepthook = _hook


def _install_qt_message_handler():
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

        def handler(mode, context, message):
            if mode == QtMsgType.QtDebugMsg:
                logger.debug(f"QT: {message}")
            elif mode == QtMsgType.QtInfoMsg:
                logger.info(f"QT: {message}")
            elif mode == QtMsgType.QtWarningMsg:
                logger.warning(f"QT: {message}")
            elif mode == QtMsgType.QtCriticalMsg:
                logger.error(f"QT: {message}")
            elif mode == QtMsgType.QtFatalMsg:
                logger.critical(f"QT: {message}")
            else:
                logger.info(f"QT: {message}")

        qInstallMessageHandler(handler)
        logger.info("Qt message handler: installed")
    except Exception as e:
        logger.warning(f"Qt message handler: NOT installed ({e})")


def _import_torch() -> bool:
    """Import torch before Qt with clearer diagnostics."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
    try:
        import torch  # noqa: F401
        logger.info(
            "PyTorch loaded: %s (from %s)",
            getattr(torch, "__version__", "unknown"),
            getattr(torch, "__file__", "unknown"),
        )
        return True
    except Exception:
        logger.critical(
            "PyTorch import failed (missing VC++ runtime or corrupted DLLs). "
            "Install vc_redist.x64.exe and retry."
        )
        logger.critical(traceback.format_exc())
        return False


def main():
    if "--recognize" in sys.argv:
        from neurowings.batch_cli import main as batch_main
        return batch_main(sys.argv[1:])

    _install_excepthook()
    _log_startup()

    neurowings_dir = BASE_DIR / "neurowings"
    if not neurowings_dir.exists():
        logger.warning(f"Директория neurowings не найдена: {neurowings_dir}")

    _import_torch()

    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QIcon
        from PyQt5.QtCore import Qt
    except ImportError as e:
        logger.error(f"PyQt5 не установлен: {e}")
        sys.exit(1)

    _install_qt_message_handler()

    class SafeApplication(QApplication):
        def notify(self, receiver, event):
            try:
                return super().notify(receiver, event)
            except Exception:
                logger.error("EXCEPTION IN Qt EVENT/slot:")
                logger.error(traceback.format_exc())
                return False

    try:
        from neurowings import MainWindow
        import neurowings.core.calculations as calc
        logger.info(f"Loaded neurowings.core.calculations from: {getattr(calc, '__file__', 'unknown')}")
        pts = [
            (1161.0, 2838.0),
            (1810.0, 2789.0),
            (1430.0, 2787.0),
            (1244.0, 2791.0),
            (1422.0, 2668.0),
            (1506.0, 2623.0),
            (1556.0, 2628.0),
            (1404.0, 2497.0),
        ]
        idx = calc.calculate_indices(pts)
        logger.info(f"SANITY 58WD: CI={idx['CI']:.12f} DsA={idx['DsA']:.12f} HI={idx['HI']:.12f} (ожидается DsA~-0.7288742363)")
    except Exception:
        logger.error("Ошибка импорта проекта:")
        logger.error(traceback.format_exc())
        sys.exit(1)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy") and hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    app = SafeApplication(sys.argv)
    app.setApplicationName("НейроКрылья")
    icon_path = _resolve_app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        window = MainWindow()
    except Exception:
        logger.error("Ошибка создания MainWindow:")
        logger.error(traceback.format_exc())
        sys.exit(1)

    window.show()
    code = app.exec_()
    logger.info(f"EXIT code: {code}")
    sys.exit(code)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.critical("FATAL ERROR:")
        logger.critical(traceback.format_exc())
        sys.exit(1)
