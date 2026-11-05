#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings Core - Ядро приложения
"""

# Важно: сначала тянем torch (models), затем PyQt (constants), иначе torch падает,
# если импортировать его после PyQt на Windows.
from .models import (
    TORCH_AVAILABLE, TORCH_IMPORT_ERROR,
    TORCHVISION_MODELS_AVAILABLE, TORCHVISION_MODELS_IMPORT_ERROR,
    get_device, load_stage2_model, load_stage2_portable_model, load_subpixel_model
)

from .constants import (
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_MAX_URL, APP_TELEGRAM_LABEL, APP_TELEGRAM_URL,
    APP_GITHUB_REPO, APP_GITHUB_RELEASES_API_URL, APP_GITHUB_RELEASES_HTML_URL, APP_UPDATE_FEED_URL,
    NUM_POINTS,
    COLOR_NORMAL, COLOR_PROBLEM, COLOR_SELECTED,
    COLOR_WING_LABEL, COLOR_WING_OK, COLOR_WING_PROBLEM,
    COLOR_YOLO, COLOR_STAGE1, COLOR_STAGE2, COLOR_GT,
    DEFAULT_POINT_RADIUS, DEFAULT_TEXT_SIZE,
    BREEDS, CLASSIC_BREEDS, BREED_NAMES_RU, BREED_SHORT_NAMES_RU, BREED_COLORS_HEX,
    ALLOWED_IMAGE_EXTENSIONS, format_breed_ru,
    INDEX_POINTS, YOLO_TO_WINGSDIG,
    STAGE2_PORTABLE_CROP_SIZE, STAGE2_PORTABLE_CROP_HALF,
    STAGE2_PORTABLE_ITERATIONS, STAGE2_PORTABLE_MAX_OFFSET
)

from .calculations import (
    calculate_ci, calculate_dsa, calculate_hi,
    ci_to_alpatov, ci_to_alpatov_classic,
    calculate_ruttner_classes, check_wing_orientation, calculate_breed_distance,
    get_breed_scores, calculate_breed_probability
)

from .data_models import (
    WingPoint, BBox, Wing, ImageData, EditMode
)

from .colony_analysis import (
    ColonyAnalysisService, ColonyAnalysisResult, analyze_colony
)

from .hardware_profiler import (
    HardwareProfiler, HardwareSpecs, ComputeProfile, POWER_MODES
)

__all__ = [
    # models (torch first)
    'TORCH_AVAILABLE', 'TORCH_IMPORT_ERROR',
    'TORCHVISION_MODELS_AVAILABLE', 'TORCHVISION_MODELS_IMPORT_ERROR',
    'get_device', 'load_stage2_model', 'load_stage2_portable_model', 'load_subpixel_model',
    # constants
    'APP_NAME', 'APP_VERSION', 'APP_AUTHOR', 'APP_MAX_URL', 'APP_TELEGRAM_LABEL', 'APP_TELEGRAM_URL',
    'APP_GITHUB_REPO', 'APP_GITHUB_RELEASES_API_URL', 'APP_GITHUB_RELEASES_HTML_URL',
    'APP_UPDATE_FEED_URL', 'NUM_POINTS',
    'COLOR_NORMAL', 'COLOR_PROBLEM', 'COLOR_SELECTED',
    'COLOR_WING_LABEL', 'COLOR_WING_OK', 'COLOR_WING_PROBLEM',
    'COLOR_YOLO', 'COLOR_STAGE1', 'COLOR_STAGE2', 'COLOR_GT',
    'DEFAULT_POINT_RADIUS', 'DEFAULT_TEXT_SIZE',
    'BREEDS', 'CLASSIC_BREEDS', 'BREED_NAMES_RU', 'BREED_SHORT_NAMES_RU', 'BREED_COLORS_HEX',
    'ALLOWED_IMAGE_EXTENSIONS', 'format_breed_ru',
    'INDEX_POINTS', 'YOLO_TO_WINGSDIG',
    'STAGE2_PORTABLE_CROP_SIZE', 'STAGE2_PORTABLE_CROP_HALF',
    'STAGE2_PORTABLE_ITERATIONS', 'STAGE2_PORTABLE_MAX_OFFSET',
    # calculations
    'calculate_ci', 'calculate_dsa', 'calculate_hi',
    'ci_to_alpatov', 'ci_to_alpatov_classic',
    'calculate_ruttner_classes', 'check_wing_orientation', 'calculate_breed_distance',
    'get_breed_scores', 'calculate_breed_probability',
    # data_models
    'WingPoint', 'BBox', 'Wing', 'ImageData', 'EditMode',
    # colony_analysis
    'ColonyAnalysisService', 'ColonyAnalysisResult', 'analyze_colony',
    # hardware_profiler
    'HardwareProfiler', 'HardwareSpecs', 'ComputeProfile', 'POWER_MODES',
]
