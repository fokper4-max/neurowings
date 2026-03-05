#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workers for update checks and downloads."""

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from ..core.update_manager import download_update, fetch_update_feed, is_newer_version


class UpdateCheckWorker(QThread):
    """Check the update feed in the background."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, feed_url: str, current_version: str):
        super().__init__()
        self.feed_url = feed_url
        self.current_version = current_version

    def run(self):
        try:
            info = fetch_update_feed(self.feed_url)
            info["update_available"] = is_newer_version(info["version"], self.current_version)
            self.finished.emit(info)
        except Exception as exc:
            self.error.emit(str(exc))


class UpdateDownloadWorker(QThread):
    """Download the update EXE in the background."""

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, info: dict, destination: Path):
        super().__init__()
        self.info = info
        self.destination = Path(destination)

    def run(self):
        try:
            path = download_update(self.info, self.destination, progress_callback=self.progress.emit)
            self.finished.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))
