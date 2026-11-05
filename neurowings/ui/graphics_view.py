#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Масштабируемый графический вид (v2.2.0)
"""

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsRectItem, QMenu, QToolButton, QWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRectF
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QCursor, QPixmap

from ..core.data_models import EditMode
from .graphics_items import PointItem, BBoxItem


def _make_crosshair_cursor(color: QColor, size: int = 24, thickness: int = 2) -> QCursor:
    """Создать яркий курсор-перекрестие с тёмной обводкой для контраста на любом фоне."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    from PyQt5.QtGui import QPainter as _P
    p = _P(pm)
    p.setRenderHint(_P.Antialiasing, False)
    mid = size // 2
    gap = 2  # зазор в центре для точности прицеливания

    # Тёмная обводка (чёрная, толще на 2 px)
    outline = QPen(QColor(0, 0, 0), thickness + 2)
    p.setPen(outline)
    p.drawLine(mid, 0, mid, mid - gap)        # верх
    p.drawLine(mid, mid + gap, mid, size - 1)  # низ
    p.drawLine(0, mid, mid - gap, mid)        # лево
    p.drawLine(mid + gap, mid, size - 1, mid)  # право

    # Яркий цвет
    bright = QPen(color, thickness)
    p.setPen(bright)
    p.drawLine(mid, 0, mid, mid - gap)
    p.drawLine(mid, mid + gap, mid, size - 1)
    p.drawLine(0, mid, mid - gap, mid)
    p.drawLine(mid + gap, mid, size - 1, mid)

    # Центральная точка
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    p.drawEllipse(mid - 1, mid - 1, 3, 3)
    p.end()
    return QCursor(pm, mid, mid)


# Кэшируем курсоры, чтобы не создавать заново каждый раз
_CURSOR_EDIT = None
_CURSOR_ADD = None
_CURSOR_BBOX = None


def _get_cached_cursors():
    """Ленивая инициализация курсоров (QPixmap нельзя до QApplication)."""
    global _CURSOR_EDIT, _CURSOR_ADD, _CURSOR_BBOX
    if _CURSOR_EDIT is None:
        _CURSOR_EDIT = _make_crosshair_cursor(QColor(0, 255, 255), 24, 2)    # голубой
        _CURSOR_ADD = _make_crosshair_cursor(QColor(255, 255, 0), 24, 2)     # жёлтый
        _CURSOR_BBOX = _make_crosshair_cursor(QColor(0, 255, 100), 24, 2)    # зелёный
    return _CURSOR_EDIT, _CURSOR_ADD, _CURSOR_BBOX


