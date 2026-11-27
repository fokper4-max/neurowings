#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Графические элементы для сцены (v2.2.0)

Улучшения для экранов высокого разрешения (до 5160x2160) и больших сканов (24-36 МП):
- Расширенная зона захвата мышью (shape() и boundingRect() с hit_radius >= max(radius * 2.5, 8.0))
- Адаптивный размер шрифта номеров точек и номеров крыльев
"""

from typing import Tuple

from PyQt5.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsSimpleTextItem
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush, QFont, QPainterPath

from ..core.constants import (
    COLOR_NORMAL, COLOR_PROBLEM, COLOR_SELECTED,
    COLOR_WING_OK, COLOR_WING_PROBLEM, DEFAULT_TEXT_SIZE
)


class PointItem(QGraphicsEllipseItem):
    """Точка крыла на сцене (локальная нумерация 1..8 на каждом крыле и расширенная зона захвата)"""

    def __init__(self, x: float, y: float, global_idx: int, wing_idx: int, point_idx: int,
                 radius: float = 1, color: QColor = None, is_problem: bool = False,
                 source_type: str = 'final', text_size: int = None):
        self.radius = max(0.5, float(radius))
        self.hit_radius = max(self.radius * 2.5, 6.0)
        super().__init__(-self.radius, -self.radius, self.radius * 2, self.radius * 2)
        self.setPos(x, y)
        self.global_idx = global_idx
        self.wing_idx = wing_idx
        self.point_idx = point_idx
        self.is_selected = False
        self.is_hovered = False
        self.is_problem = is_problem
        self.source_type = source_type

        self.point_color = COLOR_PROBLEM if is_problem else (color or COLOR_NORMAL)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, False)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(200 if source_type == 'active' else 100)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

        self.update_style()

        # Подпись точки - ВСЕГДА локальный номер точки на крыле (1..8)!
        # Для дополнительных оверлейных точек (global_idx < 0) номер не показываем.
        if global_idx >= 0:
            local_num = (point_idx + 1) if 0 <= point_idx < 8 else (global_idx % 8 + 1)
            self.label = QGraphicsSimpleTextItem(str(local_num), self)
            text_color = QColor(220, 60, 0) if is_problem else QColor(0, 40, 200)
            self.label.setBrush(QBrush(text_color))
            eff_text_size = int(text_size) if text_size is not None else DEFAULT_TEXT_SIZE
            font = QFont("Arial", eff_text_size, QFont.Bold)
            self.label.setFont(font)
            br = self.label.boundingRect()
            self.label.setPos(self.radius + 2, -br.height() * 0.85)
            self.label.setZValue(101)
        else:
            self.label = None

    def boundingRect(self) -> QRectF:
        """Расширенный прямоугольник для надёжного попадания курсором мыши на больших сканах."""
        hr = self.hit_radius + 2.0
        return QRectF(-hr, -hr, hr * 2.0, hr * 2.0)

    def shape(self) -> QPainterPath:
        """Невидимая увеличенная круглая область захвата мыши вокруг точки."""
        path = QPainterPath()
        hr = self.hit_radius
        path.addEllipse(QRectF(-hr, -hr, hr * 2.0, hr * 2.0))
        return path

    def update_label(self, new_number: int):
        """Обновить номер точки"""
        if self.label:
            self.label.setText(str(new_number))

    def update_style(self):
        """Обновить стиль точки (при радиусе 1 px диаметр строго 2 px без утолщающей обводки)"""
        if self.is_selected:
            self.setBrush(QBrush(COLOR_SELECTED))
            self.setPen(QPen(Qt.white, 1.0))
        elif self.is_hovered:
            self.setBrush(QBrush(QColor(255, 255, 0)))
            self.setPen(QPen(Qt.white, 1.0))
        else:
            self.setBrush(QBrush(self.point_color))
            if self.is_problem:
                self.setPen(QPen(Qt.yellow, 1.0))
            elif self.radius <= 1.5:
                self.setPen(QPen(Qt.NoPen))
            else:
                self.setPen(QPen(Qt.white, 1.0))

    def set_selected(self, selected: bool):
        """Установить выделение"""
        self.is_selected = selected
        self.update_style()

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update_style()
        super().hoverLeaveEvent(event)


class WingLabelItem(QGraphicsSimpleTextItem):
    """Метка крыла [№], аккуратно привязанная к верхней границе крыла"""

    def __init__(self, wing_idx: int, cx: float, cy: float, is_ok: bool, y_top: float = None, font_size: int = 22):
        super().__init__(f"[{wing_idx + 1}]")
        color = COLOR_WING_OK if is_ok else COLOR_WING_PROBLEM
        self.setBrush(QBrush(color))
        font = QFont("Arial", max(16, int(font_size)), QFont.Bold)
        self.setFont(font)
        br = self.boundingRect()
        anchor_y = (y_top - br.height() - 4) if y_top is not None else (cy - 75)
        self.setPos(cx - br.width() / 2.0, max(0.0, anchor_y))
        self.setZValue(99)


class ResizeHandle(QGraphicsRectItem):
    """Ручка для изменения размера рамки"""

    def __init__(self, position, parent=None):
        super().__init__(-5, -5, 10, 10, parent)
        self.position = position  # 'tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r'
        self.setBrush(QBrush(QColor(255, 255, 0)))
        self.setPen(QPen(QColor(255, 165, 0), 2))
        self.setZValue(52)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.setCursor(self._get_cursor())

    def _get_cursor(self):
        cursors = {
            'tl': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor,
            'bl': Qt.SizeBDiagCursor, 'br': Qt.SizeFDiagCursor,
            't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
            'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor
        }
        return cursors.get(self.position, Qt.ArrowCursor)


class BBoxItem(QGraphicsRectItem):
    """Ограничивающая рамка крыла"""

    def __init__(self, x1, y1, x2, y2, wing_idx=-1):
        super().__init__(x1, y1, x2 - x1, y2 - y1)
        self.wing_idx = wing_idx
        self.setPen(QPen(QColor(255, 165, 0), 2, Qt.DashLine))
        self.setBrush(QBrush(Qt.transparent))
        self.setZValue(50)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

        self.label = QGraphicsSimpleTextItem(f"Крыло #{wing_idx + 1}", self)
        self.label.setBrush(QBrush(QColor(255, 165, 0)))
        font = QFont("Arial", 12, QFont.Bold)
        self.label.setFont(font)
        self.label.setPos(x1 + 5, y1 + 5)
        self.label.setZValue(51)

        self.handles = {}
        positions = ['tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r']
        for pos in positions:
            handle = ResizeHandle(pos, self)
            self.handles[pos] = handle

        self._update_handles()
        self._resizing = False
        self._resize_handle = None
        self._resize_start_rect = None
        self._resize_start_pos = None
        self._press_scene_rect = None

    def update_label(self, new_number: int):
        self.wing_idx = new_number - 1
        self.label.setText(f"Крыло #{new_number}")

    def _update_handles(self):
        r = self.rect()
        positions = {
            'tl': (r.left(), r.top()),
            'tr': (r.right(), r.top()),
            'bl': (r.left(), r.bottom()),
            'br': (r.right(), r.bottom()),
            't': (r.center().x(), r.top()),
            'b': (r.center().x(), r.bottom()),
            'l': (r.left(), r.center().y()),
            'r': (r.right(), r.center().y())
        }
        for pos, (x, y) in positions.items():
            if pos in self.handles:
                self.handles[pos].setPos(x, y)
        if hasattr(self, "label") and self.label:
            self.label.setPos(r.left() + 5, r.top() + 5)

    def setRect(self, *args):
        super().setRect(*args)
        self._update_handles()

    def mousePressEvent(self, event):
        self._press_scene_rect = self.mapRectToScene(self.rect())
        if event.button() == Qt.LeftButton:
            for pos, handle in self.handles.items():
                if handle.contains(handle.mapFromParent(event.pos())):
                    self._resizing = True
                    self._resize_handle = pos
                    self._resize_start_rect = self.rect()
                    self._resize_start_pos = event.scenePos()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_handle:
            delta = event.scenePos() - self._resize_start_pos
            r = self._resize_start_rect

            new_rect = QRectF(r)
            if 'l' in self._resize_handle:
                new_rect.setLeft(r.left() + delta.x())
            if 'r' in self._resize_handle:
                new_rect.setRight(r.right() + delta.x())
            if 't' in self._resize_handle:
                new_rect.setTop(r.top() + delta.y())
            if 'b' in self._resize_handle:
                new_rect.setBottom(r.bottom() + delta.y())

            if new_rect.width() > 20 and new_rect.height() > 20:
                super().setRect(new_rect)
                self._update_handles()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Эмитируем bbox_changed ТОЛЬКО если координаты рамки реально изменились!"""
        was_resizing = self._resizing
        if self._resizing:
            self._resizing = False
            self._resize_handle = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

        if self.scene() and hasattr(self.scene(), 'views') and self.scene().views():
            view = self.scene().views()[0]
            r = self.mapRectToScene(self.rect())
            old = self._press_scene_rect
            changed = (
                old is None
                or abs(r.left() - old.left()) > 0.5
                or abs(r.top() - old.top()) > 0.5
                or abs(r.right() - old.right()) > 0.5
                or abs(r.bottom() - old.bottom()) > 0.5
            )
            if (was_resizing or changed) and hasattr(view, 'bbox_changed'):
                view.bbox_changed.emit(
                    self.wing_idx,
                    r.left(), r.top(),
                    r.right(), r.bottom()
                )
        self._press_scene_rect = None

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(255, 255, 0), 3, Qt.DashLine))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor(255, 165, 0), 2, Qt.DashLine))
        super().hoverLeaveEvent(event)


