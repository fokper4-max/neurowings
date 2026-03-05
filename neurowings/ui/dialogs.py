#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Диалоговые окна
"""

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QSpinBox, QPushButton, QDialogButtonBox, QColorDialog
)
from PyQt5.QtGui import QColor


class PointSettingsDialog(QDialog):
    """Диалог настроек отображения точек"""
    
    def __init__(self, current_radius, current_color, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки точек")
        self.setModal(True)
        
        layout = QFormLayout(self)
        
        self.spin_radius = QSpinBox()
        self.spin_radius.setRange(1, 20)
        self.spin_radius.setValue(current_radius)
        layout.addRow("Радиус точки (px):", self.spin_radius)
        
        self.btn_color = QPushButton()
        self.selected_color = current_color
        self._update_color_button()
        self.btn_color.clicked.connect(self._choose_color)
        layout.addRow("Цвет точки:", self.btn_color)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def _update_color_button(self):
        """Обновить цвет кнопки"""
        self.btn_color.setStyleSheet(
            f"background-color: {self.selected_color.name()}; min-width: 60px; min-height: 25px;"
        )
    
    def _choose_color(self):
        """Выбрать цвет"""
        color = QColorDialog.getColor(self.selected_color, self)
        if color.isValid():
            self.selected_color = color
            self._update_color_button()
    
    def get_settings(self):
        """Получить настройки"""
        return self.spin_radius.value(), self.selected_color
