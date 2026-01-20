#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Модели данных
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from enum import Enum

from .calculations import calculate_indices, identify_breed, get_problem_points, calculate_dsa_excel


@dataclass
class WingAnalysis:
    """Результаты анализа крыла"""
    CI: float = 0
    DsA: float = 0
    HI: float = 0
    breeds: List[str] = field(default_factory=list)
    index_valid: Dict[str, bool] = field(default_factory=dict)
    problem_points: List[int] = field(default_factory=list)
    is_identified: bool = False
    projection: Tuple[float, float] = (0, 0)


@dataclass
class WingPoint:
    """Точка крыла"""
    x: float
    y: float
    is_manual: bool = False


@dataclass
class BBox:
    """Ограничивающая рамка"""
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass 
class Wing:
    """Крыло с точками и анализом"""
    points: List[WingPoint] = field(default_factory=list)
    analysis: Optional[WingAnalysis] = None
    bbox: Optional[BBox] = None
    points_yolo: List[WingPoint] = field(default_factory=list)
    points_stage1: List[WingPoint] = field(default_factory=list)
    points_stage2: List[WingPoint] = field(default_factory=list)
    # Выбранная модель для каждой точки: 'yolo', 'stage1', 'stage2'
    point_sources: List[str] = field(default_factory=lambda: ['stage2'] * 8)
    
    def get_center(self) -> Tuple[float, float]:
        """Получить центр крыла"""
        if not self.points:
            return (0, 0)
        cx = sum(p.x for p in self.points) / len(self.points)
        cy = sum(p.y for p in self.points) / len(self.points)
        return (cx, cy)
    
    def get_points_tuple(self) -> List[Tuple[float, float]]:
        """Получить точки как список кортежей"""
        return [(p.x, p.y) for p in self.points]
    
    def get_active_points(self) -> List[Tuple[float, float]]:
        """Получить координаты точек согласно выбранным источникам"""
        result = []
        for i in range(min(8, len(self.points))):
            source = self.point_sources[i] if i < len(self.point_sources) else 'stage2'
            if source == 'yolo' and i < len(self.points_yolo):
                result.append((self.points_yolo[i].x, self.points_yolo[i].y))
            elif source == 'stage1' and i < len(self.points_stage1):
                result.append((self.points_stage1[i].x, self.points_stage1[i].y))
            elif source == 'stage2' and i < len(self.points_stage2):
                result.append((self.points_stage2[i].x, self.points_stage2[i].y))
            elif i < len(self.points):
                result.append((self.points[i].x, self.points[i].y))
            else:
                result.append((0, 0))
        return result
    
    def analyze(self, image_height: Optional[int] = None):
        """
        Выполнить анализ крыла
        
        Args:
            image_height: Высота изображения для преобразования координат из экранной системы (Y сверху)
                         в систему WingsDig (Y снизу). Если None, используются координаты как есть.
        """
        points = self.get_active_points()
        if len(points) != 8:
            self.analysis = WingAnalysis()
            return
        
        # Преобразование координат из экранной системы в WingsDig формат для правильных расчетов
        # В WingsDig/Excel: Y отсчитывается снизу, в экранной системе: Y отсчитывается сверху
        if image_height is not None and image_height > 0:
            # Конвертируем экранные координаты (Y сверху) в WingsDig координаты (Y снизу)
            points_wingsdig = [(px, image_height - py) for px, py in points]
            points = points_wingsdig
        
        indices = calculate_indices(points)
        breeds, index_valid = identify_breed(indices['CI'], indices['DsA'], indices['HI'])
        problem_points = get_problem_points(index_valid)
        _, projection = calculate_dsa_excel(points)
        
        self.analysis = WingAnalysis(
            CI=indices['CI'],
            DsA=indices['DsA'],
            HI=indices['HI'],
            breeds=breeds,
            index_valid=index_valid,
            problem_points=problem_points,
            is_identified=len(breeds) > 0,
            projection=projection
        )


@dataclass
class ImageData:
    """Данные изображения"""
    path: Path
    wings: List[Wing] = field(default_factory=list)
    width: int = 0
    height: int = 0
    is_processed: bool = False
    is_modified: bool = False
    analysis_results: Dict = field(default_factory=dict)
    
    def analyze_all_wings(self):
        """Анализировать все крылья"""
        for wing in self.wings:
            wing.analyze(image_height=self.height if self.height > 0 else None)


class EditMode(Enum):
    """Режимы редактирования"""
    VIEW = "Просмотр"
    EDIT = "Редактирование"
    ADD = "Оцифровка"
    BBOX = "Добавить рамку"