class ZoomableGraphicsView(QGraphicsView):
    """Масштабируемый вид с поддержкой редактирования и перетаскивания точек в режиме просмотра"""

    point_clicked = pyqtSignal(int, int, int)
    point_deleted = pyqtSignal(int, int)
    scene_clicked = pyqtSignal(float, float)
    point_moved = pyqtSignal(int, int, float, float)
    bbox_created = pyqtSignal(float, float, float, float)
    bbox_changed = pyqtSignal(int, float, float, float, float)
    bbox_deleted = pyqtSignal(int)
    point_delete_requested = pyqtSignal(int, int)
    bbox_delete_requested = pyqtSignal(int)
    wing_reset_requested = pyqtSignal(int)
    bbox_recognize_requested = pyqtSignal(int)

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

        self._fit_mode = True
        self._zoom = self.transform().m11()
        self._dragging_point = None
        self._drag_start_pos = None
        self.edit_mode = EditMode.VIEW

        self._bbox_start = None
        self._bbox_rect = None

    def _show_context_menu(self, pos):
        """Показать контекстное меню"""
        item = self.itemAt(pos)
        if item is not None and isinstance(item.parentItem(), PointItem):
            item = item.parentItem()
        elif item is not None and isinstance(item.parentItem(), BBoxItem):
            item = item.parentItem()

        menu = QMenu(self)

        if isinstance(item, PointItem) and item.global_idx >= 0:
            act_reset = menu.addAction(f"🔄 Сбросить точки крыла №{item.wing_idx + 1} (к нейросети/TPS)")
            act_reset.triggered.connect(
                lambda: self.wing_reset_requested.emit(item.wing_idx)
            )
            menu.addSeparator()
            act_delete = menu.addAction(f"🗑 Удалить точку №{item.point_idx + 1}")
            act_delete.triggered.connect(
                lambda: self.point_delete_requested.emit(item.wing_idx, item.point_idx)
            )
            act_del_wing = menu.addAction(f"🗑 Удалить всё крыло №{item.wing_idx + 1}")
            act_del_wing.triggered.connect(
                lambda: self.bbox_delete_requested.emit(item.wing_idx)
            )
        elif isinstance(item, BBoxItem):
            act_rec = menu.addAction(f"⚡ Распознать 8 точек в рамке (Крыло №{item.wing_idx + 1})")
            act_rec.triggered.connect(
                lambda: self.bbox_recognize_requested.emit(item.wing_idx)
            )
            menu.addSeparator()
            act_delete = menu.addAction("🗑 Удалить рамку и крыло")
            act_delete.triggered.connect(
                lambda: self.bbox_delete_requested.emit(item.wing_idx)
            )
        else:
            return

        menu.exec_(self.mapToGlobal(pos))

    def set_edit_mode(self, mode: EditMode):
        """Установить режим редактирования с яркими контрастными курсорами"""
        self.edit_mode = mode
        cur_edit, cur_add, cur_bbox = _get_cached_cursors()
        if mode == EditMode.VIEW:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        elif mode == EditMode.EDIT:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(cur_edit)
        elif mode == EditMode.ADD:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(cur_add)
        elif mode == EditMode.BBOX:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(cur_bbox)

    def _add_scroll_buttons(self):
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

    # resizeEvent определён ниже вместе с миникартой

    def _position_scroll_buttons(self):
        margin = 2
        sb_v = self.verticalScrollBar()
        sb_h = self.horizontalScrollBar()
        x_v = self.viewport().width() + sb_v.width() - self.btn_up.width() - margin
        mid_y = self.viewport().height() // 2
        self.btn_up.move(x_v, mid_y - self.btn_up.height() - margin)
        self.btn_down.move(x_v, mid_y + margin)
        self.btn_up.raise_()
        self.btn_down.raise_()
        y_h = self.viewport().height() + sb_h.height() - self.btn_left.height() - margin
        mid_x = self.viewport().width() // 2
        self.btn_left.move(mid_x - self.btn_left.width() - margin, y_h)
        self.btn_right.move(mid_x + margin, y_h)
        self.btn_left.raise_()
        self.btn_right.raise_()

    def _nudge(self, dx, dy):
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)

    def wheelEvent(self, event):
        self._fit_mode = False
        factor = 1.25
        if event.angleDelta().y() > 0:
            if self._zoom < 50:
                self.scale(factor, factor)
                self._zoom *= factor
        else:
            if self._zoom > 0.05:
                self.scale(1 / factor, 1 / factor)
                self._zoom /= factor

    def keyPressEvent(self, event):
        key = event.key()
        speed = 50

        # Space/Enter = «клик» под курсором (режимы ADD и BBOX)
        if key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if self.edit_mode == EditMode.ADD:
                cursor_pos = self.mapFromGlobal(QCursor.pos())
                scene_pos = self.mapToScene(cursor_pos)
                self.scene_clicked.emit(scene_pos.x(), scene_pos.y())
                return
            elif self.edit_mode == EditMode.BBOX and self._bbox_start is None:
                cursor_pos = self.mapFromGlobal(QCursor.pos())
                scene_pos = self.mapToScene(cursor_pos)
                self._bbox_start = scene_pos
                self._bbox_rect = QGraphicsRectItem()
                self._bbox_rect.setPen(QPen(QColor(0, 255, 0), 2, Qt.DashLine))
                self._bbox_rect.setBrush(QBrush(QColor(0, 255, 0, 30)))
                self.scene().addItem(self._bbox_rect)
                return

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
            if item is not None and isinstance(item.parentItem(), PointItem):
                item = item.parentItem()
            scene_pos = self.mapToScene(event.pos())

            if isinstance(item, PointItem) and item.global_idx >= 0:
                self.point_clicked.emit(item.global_idx, item.wing_idx, item.point_idx)

                # Разрешаем перетаскивать точку мышкой как в режиме EDIT, так и прямо в режиме VIEW!
                if self.edit_mode in (EditMode.EDIT, EditMode.VIEW):
                    self._dragging_point = item
                    self._drag_start_pos = scene_pos
                return

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
            start = self._drag_start_pos
            wing_idx = self._dragging_point.wing_idx
            point_idx = self._dragging_point.point_idx
            self._dragging_point = None
            self._drag_start_pos = None
            if start is None or abs(pos.x() - start.x()) > 0.01 or abs(pos.y() - start.y()) > 0.01:
                self.point_moved.emit(wing_idx, point_idx, pos.x(), pos.y())
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
        self._fit_mode = True
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()

    # ---- Миникарта (Панорамный обзор) ----

    def _ensure_minimap(self):
        """Создать миникарту при первом использовании."""
        if hasattr(self, '_minimap') and self._minimap is not None:
            return
        self._minimap = MiniMapWidget(self)
        self._minimap.navigation_requested.connect(self._navigate_to)
        self._minimap.show()
        self._position_minimap()

    def _position_minimap(self):
        """Расположить миникарту в правом верхнем углу вьюпорта."""
        if not hasattr(self, '_minimap') or self._minimap is None:
            return
        vp = self.viewport()
        m = self._minimap
        margin = 8
        m.move(vp.width() - m.width() - margin, margin)
        m.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "btn_up"):
            self._position_scroll_buttons()
        if getattr(self, "_fit_mode", False):
            self.fit_in_view()
        self._position_minimap()
        self._sync_minimap()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._sync_minimap()

    def _sync_minimap(self):
        """Обновить прямоугольник видимой области на миникарте."""
        if not hasattr(self, '_minimap') or self._minimap is None or self._minimap.isHidden():
            return
        scene_rect = self.sceneRect()
        if scene_rect.isEmpty():
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        self._minimap.update_viewport_rect(scene_rect, visible)

    def _navigate_to(self, scene_center_x: float, scene_center_y: float):
        """Переместить вид так, чтобы (scene_center_x, scene_center_y) стал центром."""
        from PyQt5.QtCore import QPointF
        self.centerOn(QPointF(scene_center_x, scene_center_y))

    def toggle_minimap(self):
        """Показать/скрыть миникарту."""
        if not hasattr(self, '_minimap') or self._minimap is None:
            self._ensure_minimap()
            self._sync_minimap()
        elif self._minimap.isVisible():
            self._minimap.hide()
        else:
            self._minimap.show()
            self._position_minimap()
            self._sync_minimap()


