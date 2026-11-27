#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Автоматическое разделение многосемейных сканов и поворот кропов.

Модуль намеренно не импортирует PyQt5, чтобы сохранять независимость ядра
и не нарушать порядок импорта torch до PyQt5.
"""

from __future__ import annotations

import copy
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

from .data_models import BBox, Wing, WingPoint
from .image_io import read_preview_rgb

Image.MAX_IMAGE_PIXELS = None

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

try:
    from scipy import ndimage as _scipy_ndimage  # type: ignore
except Exception:
    _scipy_ndimage = None


ROTATION_OPTIONS: List[Tuple[str, str]] = [
    ("none", "Без поворота (0°)"),
    ("ccw90", "↺ Повернуть 90° влево"),
    ("cw90", "↻ Повернуть 90° вправо"),
    ("rot180", "🔄 Развернуть 180°"),
]

_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

_FORBIDDEN_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WHITESPACE_RE = re.compile(r"\s+")
_MULTI_UNDERSCORE_RE = re.compile(r"_+")


@dataclass
class SplitRegion:
    """Прямоугольная область разбиения изображения в координатах оригинала."""
    x1: float
    y1: float
    x2: float
    y2: float
    name: str = ""

    def width(self) -> float:
        return max(0.0, float(self.x2) - float(self.x1))

    def height(self) -> float:
        return max(0.0, float(self.y2) - float(self.y1))

    def normalized(self, max_w: int, max_h: int) -> Tuple[int, int, int, int]:
        """Упорядочить координаты и ограничить их границами [0..max_w, 0..max_h]."""
        w_lim = max(0, int(max_w))
        h_lim = max(0, int(max_h))
        lo_x = min(float(self.x1), float(self.x2))
        hi_x = max(float(self.x1), float(self.x2))
        lo_y = min(float(self.y1), float(self.y2))
        hi_y = max(float(self.y1), float(self.y2))

        ix1 = max(0, min(w_lim, int(round(lo_x))))
        iy1 = max(0, min(h_lim, int(round(lo_y))))
        ix2 = max(0, min(w_lim, int(round(hi_x))))
        iy2 = max(0, min(h_lim, int(round(hi_y))))
        return ix1, iy1, ix2, iy2


def sanitize_region_name(name: str, fallback: str = "Семья") -> str:
    """Привести имя области к безопасному для Windows и macOS имени файла.

    Убирает запрещённые и управляющие символы, схлопывает пробелы в '_',
    защищает от зарезервированных имён Windows и ограничивает длину до 60 символов.
    Сохраняет кириллицу, латиницу, цифры, '№', '-', '_'.
    """
    def _clean(raw: str) -> str:
        s = _FORBIDDEN_FILENAME_RE.sub("", str(raw or ""))
        s = _WHITESPACE_RE.sub("_", s)
        s = _MULTI_UNDERSCORE_RE.sub("_", s)
        s = s.strip(" ._")
        if len(s) > 60:
            s = s[:60].rstrip(" ._")
        return s

    cleaned = _clean(name)
    if not cleaned:
        cleaned = _clean(fallback) or "Семья"

    base_upper = cleaned.split(".", 1)[0].upper()
    if base_upper in _WINDOWS_RESERVED_NAMES:
        if "." in cleaned:
            head, tail = cleaned.split(".", 1)
            cleaned = f"{head}_1.{tail}"
            if len(cleaned) > 60:
                cleaned = cleaned[:60].rstrip(" ._")
        else:
            cleaned = f"{cleaned}_1"
            if len(cleaned) > 60:
                cleaned = cleaned[:58].rstrip(" ._") + "_1"

    return cleaned


def generate_grid_regions(
    width: int,
    height: int,
    count: int,
    orientation: str = "horizontal",
) -> List[SplitRegion]:
    """Разбить область (width, height) на count равных полос или колонок (1..30)."""
    n = max(1, min(30, int(count)))
    w = max(1, int(width))
    h = max(1, int(height))
    orient = str(orientation or "horizontal").strip().lower()

    regions: List[SplitRegion] = []
    if orient == "vertical":
        for i in range(n):
            x1 = int(round(i * w / n))
            x2 = int(round((i + 1) * w / n))
            regions.append(SplitRegion(x1=float(x1), y1=0.0, x2=float(x2), y2=float(h), name=f"Семья_{i + 1}"))
    else:
        for i in range(n):
            y1 = int(round(i * h / n))
            y2 = int(round((i + 1) * h / n))
            regions.append(SplitRegion(x1=0.0, y1=float(y1), x2=float(w), y2=float(y2), name=f"Семья_{i + 1}"))
    return regions


def _clean_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Морфологическая очистка мелкого шума и пыли на бинарной маске контента."""
    if cv2 is not None:
        mask_u8 = (mask.astype(np.uint8)) * 255
        kernel = np.ones((5, 5), dtype=np.uint8)
        opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel)
        return opened > 0

    if _scipy_ndimage is not None:
        return _scipy_ndimage.binary_opening(mask, structure=np.ones((5, 5), dtype=bool))

    # Fallback на чистом numpy: 5x5 сглаживание с порогом (удаляет изолированные точки)
    pad = np.pad(mask.astype(np.uint8), 2, mode="constant", constant_values=0)
    h, w = mask.shape
    acc = np.zeros((h, w), dtype=np.uint8)
    for dy in range(5):
        for dx in range(5):
            acc += pad[dy:dy + h, dx:dx + w]
    return mask & (acc >= 12)


