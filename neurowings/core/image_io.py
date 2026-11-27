"""Canonical EXIF-normalized RGB pixels shared by display and inference."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Tuple

import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None

if TYPE_CHECKING:
    from PyQt5.QtGui import QPixmap

_CACHE_LOCK = threading.RLock()
_PIXMAP_CACHE = OrderedDict()
_RGB_CACHE = OrderedDict()
_DISPLAY_PIXMAP_CACHE = OrderedDict()
_PIXMAP_CACHE_MAX = 8
_RGB_CACHE_MAX = 4

_RGB_CACHE_MAX_PIXELS = 80_000_000
_PRELOAD_MAX_PIXELS = 60_000_000


def _get_qt_gui():
    """Ленивый импорт PyQt5.QtGui, чтобы не нарушать порядок импорта torch -> PyQt5."""
    from PyQt5.QtGui import QImage, QPixmap
    return QImage, QPixmap


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
        while len(_DISPLAY_PIXMAP_CACHE) > _PIXMAP_CACHE_MAX:
            _DISPLAY_PIXMAP_CACHE.popitem(last=False)


def _file_cache_key(path):
    p = Path(path)
    try:
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def evict_image_cache(path) -> None:
    """Безопасно удалить все кэшированные записи для указанного файла изображения."""
    p = Path(path)
    targets = {str(p)}
    try:
        targets.add(str(p.resolve()))
    except OSError:
        pass

    with _CACHE_LOCK:
        for cache in (_PIXMAP_CACHE, _RGB_CACHE):
            stale_keys = [
                k for k in cache.keys()
                if isinstance(k, tuple) and len(k) >= 1 and k[0] in targets
            ]
            for k in stale_keys:
                cache.pop(k, None)

        stale_display_keys = [
            k for k in _DISPLAY_PIXMAP_CACHE.keys()
            if (
                isinstance(k, tuple)
                and len(k) >= 1
                and isinstance(k[0], tuple)
                and len(k[0]) >= 1
                and k[0][0] in targets
            )
        ]
        for k in stale_display_keys:
            _DISPLAY_PIXMAP_CACHE.pop(k, None)


def clear_image_cache() -> None:
    """Полностью очистить все кэши изображений (RGB, полные и прокси QPixmap)."""
    with _CACHE_LOCK:
        _PIXMAP_CACHE.clear()
        _RGB_CACHE.clear()
        _DISPLAY_PIXMAP_CACHE.clear()


def read_rgb(path) -> np.ndarray:
    key = _file_cache_key(path)
    if key is not None:
        with _CACHE_LOCK:
            if key in _RGB_CACHE:
                _RGB_CACHE.move_to_end(key)
                return _RGB_CACHE[key]

    with Image.open(str(path)) as image:
        orient = image.getexif().get(274, 1)
        if orient != 1:
            image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        rgb = np.array(image)

    if (
        key is not None
        and rgb is not None
        and rgb.size > 0
        and (rgb.shape[0] * rgb.shape[1]) <= _RGB_CACHE_MAX_PIXELS
    ):
        with _CACHE_LOCK:
            _RGB_CACHE[key] = rgb
            while len(_RGB_CACHE) > _RGB_CACHE_MAX:
                _RGB_CACHE.popitem(last=False)
    return rgb


def read_preview_rgb(path, max_side: int = 2400) -> Tuple[np.ndarray, int, int]:
    """Быстро прочитать уменьшенную EXIF-нормализованную RGB-версию изображения.

    Возвращает кортеж (preview_rgb, orig_w, orig_h), где длинная сторона preview_rgb
    не превышает max_side. Для крупных JPEG используется image.draft для ускорения.
    """
    target_side = max(1, int(max_side))
    resampling = getattr(getattr(Image, "Resampling", Image), "BILINEAR")

    with Image.open(str(path)) as image:
        raw_w, raw_h = image.size
        orient = image.getexif().get(274, 1)
        orig_w, orig_h = (raw_h, raw_w) if orient in (5, 6, 7, 8) else (raw_w, raw_h)

        if image.format == "JPEG" and max(orig_w, orig_h) > target_side:
            try:
                image.draft("RGB", (target_side, target_side))
            except Exception:
                pass

        if orient != 1:
            image = ImageOps.exif_transpose(image)

        if max(image.size) > target_side:
            image.thumbnail((target_side, target_side), resampling)

        if image.mode != "RGB":
            image = image.convert("RGB")

        preview_rgb = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))

    return preview_rgb, int(orig_w), int(orig_h)


def read_pixmap(path) -> "QPixmap":
    key = _file_cache_key(path)
    if key is not None:
        with _CACHE_LOCK:
            if key in _PIXMAP_CACHE:
                _PIXMAP_CACHE.move_to_end(key)
                return _PIXMAP_CACHE[key]

    rgb = read_rgb(path)
    h, w = rgb.shape[:2]
    QImage, QPixmap = _get_qt_gui()
    pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())

    if key is not None and not pixmap.isNull():
        with _CACHE_LOCK:
            _PIXMAP_CACHE[key] = pixmap
            while len(_PIXMAP_CACHE) > _PIXMAP_CACHE_MAX:
                _PIXMAP_CACHE.popitem(last=False)

    return pixmap


def read_pixmap_for_display(
    path,
    max_display_side: int = 6000,
    megapixels_threshold: int = 45_000_000,
) -> Tuple["QPixmap", int, int, float, float]:
    """Прочитать QPixmap для отображения на холсте с прокси-масштабированием гигантских сканов.

    Для обычных изображений (<= megapixels_threshold и <= max_display_side) возвращает
    обычный read_pixmap и масштаб (1.0, 1.0) со 100% обратной совместимостью.
    Для гигантских сканов возвращает уменьшенный QPixmap, оригинальные размеры (orig_w, orig_h)
    и коэффициенты пересчёта (scale_x, scale_y) из пикселей прокси в пиксели оригинала.
    """
    max_side = max(1, int(max_display_side))
    orig_w, orig_h = image_size(path)

    if (orig_w * orig_h) <= megapixels_threshold and max(orig_w, orig_h) <= max_side:
        pm = read_pixmap(path)
        return pm, pm.width(), pm.height(), 1.0, 1.0

    file_key = _file_cache_key(path)
    cache_key = (file_key, max_side) if file_key is not None else None
    if cache_key is not None:
        with _CACHE_LOCK:
            if cache_key in _DISPLAY_PIXMAP_CACHE:
                _DISPLAY_PIXMAP_CACHE.move_to_end(cache_key)
                cached_pm, cached_w, cached_h = _DISPLAY_PIXMAP_CACHE[cache_key]
                return (
                    cached_pm,
                    cached_w,
                    cached_h,
                    cached_w / max(1, cached_pm.width()),
                    cached_h / max(1, cached_pm.height()),
                )

    preview_rgb, orig_w, orig_h = read_preview_rgb(path, max_side=max_side)
    ph, pw = preview_rgb.shape[:2]
    QImage, QPixmap = _get_qt_gui()
    pixmap = QPixmap.fromImage(
        QImage(preview_rgb.data, pw, ph, preview_rgb.strides[0], QImage.Format_RGB888).copy()
    )

    if cache_key is not None and not pixmap.isNull():
        with _CACHE_LOCK:
            _DISPLAY_PIXMAP_CACHE[cache_key] = (pixmap, orig_w, orig_h)
            while len(_DISPLAY_PIXMAP_CACHE) > _PIXMAP_CACHE_MAX:
                _DISPLAY_PIXMAP_CACHE.popitem(last=False)

    return (
        pixmap,
        orig_w,
        orig_h,
        orig_w / max(1, pixmap.width()),
        orig_h / max(1, pixmap.height()),
    )


def image_size(path) -> Tuple[int, int]:
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
        list(pool.map(_safe_preload_rgb, target_paths))


def _safe_preload_rgb(path):
    try:
        w, h = image_size(path)
        if w * h > _PRELOAD_MAX_PIXELS:
            return None
        return read_rgb(path)
    except Exception:
        return None


def _safe_read_rgb(path):
    try:
        return read_rgb(path)
    except Exception:
        return None