class MiniMapWidget(QWidget):
    """Маленькая миникарта (панорамный обзор) с перетаскиваемым прямоугольником видимой области."""

    navigation_requested = pyqtSignal(float, float)

    MINIMAP_W = 180
    MINIMAP_H = 130

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.MINIMAP_W, self.MINIMAP_H)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        self._scene_rect = QRectF()
        self._view_rect = QRectF()
        self._dragging = False

    def update_viewport_rect(self, scene_rect: QRectF, visible_rect: QRectF):
        self._scene_rect = scene_rect
        self._view_rect = visible_rect
        self.update()

    def _scene_to_widget(self, sx: float, sy: float):
        """Координаты сцены → координаты виджета."""
        sr = self._scene_rect
        if sr.width() < 1 or sr.height() < 1:
            return 0.0, 0.0
        margin = 4
        w = self.width() - margin * 2
        h = self.height() - margin * 2
        scale = min(w / sr.width(), h / sr.height())
        ow = sr.width() * scale
        oh = sr.height() * scale
        ox = margin + (w - ow) / 2.0
        oy = margin + (h - oh) / 2.0
        return ox + (sx - sr.x()) * scale, oy + (sy - sr.y()) * scale

    def _widget_to_scene(self, wx: float, wy: float):
        """Координаты виджета → координаты сцены."""
        sr = self._scene_rect
        if sr.width() < 1 or sr.height() < 1:
            return sr.center().x(), sr.center().y()
        margin = 4
        w = self.width() - margin * 2
        h = self.height() - margin * 2
        scale = min(w / sr.width(), h / sr.height())
        ow = sr.width() * scale
        oh = sr.height() * scale
        ox = margin + (w - ow) / 2.0
        oy = margin + (h - oh) / 2.0
        return sr.x() + (wx - ox) / scale, sr.y() + (wy - oy) / scale

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter as _P
        p = _P(self)
        p.setRenderHint(_P.Antialiasing)

        # Полупрозрачный фон
        p.fillRect(self.rect(), QColor(30, 30, 30, 180))

        sr = self._scene_rect
        if sr.width() < 1 or sr.height() < 1:
            p.end()
            return

        # Рамка сцены (светло-серая)
        x1, y1 = self._scene_to_widget(sr.x(), sr.y())
        x2, y2 = self._scene_to_widget(sr.x() + sr.width(), sr.y() + sr.height())
        p.setPen(QPen(QColor(100, 100, 100), 1))
        p.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

        # Прямоугольник видимой области (красный)
        vr = self._view_rect
        vx1, vy1 = self._scene_to_widget(vr.x(), vr.y())
        vx2, vy2 = self._scene_to_widget(vr.x() + vr.width(), vr.y() + vr.height())
        p.setPen(QPen(QColor(255, 50, 50), 2))
        p.setBrush(QBrush(QColor(255, 50, 50, 40)))
        p.drawRect(QRectF(vx1, vy1, vx2 - vx1, vy2 - vy1))

        # Надпись
        p.setPen(QColor(180, 180, 180))
        from PyQt5.QtGui import QFont as _F
        p.setFont(_F("Arial", 8))
        p.drawText(4, self.height() - 4, "📍 Обзор")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            sx, sy = self._widget_to_scene(event.pos().x(), event.pos().y())
            self.navigation_requested.emit(sx, sy)

    def mouseMoveEvent(self, event):
        if self._dragging:
            sx, sy = self._widget_to_scene(event.pos().x(), event.pos().y())
            self.navigation_requested.emit(sx, sy)

    def mouseReleaseEvent(self, event):
        self._dragging = False
