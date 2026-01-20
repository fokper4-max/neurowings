#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TPS I/O helpers.
Выделено из main_window для изоляции логики чтения/записи TPS.
Сохраняет формат WingsDig: запятая как разделитель, округление до целых с .00000, CRLF.
"""

from pathlib import Path
from typing import List

from .constants import NUM_POINTS
from .data_models import Wing, WingPoint


def load_tps_into_image(img_data, tps_path: Path) -> None:
    """
    Заполнить ImageData крыльями из TPS.
    Преобразует Y из TPS (счёт снизу) в экранные координаты (счёт сверху).
    """
    if not tps_path.exists():
        return

    # Обеспечиваем размеры изображения (для инверсии Y)
    if img_data.height == 0:
        try:
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(str(img_data.path))
            img_data.width = pixmap.width()
            img_data.height = pixmap.height()
        except Exception:
            return

    with open(tps_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f.readlines()]

    points = []
    i = 0
    while i < len(lines):
        if lines[i].upper().startswith('LM='):
            npoints = int(lines[i].split('=')[1])
            for j in range(1, npoints + 1):
                if i + j < len(lines):
                    coords = lines[i + j].replace(',', '.').split()
                    if len(coords) == 2:
                        try:
                            x, y_tps = float(coords[0]), float(coords[1])
                            # TPS/WingsDig: Y снизу; экран: сверху
                            y = img_data.height - y_tps
                            points.append((x, y))
                        except ValueError:
                            pass
            i += npoints
        i += 1

    # Формируем крылья
    img_data.wings = []
    for idx in range(0, len(points), NUM_POINTS):
        wing_pts = points[idx:idx + NUM_POINTS]
        if len(wing_pts) == NUM_POINTS:
            img_data.wings.append(Wing(points=[WingPoint(x=p[0], y=p[1]) for p in wing_pts]))


def save_tps_from_image(img_data, tps_path: Path) -> None:
    """
    Сохранить ImageData в TPS (WingsDig совместимый формат).
    """
    if not img_data.wings:
        return

    lines: List[str] = [f"LM={len(img_data.wings) * NUM_POINTS}"]

    for wing in img_data.wings:
        pts = wing.get_active_points()
        for px, py in pts:
            y_tps = img_data.height - py  # TPS/WingsDig: Y снизу
            px_rounded = round(px)
            y_tps_rounded = round(y_tps)
            coord_str = f"{px_rounded:.5f} {y_tps_rounded:.5f}".replace('.', ',')
            lines.append(coord_str)

    lines.append(f"IMAGE={img_data.path.name}")
    lines.append("ID=1")

    with open(tps_path, 'w', newline='', encoding='utf-8') as f:
        f.write('\r\n'.join(lines))
        f.write('\r\n')