class MeasurementLineItem(QGraphicsLineItem):
    """Линия для отображения геометрических измерений"""

    def __init__(self, x1, y1, x2, y2, color=QColor(0, 255, 0), width=2, style=Qt.SolidLine):
        super().__init__(x1, y1, x2, y2)
        self.setPen(QPen(color, width, style))
        self.setZValue(90)


class SplitResizeHandle(QGraphicsRectItem):
    """Экранная ручка ресайза области разбиения (12x12 px на любом зуме)."""

    def __init__(self, position: str, parent=None):
        super().__init__(-6, -6, 12, 12, parent)
        self.position = position  # 'tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r'
        self.setFlag(QGraphicsRectItem.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setPen(QPen(QColor(0, 120, 215), 2))
        self.setZValue(252)
        self.setCursor(self._get_cursor())

    def _get_cursor(self):
        cursors = {
            'tl': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor,
            'bl': Qt.SizeBDiagCursor, 'br': Qt.SizeFDiagCursor,
            't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
            'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
        }
        return cursors.get(self.position, Qt.ArrowCursor)

    def mousePressEvent(self, event):
        parent = self.parentItem()
        if event.button() == Qt.LeftButton and isinstance(parent, SplitRegionItem):
            parent._begin_resize(self.position, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        parent = self.parentItem()
        if isinstance(parent, SplitRegionItem) and parent._resizing:
            parent._apply_resize(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        parent = self.parentItem()
        if isinstance(parent, SplitRegionItem) and parent._resizing:
            parent._end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SplitRegionItem(QGraphicsRectItem):
    """Область разбиения большого скана на отдельную семью (режим Ножницы)."""

    _LABEL_OFFSET_X = 12.0
    _LABEL_OFFSET_Y = 10.0
    _MIN_SIZE = 21.0

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 region_idx: int = 0, name: str = ""):
        super().__init__(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        self.region_idx = int(region_idx)
        clean_name = (name or "").strip()
        self.region_name = clean_name if clean_name else f"Семья_{self.region_idx + 1}"

        self.setPen(self._make_pen(QColor(0, 145, 234), 3))
        self.setBrush(QBrush(QColor(0, 145, 234, 28)))
        self.setZValue(250)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

        # Читаемая плашка с подписью в экранных пикселях на любом зуме
        self.label_bg = QGraphicsRectItem(self)
        self.label_bg.setFlag(QGraphicsRectItem.ItemIgnoresTransformations, True)
        self.label_bg.setBrush(QBrush(QColor(255, 255, 255, 230)))
        self.label_bg.setPen(QPen(QColor(0, 120, 215), 1.5))
        self.label_bg.setZValue(251)

        self.label = QGraphicsSimpleTextItem(self.label_bg)
        self.label.setFont(QFont("Arial", 10, QFont.Bold))
        self.label.setBrush(QBrush(QColor(0, 80, 160)))
        self.label.setPos(self._LABEL_OFFSET_X, self._LABEL_OFFSET_Y)

        self.handles = {}
        for pos in ('tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r'):
            self.handles[pos] = SplitResizeHandle(pos, self)

        self._resizing = False
        self._resize_handle = None
        self._resize_start_rect = None
        self._resize_start_pos = None
        self._press_scene_rect = None

        self._update_handles()

    @staticmethod
    def _make_pen(color: QColor, width: float) -> QPen:
        pen = QPen(color, width, Qt.DashLine)
        pen.setCosmetic(True)
        return pen

    def _update_label_text(self):
        r = self.rect()
        w = int(round(r.width()))
        h = int(round(r.height()))
        self.label.setText(f"✂ {self.region_idx + 1}: {self.region_name} ({w}x{h})")
        br = self.label.boundingRect().adjusted(-6, -3, 6, 3)
        self.label_bg.setRect(br.translated(self._LABEL_OFFSET_X, self._LABEL_OFFSET_Y))

    def update_label(self, new_idx: int, new_name=None):
        """Обновить индекс и (опционально) название области семьи."""
        self.region_idx = int(new_idx)
        if new_name is not None:
            clean_name = str(new_name).strip()
            self.region_name = clean_name if clean_name else f"Семья_{self.region_idx + 1}"
        self._update_label_text()

    def get_scene_bounds(self) -> Tuple[float, float, float, float]:
        """Вернуть (x1, y1, x2, y2) области в координатах сцены."""
        r = self.mapRectToScene(self.rect())
        return (r.left(), r.top(), r.right(), r.bottom())

    def set_scene_bounds(self, x1: float, y1: float, x2: float, y2: float):
        """Задать границы области в координатах сцены и синхронизировать ручки и плашку."""
        self.setPos(0.0, 0.0)
        nx1, nx2 = min(float(x1), float(x2)), max(float(x1), float(x2))
        ny1, ny2 = min(float(y1), float(y2)), max(float(y1), float(y2))
        self.setRect(QRectF(nx1, ny1, max(1.0, nx2 - nx1), max(1.0, ny2 - ny1)))

    def _update_handles(self):
        r = self.rect()
        positions = {
            'tl': (r.left(), r.top()),
            'tr': (r.right(), r.top()),
            'bl': (r.left(), r.bottom()),
            'br': (r.right(), r.bottom()),
            't': (r.center().x(), r.top()),
            'b': (r.center().x(), r.bottom()),
            'l': (r.left(), r.center().y()),
            'r': (r.right(), r.center().y()),
        }
        for pos, (x, y) in positions.items():
            if pos in self.handles:
                self.handles[pos].setPos(x, y)
        if hasattr(self, "label_bg") and self.label_bg is not None:
            self.label_bg.setPos(r.left(), r.top())
            self._update_label_text()

    def setRect(self, *args):
        super().setRect(*args)
        self._update_handles()

    def _find_hit_handle(self, scene_pos):
        """Найти ближайшую ручку в пределах 10 экранных пикселей (работает при любом зуме)."""
        view = self.scene().views()[0] if (self.scene() and self.scene().views()) else None
        best_pos = None
        best_dist = None
        if view is not None:
            click_vp = view.mapFromScene(scene_pos)
            for pos, handle in self.handles.items():
                h_vp = view.mapFromScene(handle.scenePos())
                dx = abs(click_vp.x() - h_vp.x())
                dy = abs(click_vp.y() - h_vp.y())
                if dx <= 10 and dy <= 10:
                    dist_sq = dx * dx + dy * dy
                    if best_dist is None or dist_sq < best_dist:
                        best_dist = dist_sq
                        best_pos = pos
        else:
            for pos, handle in self.handles.items():
                h_pos = handle.scenePos()
                dx = abs(scene_pos.x() - h_pos.x())
                dy = abs(scene_pos.y() - h_pos.y())
                if dx <= 10 and dy <= 10:
                    dist_sq = dx * dx + dy * dy
                    if best_dist is None or dist_sq < best_dist:
                        best_dist = dist_sq
                        best_pos = pos
        return best_pos

    def _begin_resize(self, handle_pos: str, scene_pos):
        self._press_scene_rect = self.mapRectToScene(self.rect())
        self._resizing = True
        self._resize_handle = handle_pos
        self._resize_start_rect = QRectF(self.rect())
        self._resize_start_pos = scene_pos

    def _apply_resize(self, scene_pos):
        if not (self._resizing and self._resize_handle and self._resize_start_rect is not None):
            return
        delta = scene_pos - self._resize_start_pos
        r = self._resize_start_rect

        left = r.left()
        right = r.right()
        top = r.top()
        bottom = r.bottom()

        if 'l' in self._resize_handle:
            left = r.left() + delta.x()
            if right - left < self._MIN_SIZE:
                left = right - self._MIN_SIZE
        if 'r' in self._resize_handle:
            right = r.right() + delta.x()
            if right - left < self._MIN_SIZE:
                right = left + self._MIN_SIZE
        if 't' in self._resize_handle:
            top = r.top() + delta.y()
            if bottom - top < self._MIN_SIZE:
                top = bottom - self._MIN_SIZE
        if 'b' in self._resize_handle:
            bottom = r.bottom() + delta.y()
            if bottom - top < self._MIN_SIZE:
                bottom = top + self._MIN_SIZE

        new_rect = QRectF(left, top, right - left, bottom - top).normalized()
        if new_rect.width() > 20 and new_rect.height() > 20:
            super().setRect(new_rect)
            self._update_handles()

    def _emit_region_changed(self, force: bool = False):
        if self.scene() and hasattr(self.scene(), 'views') and self.scene().views():
            view = self.scene().views()[0]
            r = self.mapRectToScene(self.rect())
            old = self._press_scene_rect
            changed = (
                old is None
                or abs(r.left() - old.left()) > 0.5
                or abs(r.top() - old.top()) > 0.5
                or abs(r.right() - old.right()) > 0.5
                or abs(r.bottom() - old.bottom()) > 0.5
            )
            if (force or changed) and hasattr(view, 'split_region_changed'):
                view.split_region_changed.emit(
                    self.region_idx,
                    r.left(), r.top(),
                    r.right(), r.bottom()
                )
        self._press_scene_rect = None

    def _end_resize(self):
        was_resizing = self._resizing
        self._resizing = False
        self._resize_handle = None
        self._emit_region_changed(force=was_resizing)

    def mousePressEvent(self, event):
        self._press_scene_rect = self.mapRectToScene(self.rect())
        if event.button() == Qt.LeftButton:
            hit_pos = self._find_hit_handle(event.scenePos())
            if hit_pos is not None:
                self._begin_resize(hit_pos, event.scenePos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_handle:
            self._apply_resize(event.scenePos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Эмитируем split_region_changed только если область изменилась или шла трансформация."""
        if self._resizing:
            self._end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._emit_region_changed(force=False)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.scene() and hasattr(self.scene(), 'views') and self.scene().views():
                view = self.scene().views()[0]
                if hasattr(view, 'split_region_rename_requested'):
                    view.split_region_rename_requested.emit(self.region_idx)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def hoverEnterEvent(self, event):
        self.setPen(self._make_pen(QColor(0, 180, 255), 4))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._make_pen(QColor(0, 145, 234), 3))
        super().hoverLeaveEvent(event)
