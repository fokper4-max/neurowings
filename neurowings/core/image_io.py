"""Canonical EXIF-normalized RGB pixels shared by display and inference."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import numpy as np
from PIL import Image, ImageOps
from PyQt5.QtGui import QImage, QPixmap

_CACHE_LOCK = threading.RLock()
_PIXMAP_CACHE = OrderedDict()
_RGB_CACHE = OrderedDict()
_PIXMAP_CACHE_MAX = 8
_RGB_CACHE_MAX = 4


def set_pixmap_cache_max_items(max_items: int) -> None:
    """Установить максимальный размер LRU-кэша сканов в зависимости от объёма ОЗУ компьютера."""
    global _PIXMAP_CACHE_MAX, _RGB_CACHE_MAX
    with _CACHE_LOCK:
        _PIXMAP_CACHE_MAX = max(1, int(max_items))
        _RGB_CACHE_MAX = max(1, min(12, _PIXMAP_CACHE_MAX // 2))
        while len(_PIXMAP_CACHE) > _PIXMAP_CACHE_MAX:
            _PIXMAP_CACHE.popitem(last=False)
        while len(_RGB_CACHE) > _RGB_CACHE_MAX:
            _RGB_CACHE.popitem(last=False)


def _file_cache_key(path):
    p = Path(path)
    try:
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def read_rgb(path):
    key = _file_cache_key(path)
    if key is not None:
        with _CACHE_LOCK:
            if key in _RGB_CACHE:
                _RGB_CACHE.move_to_end(key)
                return _RGB_CACHE[key]

    with Image.open(str(path)) as image:
        rgb = np.array(ImageOps.exif_transpose(image).convert("RGB"))

    if key is not None and rgb is not None and rgb.size > 0:
        with _CACHE_LOCK:
            _RGB_CACHE[key] = rgb
            while len(_RGB_CACHE) > _RGB_CACHE_MAX:
                _RGB_CACHE.popitem(last=False)
    return rgb


def read_pixmap(path):
    key = _file_cache_key(path)
    if key is not None:
        with _CACHE_LOCK:
            if key in _PIXMAP_CACHE:
                _PIXMAP_CACHE.move_to_end(key)
                return _PIXMAP_CACHE[key]

    rgb = read_rgb(path)
    h, w = rgb.shape[:2]
    pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())

    if key is not None and not pixmap.isNull():
        with _CACHE_LOCK:
            _PIXMAP_CACHE[key] = pixmap
            while len(_PIXMAP_CACHE) > _PIXMAP_CACHE_MAX:
                _PIXMAP_CACHE.popitem(last=False)

    return pixmap


def image_size(path):
    with Image.open(str(path)) as image:
        w, h = image.size
        return (h, w) if image.getexif().get(274, 1) in (5, 6, 7, 8) else (w, h)


def preload_rgb_parallel(paths, max_workers: int = 4):
    """Параллельная предзагрузка RGB-растров в фоновых потоках для максимальной скорости."""
    target_paths = list(paths or [])[:max(1, _RGB_CACHE_MAX)]
    if not target_paths:
        return
    workers = max(1, min(int(max_workers), len(target_paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda p: _safe_read_rgb(p), target_paths))


def _safe_read_rgb(path):
    try:
        return read_rgb(path)
    except Exception:
        return None
