#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Константы и настройки
Обновлено для models_trained_2025_01_19
"""

from PyQt5.QtGui import QColor

# =============================================================================
# ОСНОВНЫЕ КОНСТАНТЫ
# =============================================================================

APP_NAME = "НейроКрылья"
APP_VERSION = "2.2.0"  # Модульная архитектура, PDF-паспорт, 2D-карта породности и UX для пасечника
APP_AUTHOR = "Дмитрий Дубровский"
APP_MAX_URL = "https://max.ru/u/f9LHodD0cOIbZcReW1B_n2lDumCww_8mo2-Kjv_3dok65ZPHlJWUNkq-MVo"
APP_TELEGRAM_LABEL = "@NeuroWings_bee"
APP_TELEGRAM_URL = "https://t.me/NeuroWings_bee"
APP_UPDATE_FEED_URL = "https://193-124-117-175.nip.io/downloads/neurowings/update-feed.json"
NUM_POINTS = 8

# =============================================================================
# ЦВЕТА
# =============================================================================

COLOR_NORMAL = QColor(255, 0, 0)
COLOR_PROBLEM = QColor(255, 165, 0)
COLOR_SELECTED = QColor(0, 255, 0)
COLOR_WING_LABEL = QColor(255, 255, 0)
COLOR_WING_OK = QColor(0, 200, 0)
COLOR_WING_PROBLEM = QColor(255, 100, 100)

# Цвета для разных моделей точек
COLOR_YOLO = QColor(255, 0, 0)      # Красный
COLOR_STAGE1 = QColor(0, 0, 255)    # Синий
COLOR_STAGE2 = QColor(128, 0, 255)  # Фиолетовый
COLOR_GT = QColor(0, 255, 0)        # Зелёный (Ground Truth)

# =============================================================================
# НАСТРОЙКИ ОТОБРАЖЕНИЯ
# =============================================================================

DEFAULT_POINT_RADIUS = 1  # Радиус 1 px = диаметр точки 2 px (не перекрывает жилки крыла)
DEFAULT_TEXT_SIZE = 7

# =============================================================================
# ПОРОДНЫЕ ДИАПАЗОНЫ (из Excel)
# =============================================================================

BREEDS = {
    'Mellifera':  {'CI': (0.76, 2.16), 'DsA': (-15.31, 0.00), 'HI': (0.616, 0.923)},
    'Caucasica':  {'CI': (1.73, 2.75), 'DsA': (-2.88, 2.88),  'HI': (0.704, 1.027)},
    'Ligustica':  {'CI': (2.00, 3.29), 'DsA': (0.00, 4.81),   'HI': (0.923, 1.206)},
    'Carnica':    {'CI': (2.16, 5.67), 'DsA': (0.00, 12.39),  'HI': (0.923, 1.420)},
    'Carpatica':  {'CI': (2.30, 3.00), 'DsA': (0.00, 10.00),  'HI': (0.850, 1.150)},
    'Macedonica': {'CI': (2.00, 2.80), 'DsA': (-2.00, 5.00),  'HI': (0.850, 1.100)},
}

CLASSIC_BREEDS = ('Mellifera', 'Caucasica', 'Ligustica', 'Carnica')

BREED_NAMES_RU = {
    'Mellifera': 'Среднерусская (Mellifera)',
    'Carnica': 'Карника (Carnica)',
    'Carpatica': 'Карпатка (Carpatica)',
    'Caucasica': 'Кавказская (Caucasica)',
    'Ligustica': 'Итальянская (Ligustica)',
    'Macedonica': 'Степная (Macedonica)',
}

BREED_SHORT_NAMES_RU = {
    'Mellifera': 'Среднерусская',
    'Carnica': 'Карника',
    'Carpatica': 'Карпатка',
    'Caucasica': 'Кавказская',
    'Ligustica': 'Итальянская',
    'Macedonica': 'Степная',
}

BREED_COLORS_HEX = {
    'Mellifera': '#e03131',
    'Caucasica': '#2f9e44',
    'Ligustica': '#1971c2',
    'Carnica': '#9c36b5',
    'Carpatica': '#f08c00',
    'Macedonica': '#0ca678',
}

ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp')


def format_breed_ru(breed_key, short: bool = False) -> str:
    """Форматировать ключ породы (или список пород) на понятном русском языке."""
    if not breed_key:
        return "Помесь / вне стандарта" if short else "Помесь / Бакфаст (вне стандарта)"
    if isinstance(breed_key, (list, tuple)):
        valid = [b for b in breed_key if b and b != "—"]
        if not valid:
            return "Помесь / вне стандарта" if short else "Помесь / Бакфаст (вне стандарта)"
        mapping = BREED_SHORT_NAMES_RU if short else BREED_NAMES_RU
        return ", ".join(mapping.get(b, str(b)) for b in valid)
    s = str(breed_key).strip()
    if not s or s in ("—", "-", "None", "Помесь / Бакфаст (вне стандарта)"):
        return "Помесь / вне стандарта" if short else "Помесь / Бакфаст (вне стандарта)"
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        mapping = BREED_SHORT_NAMES_RU if short else BREED_NAMES_RU
        return ", ".join(mapping.get(p, p) for p in parts)
    mapping = BREED_SHORT_NAMES_RU if short else BREED_NAMES_RU
    return mapping.get(s, s)

# Точки, используемые для расчёта каждого индекса
INDEX_POINTS = {
    'CI': [4, 5, 6],
    'DsA': [0, 1, 2, 7],
    'HI': [2, 3, 4, 6],
}

# Перестановка точек YOLO -> WingsDig
YOLO_TO_WINGSDIG = [0, 1, 3, 2, 4, 5, 6, 7]

# Алиас для совместимости с calculations.py
BREED_RANGES = BREEDS

# =============================================================================
# НАСТРОЙКИ ОБРАБОТКИ ИЗОБРАЖЕНИЙ
# =============================================================================

# YOLO Detection настройки
YOLO_DET_IMAGE_SIZE = 1280
YOLO_DET_CONFIDENCE = 0.5

# YOLO Pose настройки
YOLO_POSE_IMAGE_SIZE = 768
YOLO_POSE_CONFIDENCE = 0.25

# Stage2 (ResNet) настройки - НОВАЯ ЛОГИКА 2025
# Модель выдаёт прямое смещение в пикселях (не нормализованное)
STAGE2_CROP_SIZE = 256  # Размер области вокруг точки

# SubPixel настройки - НОВАЯ МОДЕЛЬ 2025
SUBPIXEL_CROP_SIZE = 64  # Размер области для SubPixel

# Stage2 настройки для портативной версии (нормализованный выход)
STAGE2_PORTABLE_CROP_SIZE = 256
STAGE2_PORTABLE_CROP_HALF = 128
STAGE2_PORTABLE_ITERATIONS = 2
STAGE2_PORTABLE_MAX_OFFSET = 30  # пикселей за итерацию

# Отступы для bbox
BBOX_MARGIN = 20  # Отступ от границ bbox (пикселей)
