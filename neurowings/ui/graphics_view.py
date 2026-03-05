#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Масштабируемый графический вид
"""

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsRectItem, QMenu, QToolButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor

from ..core.data_models import EditMode
from .graphics_items import PointItem, BBoxItem


class ZoomableGraphicsView(QGraphicsView):
    """Масштабируемый вид с поддержкой редактирования"""
    
    point_clicked = pyqtSignal(int, int, int)
    point_deleted = pyqtSignal(int, int)
    scene_clicked = pyqtSignal(float, float)
    point_moved = pyqtSignal(int, int, float, float)
    bbox_created = pyqtSignal(float, float, float, float)
    bbox_changed = pyqtSignal(int, float, float, float, float)
    bbox_deleted = pyqtSignal(int)
    point_delete_requested = pyqtSignal(int, int)
    bbox_delete_requested = pyqtSignal(int)
    
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._add_scroll_buttons()
        self._position_scroll_buttons()
        
        self._zoom = 1.0
        self._dragging_point = None
        self._drag_start_pos = None
        self.edit_mode = EditMode.VIEW
        
        self._bbox_start = None
        self._bbox_rect = None
    
    def _show_context_menu(self, pos):
        """Показать контекстное меню"""
        item = self.itemAt(pos)
        
        menu = QMenu(self)
        
        if isinstance(item, PointItem):
            act_delete = menu.addAction("🗑 Удалить точку")
            act_delete.triggered.connect(
                lambda: self.point_delete_requested.emit(item.wing_idx, item.point_idx)
            )
        elif isinstance(item, BBoxItem):
            act_delete = menu.addAction("🗑 Удалить рамку")
            act_delete.triggered.connect(
                lambda: self.bbox_delete_requested.emit(item.wing_idx)
            )
        else:
            return
        
        menu.exec_(self.mapToGlobal(pos))
    
    def set_edit_mode(self, mode: EditMode):
        """Установить режим редактирования"""
        self.edit_mode = mode
        if mode == EditMode.VIEW:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        elif mode == EditMode.EDIT:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.ArrowCursor)
        elif mode == EditMode.ADD:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        elif mode == EditMode.BBOX:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)

    def _add_scroll_buttons(self):
        """Добавить стрелки-навигации рядом со скроллами"""
        # Кнопки у вертикального скролла
        self.btn_up = QToolButton(self)
        self.btn_up.setText("▲")
        self.btn_up.setFixedSize(18, 18)
        self.btn_up.clicked.connect(lambda: self._nudge(0, -50))
        self.btn_up.setAutoRaise(True)

        self.btn_down = QToolButton(self)
        self.btn_down.setText("▼")
        self.btn_down.setFixedSize(18, 18)
        self.btn_down.clicked.connect(lambda: self._nudge(0, 50))
        self.btn_down.setAutoRaise(True)

        # Кнопки у горизонтального скролла
        self.btn_left = QToolButton(self)
        self.btn_left.setText("◀")
        self.btn_left.setFixedSize(18, 18)
        self.btn_left.clicked.connect(lambda: self._nudge(-50, 0))
        self.btn_left.setAutoRaise(True)

        self.btn_right = QToolButton(self)
        self.btn_right.setText("▶")
        self.btn_right.setFixedSize(18, 18)
        self.btn_right.clicked.connect(lambda: self._nudge(50, 0))
        self.btn_right.setAutoRaise(True)

        for btn in (self.btn_up, self.btn_down, self.btn_left, self.btn_right):
            btn.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scroll_buttons()

    def _position_scroll_buttons(self):
        """Расположить стрелки у краёв виджета рядом со скроллами"""
        margin = 2
        sb_v = self.verticalScrollBar()
        sb_h = self.horizontalScrollBar()
        # Вертикальные стрелки справа от контента, по центру высоты
        x_v = self.viewport().width() + sb_v.width() - self.btn_up.width() - margin
        mid_y = self.viewport().height() // 2
        self.btn_up.move(x_v, mid_y - self.btn_up.height() - margin)
        self.btn_down.move(x_v, mid_y + margin)
        self.btn_up.raise_()
        self.btn_down.raise_()
        # Горизонтальные стрелки снизу, по центру ширины
        y_h = self.viewport().height() + sb_h.height() - self.btn_left.height() - margin
        mid_x = self.viewport().width() // 2
        self.btn_left.move(mid_x - self.btn_left.width() - margin, y_h)
        self.btn_right.move(mid_x + margin, y_h)
        self.btn_left.raise_()
        self.btn_right.raise_()

    def _nudge(self, dx, dy):
        """Сдвиг вида кнопками-стрелками"""
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
    
    def wheelEvent(self, event):
        """Масштабирование колесом мыши"""
        factor = 1.25
        if event.angleDelta().y() > 0:
            if self._zoom < 50:
                self.scale(factor, factor)
                self._zoom *= factor
        else:
            if self._zoom > 0.05:
                self.scale(1/factor, 1/factor)
                self._zoom /= factor
    
    def keyPressEvent(self, event):
        """Навигация клавиатурой"""
        key = event.key()
        speed = 50
        if key in (Qt.Key_W, Qt.Key_Up):
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - speed)
        elif key in (Qt.Key_S, Qt.Key_Down):
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + speed)
        elif key in (Qt.Key_A, Qt.Key_Left):
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - speed)
        elif key in (Qt.Key_D, Qt.Key_Right):
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + speed)
        else:
            super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            scene_pos = self.mapToScene(event.pos())

            if isinstance(item, PointItem):
                # Всегда посылаем сигнал о клике на точку (для выделения в списке)
                self.point_clicked.emit(item.global_idx, item.wing_idx, item.point_idx)

                # ЛЮБУЮ точку можно редактировать в режиме редактирования
                if self.edit_mode == EditMode.EDIT:
                    self._dragging_point = item
                    self._drag_start_pos = scene_pos
                return  # Всегда выходим после клика на точку

            if self.edit_mode == EditMode.ADD:
                self.scene_clicked.emit(scene_pos.x(), scene_pos.y())
                return
            elif self.edit_mode == EditMode.BBOX:
                self._bbox_start = scene_pos
                self._bbox_rect = QGraphicsRectItem()
                self._bbox_rect.setPen(QPen(QColor(0, 255, 0), 2, Qt.DashLine))
                self._bbox_rect.setBrush(QBrush(QColor(0, 255, 0, 30)))
                self.scene().addItem(self._bbox_rect)
                return

        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        if self._dragging_point is not None:
            self._dragging_point.setPos(scene_pos)
            return
        
        if self._bbox_start is not None and self._bbox_rect is not None:
            x1 = min(self._bbox_start.x(), scene_pos.x())
            y1 = min(self._bbox_start.y(), scene_pos.y())
            x2 = max(self._bbox_start.x(), scene_pos.x())
            y2 = max(self._bbox_start.y(), scene_pos.y())
            self._bbox_rect.setRect(x1, y1, x2 - x1, y2 - y1)
            return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if self._dragging_point is not None:
            pos = self._dragging_point.pos()
            self.point_moved.emit(
                self._dragging_point.wing_idx,
                self._dragging_point.point_idx,
                pos.x(), pos.y()
            )
            self._dragging_point = None
            self._drag_start_pos = None
            return
        
        if self._bbox_start is not None and self._bbox_rect is not None:
            rect = self._bbox_rect.rect()
            self.scene().removeItem(self._bbox_rect)
            if rect.width() > 10 and rect.height() > 10:
                self.bbox_created.emit(
                    rect.x(), rect.y(),
                    rect.x() + rect.width(),
                    rect.y() + rect.height()
                )
            self._bbox_start = None
            self._bbox_rect = None
            return
        
        super().mouseReleaseEvent(event)
    
    def fit_in_view(self):
        """Подогнать вид под содержимое"""
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = 1.0
