#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Графические элементы для сцены (v2.2.0)

Улучшения для экранов высокого разрешения (до 5160x2160) и больших сканов (24–36 МП):
- Расширенная зона захвата мышью (shape() и boundingRect() с hit_radius >= max(radius * 2.5, 8.0))
- Адаптивный размер шрифта номеров точек и номеров крыльев
"""

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

        # Подпись точки — ВСЕГДА локальный номер точки на крыле (1..8)!
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