def _extract_profile_bands(profile: np.ndarray, side: int) -> List[Tuple[int, int]]:
    """Найти устойчивые полосы контента вдоль 1D-профиля плотности и расширить их в зазоры."""
    if side <= 0 or profile.size == 0:
        return []

    win = max(3, int(round(side * 0.008)))
    kernel = np.ones(win, dtype=np.float32) / float(win)
    smoothed = np.convolve(profile.astype(np.float32), kernel, mode="same")

    nonzero = smoothed[smoothed > 0.002]
    peak = float(np.percentile(nonzero, 95)) if nonzero.size > 0 else 0.0
    if peak <= 0.004:
        return []

    # Адаптивный порог отсекает одиночные задние крылышки и пыль в межсемейных зазорах
    thr = max(0.004, min(0.05, peak * 0.08))
    active = smoothed > thr

    raw_segs: List[List[int]] = []
    in_seg = False
    start = 0
    for idx, flag in enumerate(active):
        if flag and not in_seg:
            start = idx
            in_seg = True
        elif not flag and in_seg:
            raw_segs.append([start, idx])
            in_seg = False
    if in_seg:
        raw_segs.append([start, int(active.size)])

    if not raw_segs:
        return []

    # Отбрасываем короткие малоплотные выбросы ДО слияния, чтобы они не склеивали семьи
    strong_segs: List[List[int]] = []
    for a, b in raw_segs:
        seg_len = b - a
        seg_peak = float(smoothed[a:b].max()) if b > a else 0.0
        if seg_len < side * 0.02 and seg_peak < peak * 0.25:
            continue
        strong_segs.append([a, b])

    if not strong_segs:
        strong_segs = raw_segs

    # Объединяем сегменты, разделённые узким внутрисемейным зазором (< 2.2% стороны)
    gap_limit = side * 0.022
    merged: List[List[int]] = []
    for a, b in strong_segs:
        if merged and (a - merged[-1][1]) < gap_limit:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    # Отфильтровываем мелкие выбросы (< 4.5% стороны)
    filtered = [(a, b) for a, b in merged if (b - a) >= side * 0.045]
    if not filtered:
        return []

    # Расширяем границы каждой полосы в середину белого зазора (не более 20% её высоты)
    expanded: List[Tuple[int, int]] = []
    for idx, (a, b) in enumerate(filtered):
        band_size = b - a
        max_pad = int(round(band_size * 0.20))

        if idx > 0:
            prev_b = filtered[idx - 1][1]
            pad_before = min(max_pad, max(0, (a - prev_b) // 2))
        else:
            pad_before = min(max_pad, a)

        if idx + 1 < len(filtered):
            next_a = filtered[idx + 1][0]
            pad_after = min(max_pad, max(0, (next_a - b) // 2))
        else:
            pad_after = min(max_pad, max(0, side - b))

        ea = max(0, a - pad_before)
        eb = min(side, b + pad_after)
        expanded.append((ea, eb))

    return expanded


def _region_color_stats(
    rgb: np.ndarray,
    clean_mask: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> Dict[str, float]:
    """Оценить цветовые характеристики контента внутри прямоугольника (этикетка vs крылья)."""
    sub_mask = clean_mask[y1:y2, x1:x2]
    count = int(sub_mask.sum())
    area = max(1, (y2 - y1) * (x2 - x1))
    if count == 0:
        return {
            "density": 0.0,
            "mean_r": 255.0,
            "mean_g": 255.0,
            "mean_b": 255.0,
            "blue_frac": 0.0,
            "warm_frac": 0.0,
            "is_label_like": 0.0,
        }

    pixels = rgb[y1:y2, x1:x2][sub_mask].astype(np.int16)
    r = pixels[:, 0]
    g = pixels[:, 1]
    b = pixels[:, 2]
    mean_r = float(r.mean())
    mean_g = float(g.mean())
    mean_b = float(b.mean())
    blue_frac = float((b > (r + 15)).mean())
    warm_frac = float((r > (b + 8)).mean())
    is_label = (blue_frac > 0.55) or (mean_b > mean_r + 12.0 and warm_frac < 0.20)
    return {
        "density": float(count) / float(area),
        "mean_r": mean_r,
        "mean_g": mean_g,
        "mean_b": mean_b,
        "blue_frac": blue_frac,
        "warm_frac": warm_frac,
        "is_label_like": 1.0 if is_label else 0.0,
    }


def _is_label_plus_wings_split(
    bands: List[Tuple[int, int]],
    side: int,
    rgb: np.ndarray,
    clean_mask: np.ndarray,
    axis: str,
) -> bool:
    """Проверить, не является ли 2-полосное разбиение парой 'узкая этикетка + блок крыльев'."""
    if len(bands) != 2 or side <= 0:
        return False

    h, w = clean_mask.shape
    widths = [b - a for a, b in bands]
    narrow_idx = 0 if widths[0] <= widths[1] else 1
    narrow_w = widths[narrow_idx]
    wide_w = widths[1 - narrow_idx]

    if narrow_w >= side * 0.30:
        return False

    a, b = bands[narrow_idx]
    if axis == "x":
        stats = _region_color_stats(rgb, clean_mask, a, 0, b, h)
    else:
        stats = _region_color_stats(rgb, clean_mask, 0, a, w, b)

    if stats["is_label_like"] > 0.5:
        return True
    if wide_w / max(1, narrow_w) >= 2.1 and stats["warm_frac"] < 0.30:
        return True
    return False


def _can_split_secondary_columns(
    sec_bands: List[Tuple[int, int]],
    side: int,
    rgb: np.ndarray,
    clean_mask: np.ndarray,
    axis: str,
) -> bool:
    """Проверить, можно ли разделить лист дополнительно на 2-3 равные колонки/строки с крыльями."""
    if not (2 <= len(sec_bands) <= 3) or side <= 0:
        return False

    widths = [b - a for a, b in sec_bands]
    min_w = min(widths)
    max_w = max(widths)
    if min_w < side * 0.22:
        return False
    if max_w > min_w * 2.0:
        return False

    h, w = clean_mask.shape
    for a, b in sec_bands:
        if axis == "x":
            st = _region_color_stats(rgb, clean_mask, a, 0, b, h)
        else:
            st = _region_color_stats(rgb, clean_mask, 0, a, w, b)
        if st["is_label_like"] > 0.5:
            return False
        if st["mean_r"] < st["mean_b"] - 5.0:
            return False
        if st["warm_frac"] < 0.35 or st["density"] < 0.015:
            return False
    return True


def _connected_components(clean_mask: np.ndarray) -> List[Tuple[int, int, int, int, int, np.ndarray]]:
    """Вернуть список (x, y, bw, bh, area, local_mask) для связных компонент маски."""
    results: List[Tuple[int, int, int, int, int, np.ndarray]] = []
    h, w = clean_mask.shape
    frame_area = max(1, h * w)
    min_area = max(20, int(frame_area * 0.0001))
    max_area = int(frame_area * 0.03)

    if cv2 is not None:
        num, labels, stats, _ = cv2.connectedComponentsWithStats(
            clean_mask.astype(np.uint8), connectivity=8
        )
        for comp_id in range(1, num):
            x, y, bw, bh, area = (int(v) for v in stats[comp_id])
            if area < min_area or area > max_area:
                continue
            aspect = max(bw, bh) / float(max(1, min(bw, bh)))
            if not (1.6 <= aspect <= 5.5):
                continue
            sub_mask = labels[y:y + bh, x:x + bw] == comp_id
            results.append((x, y, bw, bh, area, sub_mask))
        return results

    if _scipy_ndimage is not None:
        labeled, num = _scipy_ndimage.label(clean_mask, structure=np.ones((3, 3), dtype=int))
        slices = _scipy_ndimage.find_objects(labeled)
        for comp_id, sl in enumerate(slices, start=1):
            if sl is None:
                continue
            ys, xs = sl
            y, x = int(ys.start), int(xs.start)
            bh, bw = int(ys.stop - ys.start), int(xs.stop - xs.start)
            aspect = max(bw, bh) / float(max(1, min(bw, bh)))
            if not (1.6 <= aspect <= 5.5):
                continue
            sub_mask = labeled[ys, xs] == comp_id
            area = int(sub_mask.sum())
            if area < min_area or area > max_area:
                continue
            results.append((x, y, bw, bh, area, sub_mask))
        return results

    return results


def _detect_wing_orientation(
    rgb: np.ndarray,
    gray: np.ndarray,
    clean_mask: np.ndarray,
) -> Tuple[str, str]:
    """Определить рекомендованный поворот и текстовую подсказку по форме крыльев."""
    components = _connected_components(clean_mask)
    if not components:
        return "none", ""

    vertical_metrics: List[Tuple[float, float, float, float, float]] = []
    horizontal_metrics: List[Tuple[float, float, float, float]] = []
    ratios_bh_bw: List[float] = []

    for x, y, bw, bh, _area, sub_mask in components:
        sub_rgb = rgb[y:y + bh, x:x + bw][sub_mask].astype(np.float32)
        if sub_rgb.size == 0:
            continue
        mean_r = float(sub_rgb[:, 0].mean())
        mean_b = float(sub_rgb[:, 2].mean())
        # Отсекаем синие элементы этикеток
        if mean_r < mean_b - 10.0:
            continue

        ratios_bh_bw.append(float(bh) / float(max(1, bw)))
        sub_gray = gray[y:y + bh, x:x + bw]

        if bh > bw:
            q = max(1, bh // 4)
            top_m = sub_mask[:q, :]
            bot_m = sub_mask[-q:, :]
            if not top_m.any() or not bot_m.any():
                continue
            top_w = float(top_m.sum(axis=1).mean())
            bot_w = float(bot_m.sum(axis=1).mean())
            dark_top = float(sub_gray[:q, :][top_m].mean())
            dark_bot = float(sub_gray[-q:, :][bot_m].mean())

            pix_g = sub_gray[sub_mask]
            _ys, xs = np.where(sub_mask)
            dark_cut = float(np.percentile(pix_g, 35))
            dark_xs = xs[pix_g <= dark_cut]
            x_com_rel = float(dark_xs.mean()) / float(max(1, bw - 1)) if dark_xs.size else 0.5
            vertical_metrics.append((top_w, bot_w, dark_top, dark_bot, x_com_rel))
        else:
            q = max(1, bw // 4)
            left_m = sub_mask[:, :q]
            right_m = sub_mask[:, -q:]
            if not left_m.any() or not right_m.any():
                continue
            left_h = float(left_m.sum(axis=0).mean())
            right_h = float(right_m.sum(axis=0).mean())
            dark_left = float(sub_gray[:, :q][left_m].mean())
            dark_right = float(sub_gray[:, -q:][right_m].mean())
            horizontal_metrics.append((left_h, right_h, dark_left, dark_right))

    if len(ratios_bh_bw) < 5:
        return "none", ""

    med_bh_bw = float(np.median(ratios_bh_bw))
    med_bw_bh = float(np.median([1.0 / max(1e-6, r) for r in ratios_bh_bw]))

    if med_bh_bw > 1.55 and len(vertical_metrics) >= 3:
        arr = np.asarray(vertical_metrics, dtype=np.float32)
        med_top_w = float(np.median(arr[:, 0]))
        med_bot_w = float(np.median(arr[:, 1]))
        med_dark_top = float(np.median(arr[:, 2]))
        med_dark_bot = float(np.median(arr[:, 3]))
        med_x_com = float(np.median(arr[:, 4]))

        # Основание крыла узкое и более тёмное; при основании сверху и костальной жилке справа
        # поворот 90 влево (ccw90) ставит основание слева и костальную жилку сверху.
        base_is_top = (
            (med_top_w < med_bot_w * 0.92)
            or (med_top_w <= med_bot_w * 1.05 and med_dark_top < med_dark_bot - 8.0)
            or (abs(med_top_w - med_bot_w) <= max(1.0, med_bot_w * 0.08) and med_x_com > 0.54)
        )
        if base_is_top:
            return (
                "ccw90",
                "Крылья ориентированы вертикально (основанием вверх) - рекомендуется поворот 90° влево.",
            )
        return (
            "cw90",
            "Крылья ориентированы вертикально (основанием вниз) - рекомендуется поворот 90° вправо.",
        )

    if med_bw_bh > 1.55 and len(horizontal_metrics) >= 3:
        arr = np.asarray(horizontal_metrics, dtype=np.float32)
        med_left_h = float(np.median(arr[:, 0]))
        med_right_h = float(np.median(arr[:, 1]))
        med_dark_left = float(np.median(arr[:, 2]))
        med_dark_right = float(np.median(arr[:, 3]))

        base_is_right = (
            (med_right_h < med_left_h * 0.92)
            or (med_right_h <= med_left_h * 1.05 and med_dark_right < med_dark_left - 8.0)
        )
        if base_is_right:
            return (
                "rot180",
                "Крылья ориентированы горизонтально (основанием вправо) - рекомендуется разворот 180°.",
            )
        return (
            "none",
            "Крылья уже ориентированы горизонтально (основанием влево) - поворот не требуется.",
        )

    return "none", ""


def detect_family_regions(src_path: Path, min_bands: int = 2) -> Dict[str, object]:
    """Автоматически обнаружить полосы семей и оптимальный поворот крыльев на скане."""
    src_path = Path(src_path)
    rgb, orig_w, orig_h = read_preview_rgb(src_path, max_side=2400)
    prev_h, prev_w = rgb.shape[:2]

    gray = (
        0.299 * rgb[:, :, 0].astype(np.float32)
        + 0.587 * rgb[:, :, 1].astype(np.float32)
        + 0.114 * rgb[:, :, 2].astype(np.float32)
    )
    bg = float(np.percentile(gray, 90))
    thresh = max(120.0, bg - 22.0)
    mask = (gray < thresh) | (rgb.min(axis=2) < (thresh - 5.0))
    clean_mask = _clean_binary_mask(mask)

    y_bands = _extract_profile_bands(clean_mask.mean(axis=1), prev_h)
    x_bands = _extract_profile_bands(clean_mask.mean(axis=0), prev_w)

    # Не режем этикетку отдельно от блока крыльев
    valid_y = [] if _is_label_plus_wings_split(y_bands, prev_h, rgb, clean_mask, "y") else y_bands
    valid_x = [] if _is_label_plus_wings_split(x_bands, prev_w, rgb, clean_mask, "x") else x_bands

    min_b = max(1, int(min_bands))
    has_y = len(valid_y) >= min_b
    has_x = len(valid_x) >= min_b

    preview_boxes: List[Tuple[int, int, int, int]] = []
    axis = "none"

    if has_y and (not has_x or len(valid_y) >= len(valid_x)):
        if _can_split_secondary_columns(valid_x, prev_w, rgb, clean_mask, "x"):
            axis = "grid"
            for x1, x2 in valid_x:
                for y1, y2 in valid_y:
                    preview_boxes.append((x1, y1, x2, y2))
        else:
            axis = "horizontal"
            for y1, y2 in valid_y:
                preview_boxes.append((0, y1, prev_w, y2))
    elif has_x:
        if _can_split_secondary_columns(valid_y, prev_h, rgb, clean_mask, "y"):
            axis = "grid"
            for x1, x2 in valid_x:
                for y1, y2 in valid_y:
                    preview_boxes.append((x1, y1, x2, y2))
        else:
            axis = "vertical"
            for x1, x2 in valid_x:
                preview_boxes.append((x1, 0, x2, prev_h))
    else:
        axis = "none"
        preview_boxes.append((0, 0, prev_w, prev_h))

    sx = float(orig_w) / float(max(1, prev_w))
    sy = float(orig_h) / float(max(1, prev_h))

    regions: List[SplitRegion] = []
    for idx, (bx1, by1, bx2, by2) in enumerate(preview_boxes, start=1):
        ox1 = max(0, min(orig_w, int(round(bx1 * sx))))
        oy1 = max(0, min(orig_h, int(round(by1 * sy))))
        ox2 = max(0, min(orig_w, int(round(bx2 * sx))))
        oy2 = max(0, min(orig_h, int(round(by2 * sy))))
        regions.append(
            SplitRegion(
                x1=float(ox1),
                y1=float(oy1),
                x2=float(ox2),
                y2=float(oy2),
                name=f"Семья_{idx}",
            )
        )

    suggested_rotation, orientation_hint = _detect_wing_orientation(rgb, gray, clean_mask)
    if orientation_hint and not orientation_hint.endswith("."):
        orientation_hint = f"{orientation_hint}."

    return {
        "regions": regions,
        "axis": axis,
        "suggested_rotation": suggested_rotation,
        "orientation_hint": orientation_hint,
        "image_size": (int(orig_w), int(orig_h)),
    }


def _transform_point(
    x: float,
    y: float,
    x1: int,
    y1: int,
    cw: int,
    ch: int,
    rotation_mode: str,
) -> Tuple[float, float]:
    lx = float(x) - float(x1)
    ly = float(y) - float(y1)
    if rotation_mode == "ccw90":
        return ly, float(cw) - lx
    if rotation_mode == "cw90":
        return float(ch) - ly, lx
    if rotation_mode == "rot180":
        return float(cw) - lx, float(ch) - ly
    return lx, ly


def _transfer_wings_for_region(
    wings: Optional[List[Wing]],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    rotation_mode: str,
) -> List[Wing]:
    if not wings:
        return []

    cw = x2 - x1
    ch = y2 - y1
    new_w, new_h = (ch, cw) if rotation_mode in ("ccw90", "cw90") else (cw, ch)
    max_x = float(max(0, new_w - 1))
    max_y = float(max(0, new_h - 1))
    transferred: List[Wing] = []

    for wing in wings:
        cx, cy = wing.get_center()
        if not (x1 <= cx <= x2 and y1 <= cy <= y2):
            continue

        cloned = copy.deepcopy(wing)
        seen_point_ids = set()
        for attr in ("points", "points_yolo", "points_stage1", "points_stage2", "points_gt"):
            pts: List[WingPoint] = getattr(cloned, attr, None)
            if not pts:
                continue
            for pt in pts:
                pt_id = id(pt)
                if pt_id in seen_point_ids:
                    continue
                seen_point_ids.add(pt_id)
                if math.isfinite(pt.x) and math.isfinite(pt.y):
                    nx, ny = _transform_point(pt.x, pt.y, x1, y1, cw, ch, rotation_mode)
                    pt.x = max(0.0, min(max_x, nx))
                    pt.y = max(0.0, min(max_y, ny))

        if cloned.bbox is not None:
            bx1, by1 = _transform_point(cloned.bbox.x1, cloned.bbox.y1, x1, y1, cw, ch, rotation_mode)
            bx2, by2 = _transform_point(cloned.bbox.x2, cloned.bbox.y2, x1, y1, cw, ch, rotation_mode)
            bx1 = max(0.0, min(max_x, bx1))
            by1 = max(0.0, min(max_y, by1))
            bx2 = max(0.0, min(max_x, bx2))
            by2 = max(0.0, min(max_y, by2))
            cloned.bbox = BBox(
                x1=min(bx1, bx2),
                y1=min(by1, by2),
                x2=max(bx1, bx2),
                y2=max(by1, by2),
            )

        if cloned.analysis is not None:
            try:
                cloned.analyze(image_height=new_h, image_width=new_w)
            except Exception:
                cloned.analysis = None

        transferred.append(cloned)

    return transferred


def _valid_dpi(dpi_value) -> Optional[Tuple[float, float]]:
    if isinstance(dpi_value, (tuple, list)) and len(dpi_value) >= 2:
        try:
            dx = float(dpi_value[0])
            dy = float(dpi_value[1])
            if math.isfinite(dx) and math.isfinite(dy) and dx > 0 and dy > 0:
                return (dx, dy)
        except (TypeError, ValueError):
            return None
    return None


def _build_save_kwargs(ext_lower: str, dpi: Optional[Tuple[float, float]]) -> Dict[str, object]:
    kwargs: Dict[str, object] = {}
    if ext_lower in (".jpg", ".jpeg"):
        kwargs["format"] = "JPEG"
        kwargs["quality"] = 95
        kwargs["subsampling"] = 0
    elif ext_lower == ".png":
        kwargs["format"] = "PNG"
    elif ext_lower in (".tif", ".tiff"):
        kwargs["format"] = "TIFF"
    elif ext_lower == ".bmp":
        kwargs["format"] = "BMP"
    elif ext_lower == ".webp":
        kwargs["format"] = "WEBP"
        kwargs["quality"] = 95

    if dpi is not None and ext_lower != ".webp":
        kwargs["dpi"] = dpi
    return kwargs


def _apply_rotation(crop: Image.Image, rotation_mode: str) -> Image.Image:
    transpose_enum = getattr(Image, "Transpose", Image)
    if rotation_mode == "ccw90":
        return crop.transpose(transpose_enum.ROTATE_90)
    if rotation_mode == "cw90":
        return crop.transpose(transpose_enum.ROTATE_270)
    if rotation_mode == "rot180":
        return crop.transpose(transpose_enum.ROTATE_180)
    return crop


def split_image_regions(
    src_path: Path,
    regions: List[SplitRegion],
    rotation_mode: str = "none",
    output_dir: Optional[Path] = None,
    wings: Optional[List[Wing]] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> List[Tuple[Path, List[Wing]]]:
    """Разрезать исходный скан по списку SplitRegion с поворотом и переносом разметки."""
    Image.MAX_IMAGE_PIXELS = None
    src = Path(src_path)
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    rot_mode = rotation_mode if rotation_mode in ("none", "ccw90", "cw90", "rot180") else "none"
    suffix = src.suffix if src.suffix else ".jpg"
    ext_lower = suffix.lower()

    results: List[Tuple[Path, List[Wing]]] = []
    used_paths = set()
    total = len(regions)

    with Image.open(str(src)) as raw_im:
        dpi = _valid_dpi(raw_im.info.get("dpi"))
        orient = raw_im.getexif().get(274, 1)
        im = ImageOps.exif_transpose(raw_im) if orient != 1 else raw_im
        orig_w, orig_h = im.size
        save_kwargs = _build_save_kwargs(ext_lower, dpi)

        for idx, reg in enumerate(regions, start=1):
            if should_stop is not None and should_stop():
                break
            x1, y1, x2, y2 = reg.normalized(orig_w, orig_h)
            if (x2 - x1) < 15 or (y2 - y1) < 15:
                if progress_cb is not None:
                    progress_cb(idx, total, "")
                continue

            crop = im.crop((x1, y1, x2, y2))
            crop = _apply_rotation(crop, rot_mode)
            if ext_lower in (".jpg", ".jpeg") and crop.mode not in ("RGB", "L"):
                crop = crop.convert("RGB")

            label = sanitize_region_name(reg.name, fallback=f"семья_{idx:02d}")
            base_stem = f"{src.stem}_{label}"
            out_path = out_dir / f"{base_stem}{suffix}"
            counter = 2
            while out_path.exists() or out_path in used_paths:
                out_path = out_dir / f"{base_stem}_{counter}{suffix}"
                counter += 1
            used_paths.add(out_path)

            fd, tmp_name = tempfile.mkstemp(prefix=".split_tmp_", suffix=suffix, dir=str(out_dir))
            os.close(fd)
            try:
                crop.save(tmp_name, **save_kwargs)
                os.replace(tmp_name, str(out_path))
            except Exception:
                try:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)
                except OSError:
                    pass
                raise
            finally:
                crop.close()

            transferred_wings = _transfer_wings_for_region(wings, x1, y1, x2, y2, rot_mode)
            results.append((out_path, transferred_wings))

            if progress_cb is not None:
                progress_cb(idx, total, out_path.name)

        if im is not raw_im:
            im.close()

    return results
