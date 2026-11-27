#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Воркер фоновой нарезки сверхбольших сканов на отдельные файлы семей.
"""

import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("NeuroWings")


class SplitWorker(QThread):
    """Фоновый воркер для неблокирующей нарезки сверхбольших сканов (432+ МП)."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        src_path: Path,
        regions: list,
        rotation_mode: str = "none",
        output_dir: Optional[Path] = None,
        wings: Optional[list] = None,
    ):
        super().__init__()
        self.src_path = Path(src_path)
        self.regions = list(regions)
        self.rotation_mode = rotation_mode
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.wings = list(wings) if wings is not None else None
        self._stop = False

    def stop(self):
        """Запросить остановку нарезки."""
        self._stop = True

    def run(self):
        """Выполнить нарезку областей в фоновом потоке."""
        if self._stop:
            self.finished.emit([])
            return

        try:
            from ..core.image_split import split_image_regions

            def _on_progress(idx: int, total: int, name: str) -> None:
                if not self._stop:
                    self.progress.emit(
                        idx, total, f"Сохранение области {idx} из {total}: {name}"
                    )

            created = split_image_regions(
                src_path=self.src_path,
                regions=self.regions,
                rotation_mode=self.rotation_mode,
                output_dir=self.output_dir,
                wings=self.wings,
                progress_cb=_on_progress,
                should_stop=lambda: self._stop,
            )
            if self._stop:
                self.finished.emit([])
                return
            self.finished.emit(created)
        except Exception as exc:
            logger.exception("Ошибка нарезки скана %s: %s", self.src_path, exc)
            self.error.emit(str(exc))
