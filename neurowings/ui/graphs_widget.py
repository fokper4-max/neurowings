#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет графиков
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ..core.constants import BREEDS

# Проверка matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class ScalableGraphLabel(QLabel):
    """QLabel с автомасштабированием изображения"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._pixmap = None
        self.setMinimumHeight(450)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self._update_scaled_pixmap()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()
    
    def _update_scaled_pixmap(self):
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            super().setPixmap(scaled)


class GraphsWidget(QWidget):
    """Виджет с интерактивными графиками"""
    
    wing_clicked = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.wing_data = []
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(20)
        
        self.graph_ci = ScalableGraphLabel("КУБИТАЛЬНЫЙ ИНДЕКС\n\nДанные не загружены")
        self.graph_ci.setAlignment(Qt.AlignCenter)
        self.graph_ci.setStyleSheet("background-color: #ffffff; border: 1px solid #cccccc; border-radius: 5px; color: #222222;")
        layout.addWidget(self.graph_ci)

        self.graph_dsa = ScalableGraphLabel("ДИСКОИДАЛЬНОЕ СМЕЩЕНИЕ\n\nДанные не загружены")
        self.graph_dsa.setAlignment(Qt.AlignCenter)
        self.graph_dsa.setStyleSheet("background-color: #ffffff; border: 1px solid #cccccc; border-radius: 5px; color: #222222;")
        layout.addWidget(self.graph_dsa)

        self.graph_hi = ScalableGraphLabel("ГАНТЕЛЬНЫЙ ИНДЕКС\n\nДанные не загружены")
        self.graph_hi.setAlignment(Qt.AlignCenter)
        self.graph_hi.setStyleSheet("background-color: #ffffff; border: 1px solid #cccccc; border-radius: 5px; color: #222222;")
        layout.addWidget(self.graph_hi)
        
        layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
    
    def update_graphs(self, ci_values, dsa_values, hi_values, wing_numbers=None):
        """Обновить графики с данными о крыльях"""
        if not MATPLOTLIB_AVAILABLE:
            self.graph_ci.setText("matplotlib не установлен")
            return
        
        try:
            import numpy as np
            from io import BytesIO

            plt.style.use('default')  # Светлая тема

            # Сохраняем данные для интерактивности
            self.wing_data = []
            if wing_numbers:
                for i, (ci, dsa, hi) in enumerate(zip(ci_values, dsa_values, hi_values)):
                    self.wing_data.append((wing_numbers[i] if i < len(wing_numbers) else i, ci, dsa, hi))
            
            def create_histogram(values, title, xlabel, breed_ranges, label_widget, color):
                if not values:
                    label_widget.setText(f"{title}\n\nНет данных")
                    return
                
                # Увеличенный размер и разрешение
                fig, ax = plt.subplots(figsize=(16, 7), dpi=150)
                fig.patch.set_facecolor('#ffffff')
                ax.set_facecolor('#f9f9f9')

                fig.suptitle(title, fontsize=18, color='#222222', fontweight='bold', y=0.98)
                
                # Гистограмма
                n, bins, patches = ax.hist(values, bins=15, color=color, edgecolor='#333333', alpha=0.7)

                # Аннотации над столбцами
                bin_wings = {i: [] for i in range(len(bins) - 1)}
                for wing_idx, val in enumerate(values):
                    for i in range(len(bins) - 1):
                        if bins[i] <= val < bins[i + 1] or (i == len(bins) - 2 and val == bins[i + 1]):
                            bin_wings[i].append(wing_idx + 1)
                            break

                for i, (count, patch) in enumerate(zip(n, patches)):
                    if count > 0 and bin_wings[i]:
                        wings_str = ','.join(map(str, bin_wings[i][:5]))
                        if len(bin_wings[i]) > 5:
                            wings_str += f'...+{len(bin_wings[i]) - 5}'
                        ax.annotate(f'№{wings_str}',
                                    xy=(patch.get_x() + patch.get_width() / 2, count),
                                    ha='center', va='bottom', fontsize=13, color='#cc6600',
                                    rotation=45, fontweight='bold')

                mean = np.mean(values)
                ax.axvline(mean, color='#ff8800', linestyle='--', linewidth=2,
                           label=f'Среднее = {mean:.3f}')

                breed_colors = {
                    'Mellifera': '#ff6b6b', 'Caucasica': '#51cf66',
                    'Ligustica': '#339af0', 'Carnica': '#cc5de8'
                }
                for breed, (vmin, vmax) in breed_ranges.items():
                    ax.axvspan(vmin, vmax, alpha=0.15, color=breed_colors.get(breed, 'gray'), label=breed)

                # Автомасштабирование: показываем только область с данными
                data_min, data_max = min(values), max(values)
                data_range = data_max - data_min
                margin = data_range * 0.1 if data_range > 0 else 0.5  # 10% запас по краям
                ax.set_xlim(data_min - margin, data_max + margin)

                ax.set_xlabel(xlabel, fontsize=14, color='#222222')
                ax.set_ylabel('Количество крыльев', fontsize=14, color='#222222')
                ax.tick_params(colors='#222222', labelsize=12)
                ax.legend(fontsize=10, loc='upper right', facecolor='#ffffff', edgecolor='#cccccc')
                ax.grid(True, alpha=0.3, linestyle='--', color='#999999')

                # Настраиваем границы графика
                for spine in ax.spines.values():
                    spine.set_edgecolor('#cccccc')

                plt.tight_layout(rect=[0, 0, 1, 0.95])

                buf = BytesIO()
                fig.savefig(buf, format='png', facecolor='#ffffff', bbox_inches='tight')
                buf.seek(0)
                plt.close(fig)
                
                pixmap = QPixmap()
                pixmap.loadFromData(buf.getvalue())
                label_widget.setPixmap(pixmap)
            
            ci_ranges = {b: r['CI'] for b, r in BREEDS.items()}
            create_histogram(ci_values, 'КУБИТАЛЬНЫЙ ИНДЕКС', 'CI', ci_ranges, self.graph_ci, '#5dade2')
            
            dsa_ranges = {b: r['DsA'] for b, r in BREEDS.items()}
            create_histogram(dsa_values, 'ДИСКОИДАЛЬНОЕ СМЕЩЕНИЕ', 'Градусы', dsa_ranges, self.graph_dsa, '#58d68d')
            
            hi_ranges = {b: r['HI'] for b, r in BREEDS.items()}
            create_histogram(hi_values, 'ГАНТЕЛЬНЫЙ ИНДЕКС', 'HI', hi_ranges, self.graph_hi, '#f5b041')
            
        except Exception as e:
            self.graph_ci.setText(f"Ошибка построения графиков: {e}")
