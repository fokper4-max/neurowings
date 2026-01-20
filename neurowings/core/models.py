#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Нейросетевые модели
Обновлено для models_trained_2025_01_19
"""

import logging

logger = logging.getLogger("NeuroWings")

try:
    import torch
    import torch.nn as nn
    from torchvision import models
    TORCH_AVAILABLE = True
except ImportError as e:
    TORCH_AVAILABLE = False
    logger.warning(f"PyTorch не установлен: {e}. Нейросетевые функции недоступны.")


class Stage2Model(nn.Module):
    """
    Модель Stage2 для уточнения координат точек (новая архитектура 2025).
    ResNet34 backbone + регрессионная голова.
    Выход: прямое смещение в пикселях от центра патча.
    """

    def __init__(self):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for Stage2Model")

        super().__init__()
        resnet = models.resnet34(weights=None)
        self.backbone = nn.Sequential(*list(resnet.children())[:-1])
        self.fc = nn.Sequential(
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 2)
        )

    def forward(self, x):
        x = self.backbone(x)
        x = x.view(x.size(0), -1)
        return self.fc(x)


class SubPixelModel(nn.Module):
    """
    Модель SubPixel для субпиксельного уточнения координат (новая 2025).
    Custom CNN для патчей 64x64.
    Выход: прямое смещение в пикселях от центра патча.
    """

    def __init__(self):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for SubPixelModel")

        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(3, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(128, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.Conv2d(256, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.conv4 = nn.Sequential(
            nn.Conv2d(256, 512, 3, padding=1), nn.BatchNorm2d(512), nn.ReLU(inplace=True),
            nn.Conv2d(512, 512, 3, padding=1), nn.BatchNorm2d(512), nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.regressor = nn.Sequential(
            nn.Linear(512, 256), nn.ReLU(inplace=True), nn.Dropout(0.3),
            nn.Linear(256, 64), nn.ReLU(inplace=True),
            nn.Linear(64, 2)
        )

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = x.view(x.size(0), -1)
        return self.regressor(x)


def load_stage2_model(model_path: str, device):
    """
    Загрузить модель Stage2 из файла.

    Args:
        model_path: Путь к .pth файлу
        device: torch.device

    Returns:
        Stage2Model или None при ошибке
    """
    if not TORCH_AVAILABLE:
        return None

    try:
        model = Stage2Model()
        state = torch.load(model_path, map_location=device, weights_only=False)

        if isinstance(state, dict) and 'model_state_dict' in state:
            model.load_state_dict(state['model_state_dict'])
        else:
            model.load_state_dict(state)

        model.to(device)
        model.eval()
        logger.info(f"Stage2 модель успешно загружена из {model_path}")
        return model
    except FileNotFoundError:
        logger.error(f"Файл модели не найден: {model_path}")
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки Stage2 модели: {e}", exc_info=True)
        return None


def load_subpixel_model(model_path: str, device):
    """
    Загрузить модель SubPixel из файла.

    Args:
        model_path: Путь к .pth файлу
        device: torch.device

    Returns:
        SubPixelModel или None при ошибке
    """
    if not TORCH_AVAILABLE:
        return None

    try:
        model = SubPixelModel()
        state = torch.load(model_path, map_location=device, weights_only=False)

        if isinstance(state, dict) and 'model_state_dict' in state:
            model.load_state_dict(state['model_state_dict'])
        else:
            model.load_state_dict(state)

        model.to(device)
        model.eval()
        logger.info(f"SubPixel модель успешно загружена из {model_path}")
        return model
    except FileNotFoundError:
        logger.error(f"Файл модели SubPixel не найден: {model_path}")
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки SubPixel модели: {e}", exc_info=True)
        return None


def get_device():
    """Получить доступное устройство (CUDA/MPS/CPU)"""
    if not TORCH_AVAILABLE:
        return None

    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"Используется GPU: {torch.cuda.get_device_name(0)}")
        return device
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        logger.info("Используется Apple MPS")
        return torch.device("mps")
    else:
        logger.info("Используется CPU")
        return torch.device("cpu")


# -----------------------------------------------------------------------------
# ПОРТАБЕЛЬНАЯ Stage2 (нормализованный выход, итеративное уточнение)
# -----------------------------------------------------------------------------
class Stage2PortableModel(nn.Module):
    """
    Stage2 из версии 1.6: выход — нормализованное смещение, умножается на STAGE2_CROP_HALF.
    """
    def __init__(self):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for Stage2PortableModel")
        super().__init__()
        resnet = models.resnet34(weights=None)
        self.bb = nn.Sequential(*list(resnet.children())[:-1])
        self.hd = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(256, 64), nn.ReLU(),
            nn.Linear(64, 2)
        )

    def forward(self, x):
        return self.hd(self.bb(x))


def load_stage2_portable_model(model_path: str, device):
    """Загрузить портативную Stage2 модель."""
    if not TORCH_AVAILABLE:
        return None
    try:
        model = Stage2PortableModel()
        state = torch.load(model_path, map_location=device, weights_only=False)
        if isinstance(state, dict) and 'model_state_dict' in state:
            model.load_state_dict(state['model_state_dict'])
        else:
            model.load_state_dict(state)
        model.to(device)
        model.eval()
        logger.info(f"Stage2 portable модель успешно загружена из {model_path}")
        return model
    except FileNotFoundError:
        logger.error(f"Файл модели не найден: {model_path}")
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки Stage2 portable: {e}", exc_info=True)
        return None
