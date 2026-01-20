#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings Core - Ядро приложения
"""

from .constants import (
    APP_NAME, APP_VERSION, APP_AUTHOR, NUM_POINTS,
    COLOR_NORMAL, COLOR_PROBLEM, COLOR_SELECTED,
    COLOR_WING_LABEL, COLOR_WING_OK, COLOR_WING_PROBLEM,
    COLOR_YOLO, COLOR_STAGE1, COLOR_STAGE2, COLOR_GT,
    DEFAULT_POINT_RADIUS, DEFAULT_TEXT_SIZE,
    BREEDS, INDEX_POINTS, YOLO_TO_WINGSDIG,
    STAGE2_PORTABLE_CROP_SIZE, STAGE2_PORTABLE_CROP_HALF,
    STAGE2_PORTABLE_ITERATIONS, STAGE2_PORTABLE_MAX_OFFSET
)

from .calculations import (
    calculate_ci, calculate_dsa, calculate_hi,
    ci_to_alpatov, get_breed_scores, calculate_breed_probability
)

from .data_models import (
    WingPoint, BBox, Wing, ImageData, EditMode
)

from .models import (
    TORCH_AVAILABLE, get_device, load_stage2_model, load_stage2_portable_model, load_subpixel_model
)

__all__ = [
    # constants
    'APP_NAME', 'APP_VERSION', 'APP_AUTHOR', 'NUM_POINTS',
    'COLOR_NORMAL', 'COLOR_PROBLEM', 'COLOR_SELECTED',
    'COLOR_WING_LABEL', 'COLOR_WING_OK', 'COLOR_WING_PROBLEM',
    'COLOR_YOLO', 'COLOR_STAGE1', 'COLOR_STAGE2', 'COLOR_GT',
    'DEFAULT_POINT_RADIUS', 'DEFAULT_TEXT_SIZE',
    'BREEDS', 'INDEX_POINTS', 'YOLO_TO_WINGSDIG',
    'STAGE2_PORTABLE_CROP_SIZE', 'STAGE2_PORTABLE_CROP_HALF',
    'STAGE2_PORTABLE_ITERATIONS', 'STAGE2_PORTABLE_MAX_OFFSET',
    # calculations
    'calculate_ci', 'calculate_dsa', 'calculate_hi',
    'ci_to_alpatov', 'get_breed_scores', 'calculate_breed_probability',
    # data_models
    'WingPoint', 'BBox', 'Wing', 'ImageData', 'EditMode',
    # models
    'TORCH_AVAILABLE', 'get_device', 'load_stage2_model', 'load_stage2_portable_model', 'load_subpixel_model',
]
