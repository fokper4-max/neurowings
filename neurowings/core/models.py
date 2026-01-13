#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Нейросетевые модели
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
    Модель Stage2 для уточнения координат точек.
    ResNet34 backbone + регрессионная голова.
    """
    
    def __init__(self):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for Stage2Model")
        
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
        state = torch.load(model_path, map_location=device)

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
