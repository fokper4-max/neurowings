#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет интерпретации данных
"""

import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

from ..core.constants import BREEDS
from ..core.data_models import ImageData


class InterpretationWidget(QWidget):
    """Виджет экспертной интерпретации данных"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("🐝 Интерпретация данных")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0;")
        layout.addWidget(title)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #222222;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.text_edit)
    
    def update_interpretation(self, image_data: ImageData):
        """Обновить интерпретацию для изображения"""
        if not image_data or not image_data.wings:
            self.text_edit.setText("Нет данных для интерпретации")
            return
        
        image_data.analyze_all_wings()
        wings = image_data.wings
        
        ci_values = [w.analysis.CI for w in wings if w.analysis and w.analysis.CI > 0]
        dsa_values = [w.analysis.DsA for w in wings if w.analysis]
        hi_values = [w.analysis.HI for w in wings if w.analysis and w.analysis.HI > 0]
        
        if not ci_values:
            self.text_edit.setText("Недостаточно данных для анализа")
            return
        
        mean_ci = np.mean(ci_values)
        mean_dsa = np.mean(dsa_values)
        mean_hi = np.mean(hi_values)
        
        identified = sum(1 for w in wings if w.analysis and w.analysis.is_identified)
        total = len(wings)
        id_pct = 100 * identified / total if total > 0 else 0
        
        text = f"""<h3>📊 Экспертный анализ пробы</h3>

<p><b>Общая характеристика:</b></p>
<ul>
<li>Исследовано крыльев: {total}</li>
<li>Идентифицировано: {identified} ({id_pct:.1f}%)</li>
</ul>

<p><b>Морфометрические показатели:</b></p>
<ul>
<li>Кубитальный индекс: {mean_ci:.3f} (норма Mellifera: 0.76-2.16)</li>
<li>Дискоидальное смещение: {mean_dsa:.2f} (норма Mellifera: -15.31 - 0.00)</li>
<li>Гантельный индекс: {mean_hi:.3f} (норма Mellifera: 0.616-0.923)</li>
</ul>

<p><b>Интерпретация:</b></p>
"""
        
        # Анализ CI
        if mean_ci < 1.7:
            text += "<p>✅ <b>Кубитальный индекс</b> указывает на чистопородность (Mellifera)</p>"
        elif mean_ci < 2.1:
            text += "<p>⚠️ <b>Кубитальный индекс</b> находится в пограничной зоне</p>"
        else:
            text += "<p>❌ <b>Кубитальный индекс</b> указывает на гибридизацию</p>"
        
        # Анализ DsA
        if mean_dsa < -3:
            text += "<p>✅ <b>Дискоидальное смещение</b> отрицательное - типично для Mellifera</p>"
        elif mean_dsa < 0:
            text += "<p>⚠️ <b>Дискоидальное смещение</b> слабо отрицательное</p>"
        else:
            text += "<p>❌ <b>Дискоидальное смещение</b> положительное - нетипично для Mellifera</p>"
        
        # Анализ HI
        if mean_hi < 0.85:
            text += "<p>✅ <b>Гантельный индекс</b> в норме для Mellifera</p>"
        elif mean_hi < 0.923:
            text += "<p>⚠️ <b>Гантельный индекс</b> в верхней границе нормы</p>"
        else:
            text += "<p>❌ <b>Гантельный индекс</b> выше нормы для Mellifera</p>"
        
        # Общий вывод
        text += "<hr><p><b>Заключение:</b></p>"
        if id_pct >= 90 and mean_ci < 1.7 and mean_dsa < -3:
            text += "<p style='color: #4CAF50;'>🐝 Семья соответствует стандарту породы Mellifera с высокой вероятностью</p>"
        elif id_pct >= 70:
            text += "<p style='color: #FFC107;'>⚠️ Семья имеет признаки гибридизации, требуется дополнительный анализ</p>"
        else:
            text += "<p style='color: #f44336;'>❌ Семья не соответствует стандарту чистопородности</p>"
        
        self.text_edit.setHtml(text)
