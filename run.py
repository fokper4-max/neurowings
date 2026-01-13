#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - RUN

Добавлено:
- авто-очистка __pycache__ и *.pyc/*.pyo при старте (в лог)
- вывод структуры проекта (дерево) в лог
- вывод реальных путей загруженных модулей (откуда импортировались)
- перехват исключений Qt-событий (чтобы приложение не закрывалось молча)
"""

import sys
import os
import shutil
import logging
import traceback
import platform
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "neurowings.log"

# Настройка логирования с обработкой ошибок
try:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
except (PermissionError, OSError) as e:
    # Fallback: только консольное логирование
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    print(f"Предупреждение: не удалось создать лог-файл {LOG_FILE}: {e}")

logger = logging.getLogger("NeuroWings")


def _log_startup():
    logger.info("=" * 100)
    logger.info("NeuroWings START")
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


def _clean_cache(base_dir: Path) -> None:
    removed_dirs = 0
    removed_files = 0
    errors = 0
    logger.info("CACHE CLEAN: START")

    skip_dirs = {".git", ".venv", "venv", "build", "dist", ".idea", ".vscode"}

    for root, dirs, files in os.walk(base_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if "__pycache__" in dirs:
            cache_dir = Path(root) / "__pycache__"
            try:
                shutil.rmtree(cache_dir, ignore_errors=False)
                removed_dirs += 1
                logger.info(f"Removed dir: {cache_dir.relative_to(base_dir)}")
            except Exception as e:
                errors += 1
                logger.error(f"Failed remove dir {cache_dir}: {e}")
            dirs.remove("__pycache__")

    for p in base_dir.rglob("*"):
        if p.is_file() and p.suffix in {".pyc", ".pyo"}:
            try:
                p.unlink()
                removed_files += 1
                logger.info(f"Removed file: {p.relative_to(base_dir)}")
            except Exception as e:
                errors += 1
                logger.error(f"Failed remove file {p}: {e}")

    logger.info(f"CACHE CLEAN: DONE (dirs={removed_dirs}, files={removed_files}, errors={errors})")


def _log_tree(base_dir: Path, max_depth: int = 25) -> None:
    logger.info("=" * 100)
    logger.info(f"PROJECT TREE (max_depth={max_depth})")
    logger.info(f"ROOT: {base_dir}")
    logger.info("-" * 100)

    def depth(p: Path) -> int:
        rel = p.relative_to(base_dir)
        return 0 if rel == Path(".") else len(rel.parts)

    paths = sorted(base_dir.rglob("*"), key=lambda x: (x.is_file(), str(x).lower()))
    for p in paths:
        d = depth(p)
        if d > max_depth:
            continue
        indent = "  " * d
        rel = p.relative_to(base_dir)
        if p.is_dir():
            logger.info(f"{indent}[D] {rel}/")
        else:
            try:
                size = p.stat().st_size
            except Exception:
                size = -1
            logger.info(f"{indent}[F] {rel} ({size} bytes)")

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


def main():
    _install_excepthook()
    _log_startup()

    # Очищаем только кеш neurowings (не всего BASE_DIR - там может быть PyTorch)
    neurowings_dir = BASE_DIR / "neurowings"
    if neurowings_dir.exists():
        _clean_cache(neurowings_dir)
        # Логируем только структуру neurowings, не всего проекта (иначе PyTorch = часы ожидания)
        _log_tree(neurowings_dir, max_depth=10)
    else:
        logger.warning(f"Директория neurowings не найдена: {neurowings_dir}")

    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QColor, QPalette
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

    # Импорт проекта
    try:
        from neurowings import MainWindow
        import neurowings.core.calculations as calc
        logger.info(f"Loaded neurowings.core.calculations from: {getattr(calc, '__file__', 'unknown')}")
        # Санити-чек DsA на контрольных точках из 58 WD.tps (первые 8 точек):
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
        logger.info(f"SANITY 58WD: CI={idx['CI']:.12f} DsA={idx['DsA']:.12f} HI={idx['HI']:.12f} (ожидается DsA≈-0.7288742363)")
    except Exception:
        logger.error("Ошибка импорта проекта:")
        logger.error(traceback.format_exc())
        sys.exit(1)

    # Приложение
    app = SafeApplication(sys.argv)
    app.setApplicationName("NeuroWings")

    try:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(palette)
    except Exception:
        logger.warning("Theme setup failed:")
        logger.warning(traceback.format_exc())

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
        main()
    except Exception:
        logger.critical("FATAL ERROR:")
        logger.critical(traceback.format_exc())
        sys.exit(1)
