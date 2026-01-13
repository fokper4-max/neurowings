#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Графические элементы для сцены
"""

from PyQt5.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsSimpleTextItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPen, QBrush, QFont

from ..core.constants import (
    COLOR_NORMAL, COLOR_PROBLEM, COLOR_SELECTED,
    COLOR_WING_OK, COLOR_WING_PROBLEM, DEFAULT_TEXT_SIZE
)


class PointItem(QGraphicsEllipseItem):
    """Точка крыла на сцене"""
    
    def __init__(self, x: float, y: float, global_idx: int, wing_idx: int, point_idx: int,
                 radius: float = 1, color: QColor = None, is_problem: bool = False,
                 source_type: str = 'final'):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.setPos(x, y)
        self.global_idx = global_idx
        self.wing_idx = wing_idx
        self.point_idx = point_idx
        self.radius = radius
        self.is_selected = False
        self.is_hovered = False
        self.is_problem = is_problem
        self.source_type = source_type
        
        self.point_color = COLOR_PROBLEM if is_problem else (color or COLOR_NORMAL)
        
        self.setAcceptHoverEvents(True)
        # ВСЕ точки можно редактировать
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, False)  # Управляем перемещением вручную
        self.setCursor(Qt.PointingHandCursor)
        # Активные точки поверх вспомогательных
        self.setZValue(200 if source_type == 'active' else 100)
        # ВСЕ точки принимают события мыши
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        
        self.update_style()

        # Подпись точки - используем ГЛОБАЛЬНЫЙ номер (global_idx + 1)
        # Для дополнительных точек (global_idx < 0) номер не показываем
        if global_idx >= 0:
            self.label = QGraphicsSimpleTextItem(str(global_idx + 1), self)
            text_color = QColor(255, 100, 0) if is_problem else QColor(0, 0, 255)
            self.label.setBrush(QBrush(text_color))
            font = QFont("Arial", DEFAULT_TEXT_SIZE, QFont.Bold)
            self.label.setFont(font)
            br = self.label.boundingRect()
            self.label.setPos(radius + 2, -br.height()/2)
            self.label.setZValue(101)
        else:
            self.label = None  # Нет номера для дополнительных точек

    def update_label(self, new_number: int):
        """Обновить номер точки"""
        if self.label:
            self.label.setText(str(new_number))
    
    def update_style(self):
        """Обновить стиль точки"""
        if self.is_selected:
            self.setBrush(QBrush(COLOR_SELECTED))
            self.setPen(QPen(Qt.white, 3))
        elif self.is_hovered:
            self.setBrush(QBrush(QColor(255, 255, 0)))
            self.setPen(QPen(Qt.white, 2))
        else:
            self.setBrush(QBrush(self.point_color))
            pen_color = Qt.yellow if self.is_problem else Qt.white
            self.setPen(QPen(pen_color, 2 if self.is_problem else 1))
    
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
    """Метка крыла (номер)"""
    
    def __init__(self, wing_idx: int, cx: float, cy: float, is_ok: bool):
        super().__init__(f"[{wing_idx + 1}]")
        self.setPos(cx - 50, cy - 200)
        color = COLOR_WING_OK if is_ok else COLOR_WING_PROBLEM
        self.setBrush(QBrush(color))
        font = QFont("Arial", 64, QFont.Bold)
        self.setFont(font)
        self.setZValue(99)


class ResizeHandle(QGraphicsRectItem):
    """Ручка для изменения размера рамки"""

    def __init__(self, position, parent=None):
        super().__init__(-4, -4, 8, 8, parent)
        self.position = position  # 'tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r'
        self.setBrush(QBrush(QColor(255, 255, 0)))
        self.setPen(QPen(QColor(255, 165, 0), 2))
        self.setZValue(52)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.setCursor(self._get_cursor())

    def _get_cursor(self):
        """Получить курсор для ручки"""
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

        # Подпись рамки с номером крыла
        self.label = QGraphicsSimpleTextItem(f"Крыло #{wing_idx + 1}", self)
        self.label.setBrush(QBrush(QColor(255, 165, 0)))
        font = QFont("Arial", 12, QFont.Bold)
        self.label.setFont(font)
        self.label.setPos(5, 5)
        self.label.setZValue(51)

        # Ручки для изменения размера
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

    def update_label(self, new_number: int):
        """Обновить номер рамки"""
        self.wing_idx = new_number - 1
        self.label.setText(f"Крыло #{new_number}")

    def _update_handles(self):
        """Обновить позиции ручек"""
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

    def setRect(self, *args):
        """Переопределяем setRect чтобы обновлять ручки"""
        super().setRect(*args)
        self._update_handles()

    def mousePressEvent(self, event):
        """Обработка нажатия мыши"""
        if event.button() == Qt.LeftButton:
            # Проверяем, нажали ли на ручку
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
        """Обработка перемещения мыши"""
        if self._resizing and self._resize_handle:
            delta = event.scenePos() - self._resize_start_pos
            r = self._resize_start_rect

            new_rect = r
            if 'l' in self._resize_handle:
                new_rect.setLeft(r.left() + delta.x())
            if 'r' in self._resize_handle:
                new_rect.setRight(r.right() + delta.x())
            if 't' in self._resize_handle:
                new_rect.setTop(r.top() + delta.y())
            if 'b' in self._resize_handle:
                new_rect.setBottom(r.bottom() + delta.y())

            # Минимальный размер 20x20
            if new_rect.width() > 20 and new_rect.height() > 20:
                super().setRect(new_rect)
                self._update_handles()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания мыши"""
        if self._resizing:
            self._resizing = False
            self._resize_handle = None
            # Сигнализируем об изменении размера
            if hasattr(self.scene(), 'views') and self.scene().views():
                view = self.scene().views()[0]
                r = self.rect()
                if hasattr(view, 'bbox_changed'):
                    view.bbox_changed.emit(
                        self.wing_idx,
                        r.x(), r.y(),
                        r.x() + r.width(),
                        r.y() + r.height()
                    )
            event.accept()
        else:
            super().mouseReleaseEvent(event)

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