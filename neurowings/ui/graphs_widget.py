#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет графиков (2D-карта породности + 3 варианта визуала графиков CI, DsA, HI,
включая точный вид 1:1 как в Excel В. А. Карташёва «Порода по крыльям в. 2.5»).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ..core.constants import (
    BREEDS, CLASSIC_BREEDS, BREED_NAMES_RU, BREED_COLORS_HEX, BREED_SHORT_NAMES_RU
)
from ..core.calculations import (
    identify_breed,
    calculate_breed_distance,
    calculate_breed_probability,
    KARTASHOV_CI_BOUNDS,
    KARTASHOV_DSA_BOUNDS,
    KARTASHOV_HI_BOUNDS,
)

# Проверка matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Ellipse
    from matplotlib.ticker import MultipleLocator
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Эталонные цвета 4 классических пород из Excel В. А. Карташёва «Порода по крыльям в. 2.5»
KARTASHOV_BREED_COLORS = {
    "Mellifera": "#0033CC",   # Синий
    "Caucasica": "#993300",   # Коричневый
    "Ligustica": "#FFCC00",   # Жёлтый
    "Carnica":   "#008000",   # Зелёный
    "Carpatica": "#008000",   # Зелёный (для регионального экотипа)
    "Macedonica": "#0ca678",
}


class ScalableGraphLabel(QLabel):
    """QLabel с автомасштабированием изображения"""

    def __init__(self, text="", parent=None, min_height: int = 420):
        super().__init__(text, parent)
        self._pixmap = None
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self._update_scaled_pixmap()

    def setText(self, text):
        self._pixmap = None
        super().setText(text)

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
    """Виджет с 2D-картой породности семьи и 3 вариантами графиков CI, DsA, HI"""

    wing_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wing_data = []
        self._pending_data = None
        self._graphs_dirty = False
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(20)

        card_style = (
            "background-color: #ffffff; border: 1px solid #cccccc; "
            "border-radius: 5px; color: #222222;"
        )

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        lbl_style = QLabel("📈 <b>Вид графиков:</b>")
        lbl_style.setStyleSheet("color: #222222;")
        top_bar.addWidget(lbl_style)

        self.combo_chart_style = QComboBox()
        self.combo_chart_style.addItems([
            "📊 Столбчатые гистограммы (классический вид)",
            "📉 Гистограммы + плавная кривая плотности",
            "📊 Как в Excel «Порода по крыльям» (Карташёв в. 2.5)",
        ])
        self.combo_chart_style.setCurrentIndex(2)
        self.combo_chart_style.setToolTip(
            "Выберите вариант визуализации графиков:\n"
            "1) Классические столбчатые гистограммы\n"
            "2) Гистограммы + плавная кривая плотности (KDE)\n"
            "3) Точный вид как в Excel-программе В. А. Карташёва «Порода по крыльям в. 2.5» "
            "(матрица 2×2 + частотные графики по классам с зелёными и красными границами)"
        )
        self.combo_chart_style.currentIndexChanged.connect(self._on_chart_options_changed)
        top_bar.addWidget(self.combo_chart_style)

        lbl_breed = QLabel("🐝 <b>Порода для границ:</b>")
        lbl_breed.setStyleSheet("color: #222222; margin-left: 6px;")
        top_bar.addWidget(lbl_breed)

        self.combo_excel_breed = QComboBox()
        self.combo_excel_breed.addItem("Авто (превалирующая порода)", "auto")
        for b_key, b_name_ru in BREED_NAMES_RU.items():
            self.combo_excel_breed.addItem(b_name_ru, b_key)
        self.combo_excel_breed.setToolTip(
            "Порода, для которой на графиках Карташёва рисуются зелёные вертикальные границы стандарта "
            "и красные границы 1-го ранга гибридизации (±3 класса)"
        )
        self.combo_excel_breed.currentIndexChanged.connect(self._on_chart_options_changed)
        top_bar.addWidget(self.combo_excel_breed)

        lbl_map = QLabel("🗺 <b>Верхняя панель:</b>")
        lbl_map.setStyleSheet("color: #222222; margin-left: 6px;")
        top_bar.addWidget(lbl_map)

        self.combo_2d_mode = QComboBox()
        self.combo_2d_mode.addItems([
            "Авто (Матрица 2×2 Карташёва / Двойная 2D-карта)",
            "Крупно: Дискоидальное смещение (DsA) ↔ Кубитальный индекс (CI)",
            "Крупно: Гантельный индекс (HI) ↔ Кубитальный индекс (CI)",
            "Скрыть верхнюю карту (только 3 графика индексов)",
        ])
        self.combo_2d_mode.currentIndexChanged.connect(self._on_2d_mode_changed)
        top_bar.addWidget(self.combo_2d_mode)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.graph_map_2d = ScalableGraphLabel(
            "2D-КАРТА ПОРОДНОСТИ СЕМЬИ (DsA ↔ CI и HI ↔ CI)\n\nДанные не загружены",
            min_height=480,
        )
        self.graph_map_2d.setAlignment(Qt.AlignCenter)
        self.graph_map_2d.setStyleSheet(card_style)
        layout.addWidget(self.graph_map_2d)

        self.graph_ci = ScalableGraphLabel("КУБИТАЛЬНЫЙ ИНДЕКС\n\nДанные не загружены")
        self.graph_ci.setAlignment(Qt.AlignCenter)
        self.graph_ci.setStyleSheet(card_style)
        layout.addWidget(self.graph_ci)

        self.graph_dsa = ScalableGraphLabel("ДИСКОИДАЛЬНОЕ СМЕЩЕНИЕ\n\nДанные не загружены")
        self.graph_dsa.setAlignment(Qt.AlignCenter)
        self.graph_dsa.setStyleSheet(card_style)
        layout.addWidget(self.graph_dsa)

        self.graph_hi = ScalableGraphLabel("ГАНТЕЛЬНЫЙ ИНДЕКС\n\nДанные не загружены")
        self.graph_hi.setAlignment(Qt.AlignCenter)
        self.graph_hi.setStyleSheet(card_style)
        layout.addWidget(self.graph_hi)

        layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def set_target_breed(self, breed_key: str):
        """Установить породу для вертикальных границ стандарта на графиках."""
        idx = self.combo_excel_breed.findData(breed_key or "auto")
        if idx >= 0 and idx != self.combo_excel_breed.currentIndex():
            self.combo_excel_breed.setCurrentIndex(idx)

    def clear_graphs(self, message: str = "Нет данных"):
        self._pending_data = None
        self._graphs_dirty = False
        for graph in (self.graph_map_2d, self.graph_ci, self.graph_dsa, self.graph_hi):
            graph.setText(message)

    def schedule_update(self, ci_values, dsa_values, hi_values, wing_numbers=None, force: bool = False):
        """Отложенное (ленивое) обновление графиков: рендерит сразу только если вкладка открыта или force=True."""
        self._pending_data = (
            list(ci_values or []),
            list(dsa_values or []),
            list(hi_values or []),
            list(wing_numbers) if wing_numbers else None,
        )
        self._graphs_dirty = True
        if force or self.isVisible():
            self.flush_pending()

    def flush_pending(self):
        """Отрисовать отложенные графики, если они помечены как устаревшие."""
        if not self._graphs_dirty or self._pending_data is None:
            return
        ci_v, dsa_v, hi_v, w_nums = self._pending_data
        self._graphs_dirty = False
        self.update_graphs(ci_v, dsa_v, hi_v, w_nums)

    @staticmethod
    def _add_confidence_ellipse(ax, x_vals, y_vals, color="#d9480f"):
        import numpy as np
        x = np.asarray(x_vals, dtype=float)
        y = np.asarray(y_vals, dtype=float)
        if x.size < 3 or y.size < 3:
            return
        cov = np.cov(x, y)
        if not np.all(np.isfinite(cov)):
            return
        vals, vecs = np.linalg.eigh(cov)
        order = vals.argsort()[::-1]
        vals = vals[order]
        vecs = vecs[:, order]
        if vals[0] <= 1e-9 or vals[1] <= 1e-9:
            return
        theta = float(np.degrees(np.arctan2(*vecs[:, 0][::-1])))
        width, height = 2.0 * 2.4477 * np.sqrt(vals)
        ell = Ellipse(
            xy=(float(np.mean(x)), float(np.mean(y))),
            width=float(width),
            height=float(height),
            angle=theta,
            edgecolor=color,
            facecolor=color,
            alpha=0.14,
            linewidth=2.0,
            linestyle="--",
            label="95% эллипс семьи",
            zorder=4,
        )
        ax.add_patch(ell)

    def _render_kartashov_2x2_matrix(self, ci_values, dsa_values, hi_values):
        """
        Отрисовать сводную матрицу 2×2 (Графики 1, 2, 3, 4 с листа «Графики»)
        1:1 как в Excel-программе В. А. Карташёва «Порода по крыльям в. 2.5».
        """
        import numpy as np
        from io import BytesIO

        n_pts = min(len(ci_values), len(dsa_values), len(hi_values))
        ci_arr = np.asarray(ci_values[:n_pts], dtype=float)
        dsa_arr = np.asarray(dsa_values[:n_pts], dtype=float)
        hi_arr = np.asarray(hi_values[:n_pts], dtype=float)

        fig, ((ax_g1, ax_g3), (ax_g2, ax_g4)) = plt.subplots(2, 2, figsize=(13.5, 8.2), dpi=115)
        fig.patch.set_facecolor('#ffffff')
        fig.suptitle(
            "СВОДНЫЕ ГРАФИКИ ИДЕНТИФИКАЦИИ ПОРОДЫ (КАРТАШЁВ В. 2.5, ЛИСТ «ГРАФИКИ»)",
            fontsize=14.0, color='#1a1a1a', fontweight='bold', y=0.99
        )

        # --- График 1 (0, 0): 1. Фактическое и прогнозное распределение пчел по породам ---
        ax_g1.set_facecolor('#ffffff')
        actual_counts = {b: 0 for b in CLASSIC_BREEDS}
        for i in range(n_pts):
            found, _ = identify_breed(float(ci_arr[i]), float(dsa_arr[i]), float(hi_arr[i]))
            for b in CLASSIC_BREEDS:
                if b in found:
                    actual_counts[b] += 1

        sum_actual = sum(actual_counts.values())
        if sum_actual > 0:
            actual_shares = {b: 100.0 * actual_counts[b] / sum_actual for b in CLASSIC_BREEDS}
        else:
            actual_shares = {b: 0.0 for b in CLASSIC_BREEDS}

        probs_raw = {
            b: calculate_breed_probability(list(ci_arr), list(dsa_arr), list(hi_arr), b)
            for b in CLASSIC_BREEDS
        }
        sum_probs = sum(probs_raw.values())
        if sum_probs > 1e-9:
            pred_shares = {b: 100.0 * probs_raw[b] / sum_probs for b in CLASSIC_BREEDS}
        else:
            pred_shares = dict(actual_shares)

        x_bars = [0, 1]
        bottom_act = 0.0
        bottom_pred = 0.0
        for b in CLASSIC_BREEDS:
            val_act = actual_shares[b]
            val_pred = pred_shares[b]
            b_col = KARTASHOV_BREED_COLORS[b]
            b_label = f"{b} ({BREED_SHORT_NAMES_RU.get(b, b)})"
            ax_g1.bar(
                0, val_act, bottom=bottom_act, width=0.42,
                color=b_col, edgecolor='#000000', linewidth=0.9, label=b_label, zorder=3
            )
            ax_g1.bar(
                1, val_pred, bottom=bottom_pred, width=0.42,
                color=b_col, edgecolor='#000000', linewidth=0.9, zorder=3
            )
            if val_act >= 7.0:
                txt_col = '#000000' if b == 'Ligustica' else '#ffffff'
                ax_g1.text(0, bottom_act + val_act * 0.5, f"{val_act:.0f}%", ha='center', va='center', fontsize=8.5, fontweight='bold', color=txt_col, zorder=5)
            if val_pred >= 7.0:
                txt_col = '#000000' if b == 'Ligustica' else '#ffffff'
                ax_g1.text(1, bottom_pred + val_pred * 0.5, f"{val_pred:.0f}%", ha='center', va='center', fontsize=8.5, fontweight='bold', color=txt_col, zorder=5)
            bottom_act += val_act
            bottom_pred += val_pred

        ax_g1.set_title("1. Фактическое и прогнозное распределение пчел по породам", fontsize=10.5, fontweight='bold')
        ax_g1.set_xticks(x_bars)
        ax_g1.set_xticklabels(["Исследованная\nпроба пчел", "Прогнозная\nвероятностная оценка"], fontsize=9.0, fontweight='bold')
        ax_g1.set_ylim(0, 100)
        ax_g1.set_yticks(range(0, 101, 10))
        ax_g1.set_yticklabels([f"{y}%" for y in range(0, 101, 10)], fontsize=8.5)
        ax_g1.grid(True, axis='y', color='#888888', linestyle='-', linewidth=0.6, alpha=0.6, zorder=0)
        ax_g1.legend(fontsize=8.0, loc='center left', bbox_to_anchor=(1.01, 0.5), frameon=True, facecolor='#ffffff', edgecolor='#888888')

        # Статистика семьи (МО ± 1.96 * СКО) для красного прямоугольника
        ci_mean = float(np.mean(ci_arr))
        dsa_mean = float(np.mean(dsa_arr))
        hi_mean = float(np.mean(hi_arr))
        ci_sd = round(float(np.std(ci_arr, ddof=1)), 3) if n_pts > 1 else 0.0
        dsa_sd = round(float(np.std(dsa_arr, ddof=1)), 3) if n_pts > 1 else 0.0
        hi_sd = round(float(np.std(hi_arr, ddof=1)), 3) if n_pts > 1 else 0.0

        fam_bounds = {
            "CI": (ci_mean - 1.96 * ci_sd, ci_mean + 1.96 * ci_sd),
            "DsA": (dsa_mean - 1.96 * dsa_sd, dsa_mean + 1.96 * dsa_sd),
            "HI": (hi_mean - 1.96 * hi_sd, hi_mean + 1.96 * hi_sd),
        }
        means_map = {"CI": ci_mean, "DsA": dsa_mean, "HI": hi_mean}
        arrs_map = {"CI": ci_arr, "DsA": dsa_arr, "HI": hi_arr}

        def _draw_2d_subplot(ax, x_key: str, y_key: str, title: str):
            ax.set_facecolor('#ffffff')
            # Штриховые контуры 4 классических пород (без заливки)
            for b in CLASSIC_BREEDS:
                bx0, bx1 = BREEDS[b][x_key]
                by0, by1 = BREEDS[b][y_key]
                rect_b = Rectangle(
                    (bx0, by0), bx1 - bx0, by1 - by0,
                    facecolor='none', edgecolor=KARTASHOV_BREED_COLORS[b],
                    linestyle='--', linewidth=2.2, label=b, zorder=3
                )
                ax.add_patch(rect_b)

            # Сплошной красный прямоугольник доверительного интервала семьи (МО ± 1.96*СКО)
            fx0, fx1 = fam_bounds[x_key]
            fy0, fy1 = fam_bounds[y_key]
            rect_fam = Rectangle(
                (fx0, fy0), max(1e-4, fx1 - fx0), max(1e-4, fy1 - fy0),
                facecolor='none', edgecolor='#FF0000',
                linestyle='-', linewidth=2.2, label='Интервал семьи (95%)', zorder=5
            )
            ax.add_patch(rect_fam)

            # Точки крыльев (тёмно-бордовые квадратики) и центроид семьи (крупный синий ромбик)
            ax.scatter(
                arrs_map[x_key], arrs_map[y_key],
                marker='s', color='#800000', s=18, label='Крылья', zorder=6
            )
            ax.scatter(
                [means_map[x_key]], [means_map[y_key]],
                marker='D', color='#0000FF', edgecolors='#ffffff', linewidth=0.8,
                s=55, label='МО семьи', zorder=8
            )

            if y_key == "DsA":
                ax.axhline(0.0, color='#000000', linestyle='-', linewidth=1.3, zorder=2)

            ax.set_title(title, fontsize=10.5, fontweight='bold')
            ax.set_xlabel(x_key, fontsize=9.5, fontweight='bold')
            ax.set_ylabel(y_key, fontsize=9.5, fontweight='bold')

            if x_key == "CI":
                ax.set_xlim(min(0.5, float(np.min(ci_arr)) - 0.1), max(6.0, float(np.max(ci_arr)) + 0.2))
                ax.xaxis.set_major_locator(MultipleLocator(0.5))
            elif x_key == "HI":
                ax.set_xlim(min(0.6, float(np.min(hi_arr)) - 0.02), max(1.5, float(np.max(hi_arr)) + 0.02))
                ax.xaxis.set_major_locator(MultipleLocator(0.1))

            if y_key == "HI":
                ax.set_ylim(min(0.6, float(np.min(hi_arr)) - 0.02), max(1.5, float(np.max(hi_arr)) + 0.02))
                ax.yaxis.set_major_locator(MultipleLocator(0.1))
            elif y_key == "DsA":
                ax.set_ylim(min(-16.0, float(np.min(dsa_arr)) - 1.0), max(12.0, float(np.max(dsa_arr)) + 1.0))
                ax.yaxis.set_major_locator(MultipleLocator(2.0))

            ax.tick_params(labelsize=8.5)
            ax.grid(True, color='#888888', linestyle='-', linewidth=0.5, alpha=0.55, zorder=0)

        _draw_2d_subplot(ax_g3, "CI", "HI", "3. Распределение HI / CI")
        _draw_2d_subplot(ax_g2, "CI", "DsA", "2. Распределение DsA / CI")
        _draw_2d_subplot(ax_g4, "HI", "DsA", "4. Распределение DsA / HI")
        ax_g3.legend(fontsize=7.8, loc='upper right', frameon=True, facecolor='#ffffff', edgecolor='#888888')

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        buf = BytesIO()
        fig.savefig(buf, format='png', facecolor='#ffffff', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        self.graph_map_2d.setPixmap(pixmap)

    def _render_2d_map(self, ci_values, dsa_values, hi_values, wing_numbers):
        import numpy as np
        from io import BytesIO

        mode_idx = self.combo_2d_mode.currentIndex() if hasattr(self, "combo_2d_mode") else 0
        if mode_idx == 3:
            self.graph_map_2d.setVisible(False)
            return
        self.graph_map_2d.setVisible(True)

        if not (ci_values and dsa_values and hi_values):
            self.graph_map_2d.setText("2D-КАРТА ПОРОДНОСТИ СЕМЬИ\n\nДанные не загружены")
            return

        style_idx = self.combo_chart_style.currentIndex() if hasattr(self, "combo_chart_style") else 2
        if style_idx == 2 and mode_idx == 0:
            self._render_kartashov_2x2_matrix(ci_values, dsa_values, hi_values)
            return

        if mode_idx == 1:
            fig, ax1 = plt.subplots(1, 1, figsize=(12.5, 5.6), dpi=115)
            ax2 = None
            axes_list = [ax1]
        elif mode_idx == 2:
            fig, ax2 = plt.subplots(1, 1, figsize=(12.5, 5.6), dpi=115)
            ax1 = None
            axes_list = [ax2]
        else:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.6), dpi=115)
            axes_list = [ax1, ax2]

        fig.patch.set_facecolor('#ffffff')
        fig.suptitle(
            "2D-КАРТА ПОРОДНОСТИ СЕМЬИ (ЭТАЛОННЫЕ ЗОНЫ И ДОВЕРИТЕЛЬНЫЙ ЭЛЛИПС)",
            fontsize=15, color='#222222', fontweight='bold', y=0.98
        )

        for ax in axes_list:
            ax.set_facecolor('#f9f9f9')
            for spine in ax.spines.values():
                spine.set_edgecolor('#cccccc')

        for breed, ranges in BREEDS.items():
            color = BREED_COLORS_HEX.get(breed, '#888888')
            label_ru = f"{BREED_SHORT_NAMES_RU.get(breed, breed)} ({breed})"
            dsa_lo, dsa_hi = ranges['DsA']
            ci_lo, ci_hi = ranges['CI']
            hi_lo, hi_hi = ranges['HI']

            if ax1 is not None:
                r1 = Rectangle(
                    (dsa_lo, ci_lo), dsa_hi - dsa_lo, ci_hi - ci_lo,
                    facecolor=color, edgecolor=color, alpha=0.12, linewidth=1.4,
                    label=label_ru, zorder=1
                )
                ax1.add_patch(r1)
                ax1.text(
                    dsa_lo + 0.25, ci_hi - 0.14, BREED_SHORT_NAMES_RU.get(breed, breed),
                    fontsize=8.5, color=color, fontweight='bold', alpha=0.88, zorder=2
                )

            if ax2 is not None:
                r2 = Rectangle(
                    (hi_lo, ci_lo), hi_hi - hi_lo, ci_hi - ci_lo,
                    facecolor=color, edgecolor=color, alpha=0.12, linewidth=1.4,
                    label=label_ru, zorder=1
                )
                ax2.add_patch(r2)
                ax2.text(
                    hi_lo + 0.01, ci_hi - 0.14, BREED_SHORT_NAMES_RU.get(breed, breed),
                    fontsize=8.5, color=color, fontweight='bold', alpha=0.88, zorder=2
                )

        n_pts = min(len(ci_values), len(dsa_values), len(hi_values))
        for idx in range(n_pts):
            ci_v = float(ci_values[idx])
            dsa_v = float(dsa_values[idx])
            hi_v = float(hi_values[idx])
            w_num = wing_numbers[idx] if wing_numbers and idx < len(wing_numbers) else (idx + 1)
            breeds_found, _ = identify_breed(ci_v, dsa_v, hi_v)
            pt_color = '#2b8a3e' if breeds_found else '#e03131'

            if ax1 is not None:
                ax1.scatter(dsa_v, ci_v, c=pt_color, s=42, edgecolors='white', linewidth=0.8, zorder=5)
                ax1.annotate(
                    f"№{w_num}", (dsa_v, ci_v),
                    textcoords="offset points", xytext=(4, 3),
                    fontsize=8, color='#222222', fontweight='bold', zorder=6
                )

            if ax2 is not None:
                ax2.scatter(hi_v, ci_v, c=pt_color, s=42, edgecolors='white', linewidth=0.8, zorder=5)
                ax2.annotate(
                    f"№{w_num}", (hi_v, ci_v),
                    textcoords="offset points", xytext=(4, 3),
                    fontsize=8, color='#222222', fontweight='bold', zorder=6
                )

        mean_ci = float(np.mean(ci_values[:n_pts]))
        mean_dsa = float(np.mean(dsa_values[:n_pts]))
        mean_hi = float(np.mean(hi_values[:n_pts]))

        if ax1 is not None:
            self._add_confidence_ellipse(ax1, dsa_values[:n_pts], ci_values[:n_pts], color="#d9480f")
            ax1.scatter(
                [mean_dsa], [mean_ci], c='#d9480f', marker='X', s=110,
                edgecolors='black', linewidth=1.0,
                label=f'Центроид семьи ({mean_dsa:+.2f}°, {mean_ci:.2f})', zorder=7
            )
            ax1.axvline(0.0, color='#666666', linestyle=':', linewidth=1.2)
            ax1.set_title("Дискоидальное смещение (DsA) ↔ Кубитальный индекс (CI)", fontsize=11.5, fontweight='bold')
            ax1.set_xlabel("Дискоидальное смещение DsA (°)", fontsize=10.5)
            ax1.set_ylabel("Кубитальный индекс CI", fontsize=10.5)
            ax1.set_xlim(min(-16.0, min(dsa_values[:n_pts]) - 1.5), max(13.5, max(dsa_values[:n_pts]) + 1.5))
            ax1.set_ylim(min(0.7, min(ci_values[:n_pts]) - 0.2), max(5.8, max(ci_values[:n_pts]) + 0.3))
            ax1.grid(True, alpha=0.3, linestyle='--')
            ax1.legend(fontsize=8.0, loc='upper left', ncol=2, facecolor='#ffffff', framealpha=0.9)

        if ax2 is not None:
            self._add_confidence_ellipse(ax2, hi_values[:n_pts], ci_values[:n_pts], color="#d9480f")
            ax2.scatter(
                [mean_hi], [mean_ci], c='#d9480f', marker='X', s=110,
                edgecolors='black', linewidth=1.0,
                label=f'Центроид семьи ({mean_hi:.3f}, {mean_ci:.2f})', zorder=7
            )
            ax2.set_title("Гантельный индекс (HI) ↔ Кубитальный индекс (CI)", fontsize=11.5, fontweight='bold')
            ax2.set_xlabel("Гантельный индекс HI", fontsize=10.5)
            ax2.set_ylabel("Кубитальный индекс CI", fontsize=10.5)
            ax2.set_xlim(min(0.58, min(hi_values[:n_pts]) - 0.05), max(1.45, max(hi_values[:n_pts]) + 0.05))
            ax2.set_ylim(min(0.7, min(ci_values[:n_pts]) - 0.2), max(5.8, max(ci_values[:n_pts]) + 0.3))
            ax2.grid(True, alpha=0.3, linestyle='--')
            ax2.legend(fontsize=8.0, loc='upper left', ncol=2, facecolor='#ffffff', framealpha=0.9)

        plt.tight_layout(rect=[0, 0, 1, 0.94])
        buf = BytesIO()
        fig.savefig(buf, format='png', facecolor='#ffffff', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        self.graph_map_2d.setPixmap(pixmap)

    def _on_2d_mode_changed(self, _index: int):
        if self._pending_data is not None:
            ci_v, dsa_v, hi_v, w_nums = self._pending_data
            if ci_v and dsa_v and hi_v:
                self._render_2d_map(ci_v, dsa_v, hi_v, w_nums)
        elif hasattr(self, "combo_2d_mode"):
            self.graph_map_2d.setVisible(self.combo_2d_mode.currentIndex() != 3)

    def _on_chart_options_changed(self, _index: int):
        if self._pending_data is not None:
            ci_v, dsa_v, hi_v, w_nums = self._pending_data
            if ci_v and dsa_v and hi_v:
                self._render_2d_map(ci_v, dsa_v, hi_v, w_nums)
                self._render_index_charts(ci_v, dsa_v, hi_v, w_nums)

    def _resolve_active_breed(self, ci_values, dsa_values, hi_values) -> str:
        """Определить превалирующую / выбранную породу для отрисовки зелёных и красных границ."""
        selected = self.combo_excel_breed.currentData() if hasattr(self, "combo_excel_breed") else "auto"
        if selected and selected != "auto" and selected in BREEDS:
            return selected

        if not (ci_values and dsa_values and hi_values):
            return "Carnica"

        import numpy as np
        n_pts = min(len(ci_values), len(dsa_values), len(hi_values))
        counts = {b: 0 for b in BREEDS}
        for i in range(n_pts):
            found, _ = identify_breed(float(ci_values[i]), float(dsa_values[i]), float(hi_values[i]))
            for b in found:
                if b in counts:
                    counts[b] += 1

        mean_ci = float(np.mean(ci_values[:n_pts]))
        mean_dsa = float(np.mean(dsa_values[:n_pts]))
        mean_hi = float(np.mean(hi_values[:n_pts]))

        classic_best = max(CLASSIC_BREEDS, key=lambda b: (counts.get(b, 0), -calculate_breed_distance(mean_ci, mean_dsa, mean_hi, b)))
        if counts.get(classic_best, 0) > 0:
            return classic_best

        all_best = max(BREEDS.keys(), key=lambda b: (counts.get(b, 0), -calculate_breed_distance(mean_ci, mean_dsa, mean_hi, b)))
        return all_best

    @staticmethod
    def _smooth_catmull_rom(x_vals: List[float], y_vals: List[float], points_per_seg: int = 12):
        """Построить сглаженную огибающую кривую по точкам (x_vals, y_vals) с ограничением >= 0."""
        import numpy as np
        pts_x = np.asarray(x_vals, dtype=float)
        pts_y = np.asarray(y_vals, dtype=float)
        n = len(pts_x)
        if n < 2:
            return pts_x, pts_y

        out_x = []
        out_y = []
        for i in range(n - 1):
            p0_y = pts_y[max(0, i - 1)]
            p1_y = pts_y[i]
            p2_y = pts_y[i + 1]
            p3_y = pts_y[min(n - 1, i + 2)]
            x1, x2 = pts_x[i], pts_x[i + 1]
            ts = np.linspace(0.0, 1.0, points_per_seg, endpoint=(i == n - 2))
            for t in ts:
                t2 = t * t
                t3 = t2 * t
                # Кубический сплайн Catmull-Rom
                val_y = 0.5 * (
                    (2.0 * p1_y)
                    + (-p0_y + p2_y) * t
                    + (2.0 * p0_y - 5.0 * p1_y + 4.0 * p2_y - p3_y) * t2
                    + (-p0_y + 3.0 * p1_y - 3.0 * p2_y + p3_y) * t3
                )
                if p1_y == 0.0 and p2_y == 0.0:
                    val_y = 0.0
                out_x.append(x1 + (x2 - x1) * t)
                out_y.append(max(0.0, float(val_y)))
        return np.asarray(out_x), np.asarray(out_y)

    @staticmethod
    def _bound_to_pos(val: float, class_nums: List[int], upper_bounds: List[float]) -> float:
        """Перевести численное значение границы породы в координату на оси классов."""
        n = len(upper_bounds)
        if n == 0:
            return 0.0
        for i, b in enumerate(upper_bounds):
            if abs(val - b) < 1e-6:
                return float(class_nums[i])
            if val < b:
                if i == 0:
                    step = (upper_bounds[1] - upper_bounds[0]) if n > 1 else 1.0
                    return float(class_nums[0]) - (b - val) / max(1e-6, step)
                prev_b = upper_bounds[i - 1]
                frac = (val - prev_b) / max(1e-6, b - prev_b)
                return float(class_nums[i - 1]) + frac * (class_nums[i] - class_nums[i - 1])
        return float(class_nums[-1])

    def _render_excel_kartashov_chart(
        self,
        values: List[float],
        wing_numbers: Optional[List[int]],
        title: str,
        index_key: str,
        full_bounds: Tuple[float, ...],
        slice_start: int,
        slice_end: int,
        class_num_start: int,
        active_breed: str,
        label_widget: ScalableGraphLabel,
    ):
        """
        Отрисовать частотный график индекса (Графики 5, 6, 7 из «Порода по крыльям в. 2.5»):
        - Нижняя ось X: номера классов Руттнера/Крубера (1..26 для CI, 6..35 для DsA, 6..37 для HI)
        - Верхняя ось X: верхние численные границы каждого класса (вертикально 90°, через запятую)
        - Узкие бордово-коричневые столбики (#993300) + красная сглаженная огибающая кривая (#FF0000)
        - Зелёные вертикальные границы превалирующей породы (#00B050) и красные границы 1-го ранга (±3 класса, #FF0000)
        """
        import numpy as np
        from io import BytesIO

        if not values:
            label_widget.setText(f"{title}\n\nНет данных")
            return

        # 1. Распределение FREQUENCY(vals, full_bounds) по полной шкале Карташёва
        full_counts = [0] * len(full_bounds)
        for raw_val in values:
            val = float(raw_val)
            placed = False
            for i, b in enumerate(full_bounds):
                if val <= b + 1e-9:
                    full_counts[i] += 1
                    placed = True
                    break
            if not placed:
                full_counts[-1] += 1

        upper_bounds = list(full_bounds[slice_start:slice_end])
        counts = list(full_counts[slice_start:slice_end])
        n_bins = len(upper_bounds)
        class_nums = [class_num_start + i for i in range(n_bins)]

        fig, ax = plt.subplots(figsize=(13.2, 5.2), dpi=115)
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#ffffff')

        max_count = max(counts) if counts else 0
        y_top = max(6, int(math.ceil((max_count + 2) / 5.0) * 5)) if max_count >= 4 else max(6, max_count + 2)

        # Сетка по каждому классу по X и каждому 1 крылу (основная каждые 5) по Y
        ax.set_xlim(class_nums[0] - 0.6, class_nums[-1] + 0.6)
        ax.set_ylim(0, y_top)
        ax.set_xticks(class_nums)
        ax.set_xticklabels([str(c) for c in class_nums], fontsize=9.0, fontweight='bold', color='#000000')
        ax.yaxis.set_major_locator(MultipleLocator(5))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
        ax.grid(True, which='major', axis='both', color='#777777', linestyle='-', linewidth=0.75, alpha=0.7, zorder=0)
        ax.grid(True, which='minor', axis='y', color='#bbbbbb', linestyle='-', linewidth=0.45, alpha=0.6, zorder=0)

        # 2. Узкие бордово-коричневые столбики (#993300 с чёрной рамкой)
        ax.bar(
            class_nums, counts, width=0.38,
            color='#993300', edgecolor='#000000', linewidth=1.0,
            label='Частота (шт.)', zorder=3
        )

        # 3. Ярко-красная сглаженная огибающая кривая по вершинам столбиков
        sx, sy = self._smooth_catmull_rom(class_nums, counts, points_per_seg=14)
        ax.plot(sx, sy, color='#FF0000', linewidth=2.4, label='Огибающая кривая', zorder=5)

        # 4. Вертикальные зелёные линии границ породы и красные линии 1-го ранга гибридизации (±3 класса)
        if active_breed in BREEDS:
            vmin, vmax = BREEDS[active_breed][index_key]
            x_min_green = self._bound_to_pos(vmin, class_nums, upper_bounds)
            x_max_green = self._bound_to_pos(vmax, class_nums, upper_bounds)
            breed_ru = BREED_SHORT_NAMES_RU.get(active_breed, active_breed)

            ax.axvline(
                x_min_green, color='#00B050', linestyle='-', linewidth=2.5,
                label=f'Границы породы ({breed_ru})', zorder=6
            )
            ax.axvline(x_max_green, color='#00B050', linestyle='-', linewidth=2.5, zorder=6)

            # Критические области 1-го ранга (3 класса наружу от границ породы)
            red_positions = []
            if active_breed == "Mellifera":
                red_positions.append(x_max_green + 3.0)
            elif active_breed in ("Carnica", "Carpatica"):
                red_positions.append(x_min_green - 3.0)
            else:
                red_positions.append(x_min_green - 3.0)
                red_positions.append(x_max_green + 3.0)

            for r_idx, rx in enumerate(red_positions):
                if class_nums[0] - 0.5 <= rx <= class_nums[-1] + 0.5:
                    ax.axvline(
                        rx, color='#FF0000', linestyle='-', linewidth=2.2,
                        label='Граница 1-го ранга (±3 кл.)' if r_idx == 0 else None,
                        zorder=6
                    )

        # 5. Верхняя ось X: верхние численные границы каждого класса (вертикально 90°, с запятой)
        ax_top = ax.twiny()
        ax_top.set_xlim(ax.get_xlim())
        ax_top.set_xticks(class_nums)
        fmt_precision = 3 if index_key == "HI" else 2
        top_labels = [f"{b:.{fmt_precision}f}".replace(".", ",") for b in upper_bounds]
        ax_top.set_xticklabels(top_labels, rotation=90, fontsize=8.2, color='#111111')
        ax_top.tick_params(axis='x', pad=2, length=3)

        ax.set_xlabel("Классы", fontsize=10.5, fontweight='bold', color='#000000')
        ax.set_ylabel("Кол-во, шт.", fontsize=10.5, fontweight='bold', color='#000000')
        ax.set_title(title, fontsize=12.5, fontweight='bold', color='#000000', pad=36)
        ax.legend(fontsize=8.5, loc='upper right', frameon=True, facecolor='#ffffff', edgecolor='#888888')

        for spine in ax.spines.values():
            spine.set_edgecolor('#000000')
            spine.set_linewidth(1.0)

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format='png', facecolor='#ffffff', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        label_widget.setPixmap(pixmap)

    def _render_classic_or_kde_histogram(
        self,
        values: List[float],
        wing_numbers: Optional[List[int]],
        title: str,
        xlabel: str,
        breed_ranges: Dict[str, Tuple[float, float]],
        label_widget: ScalableGraphLabel,
        color: str,
        with_density_curve: bool = False,
    ):
        """Отрисовать классическую столбчатую гистограмму (Вариант 1) или гистограмму с плавной кривой плотности (Вариант 2)."""
        import numpy as np
        from io import BytesIO

        if not values:
            label_widget.setText(f"{title}\n\nНет данных")
            return

        fig, ax = plt.subplots(figsize=(12.5, 5.2), dpi=115)
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#f9f9f9')

        fig.suptitle(title, fontsize=15, color='#222222', fontweight='bold', y=0.98)

        n, bins, patches = ax.hist(values, bins=15, color=color, edgecolor='#333333', alpha=0.72)

        bin_wings = {i: [] for i in range(len(bins) - 1)}
        for wing_idx, val in enumerate(values):
            for i in range(len(bins) - 1):
                if bins[i] <= val < bins[i + 1] or (i == len(bins) - 2 and val == bins[i + 1]):
                    bin_wings[i].append(
                        wing_numbers[wing_idx] if wing_numbers and wing_idx < len(wing_numbers) else wing_idx + 1
                    )
                    break

        for i, (count, patch) in enumerate(zip(n, patches)):
            if count > 0 and bin_wings[i]:
                wings_str = ','.join(map(str, bin_wings[i][:5]))
                if len(bin_wings[i]) > 5:
                    wings_str += f'...+{len(bin_wings[i]) - 5}'
                ax.annotate(
                    f'№{wings_str}',
                    xy=(patch.get_x() + patch.get_width() / 2, count),
                    ha='center', va='bottom', fontsize=10, color='#cc6600',
                    rotation=35, fontweight='bold'
                )

        mean = float(np.mean(values))
        std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

        if with_density_curve and len(values) >= 2 and std > 1e-9:
            data_min, data_max = min(values), max(values)
            span = max(1e-6, data_max - data_min)
            xs = np.linspace(data_min - 0.2 * span, data_max + 0.2 * span, 200)
            bin_w = (bins[-1] - bins[0]) / max(1, len(bins) - 1)
            bw = max(std * (len(values) ** (-0.2)), span * 0.08, 1e-4)
            vals_arr = np.asarray(values, dtype=float)[:, None]
            kernels = np.exp(-0.5 * ((xs[None, :] - vals_arr) / bw) ** 2) / (bw * math.sqrt(2.0 * math.pi))
            ys = kernels.mean(axis=0) * len(values) * bin_w
            ax.plot(xs, ys, color='#1864ab', linewidth=2.6, label='Плавная кривая плотности (KDE)', zorder=5)
            ax.fill_between(xs, ys, 0, color='#1864ab', alpha=0.10, zorder=2)

        ax.axvline(
            mean, color='#ff8800', linestyle='--', linewidth=2,
            label=f'Среднее = {mean:.3f}'
        )

        for breed, (vmin, vmax) in breed_ranges.items():
            label_ru = f"{BREED_SHORT_NAMES_RU.get(breed, breed)} ({breed})"
            ax.axvspan(
                vmin, vmax, alpha=0.14,
                color=BREED_COLORS_HEX.get(breed, 'gray'),
                label=label_ru
            )

        data_min, data_max = min(values), max(values)
        data_range = data_max - data_min
        margin = data_range * 0.12 if data_range > 0 else 0.5
        ax.set_xlim(data_min - margin, data_max + margin)

        ax.set_xlabel(xlabel, fontsize=12, color='#222222')
        ax.set_ylabel('Количество крыльев', fontsize=12, color='#222222')
        ax.tick_params(colors='#222222', labelsize=10)
        ax.legend(fontsize=9, loc='upper right', facecolor='#ffffff', edgecolor='#cccccc')
        ax.grid(True, alpha=0.3, linestyle='--', color='#999999')

        for spine in ax.spines.values():
            spine.set_edgecolor('#cccccc')

        plt.tight_layout(rect=[0, 0, 1, 0.94])

        buf = BytesIO()
        fig.savefig(buf, format='png', facecolor='#ffffff', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        label_widget.setPixmap(pixmap)

    def _render_index_charts(self, ci_values, dsa_values, hi_values, wing_numbers=None):
        """Отрисовать 3 графика индексов (CI, DsA, HI) в выбранном стиле (0, 1 или 2)."""
        style_idx = self.combo_chart_style.currentIndex() if hasattr(self, "combo_chart_style") else 2

        if style_idx == 2:
            active_breed = self._resolve_active_breed(ci_values, dsa_values, hi_values)
            # График 5: CI — 26 классов (1..26), границы KARTASHOV_CI_BOUNDS[1:27] (0.76 .. 5.67)
            self._render_excel_kartashov_chart(
                ci_values, wing_numbers,
                "5. Распределение частоты CI по классам", "CI",
                KARTASHOV_CI_BOUNDS, 1, 27, 1,
                active_breed, self.graph_ci,
            )
            # График 6: DsA — 30 классов (6..35), границы KARTASHOV_DSA_BOUNDS[1:31] (-15.31 .. +12.39)
            self._render_excel_kartashov_chart(
                dsa_values, wing_numbers,
                "6. Распределение частоты DsA по классам", "DsA",
                KARTASHOV_DSA_BOUNDS, 1, 31, 6,
                active_breed, self.graph_dsa,
            )
            # График 7: HI — 32 класса (6..37), границы KARTASHOV_HI_BOUNDS[1:33] (0.616 .. 1.420)
            self._render_excel_kartashov_chart(
                hi_values, wing_numbers,
                "7. Распределение частоты HI по классам", "HI",
                KARTASHOV_HI_BOUNDS, 1, 33, 6,
                active_breed, self.graph_hi,
            )
        else:
            with_kde = (style_idx == 1)
            ci_ranges = {b: r['CI'] for b, r in BREEDS.items()}
            self._render_classic_or_kde_histogram(
                ci_values, wing_numbers,
                'КУБИТАЛЬНЫЙ ИНДЕКС (CI)', 'Кубитальный индекс (CI)',
                ci_ranges, self.graph_ci, '#5dade2', with_density_curve=with_kde
            )

            dsa_ranges = {b: r['DsA'] for b, r in BREEDS.items()}
            self._render_classic_or_kde_histogram(
                dsa_values, wing_numbers,
                'ДИСКОИДАЛЬНОЕ СМЕЩЕНИЕ (DsA)', 'Градусы (°)',
                dsa_ranges, self.graph_dsa, '#58d68d', with_density_curve=with_kde
            )

            hi_ranges = {b: r['HI'] for b, r in BREEDS.items()}
            self._render_classic_or_kde_histogram(
                hi_values, wing_numbers,
                'ГАНТЕЛЬНЫЙ ИНДЕКС (HI)', 'Гантельный индекс (HI)',
                hi_ranges, self.graph_hi, '#f5b041', with_density_curve=with_kde
            )

    def update_graphs(self, ci_values, dsa_values, hi_values, wing_numbers=None, **kwargs):
        """Обновить 2D-карту породности и графики индексов с данными о крыльях"""
        self._pending_data = (
            list(ci_values or []),
            list(dsa_values or []),
            list(hi_values or []),
            list(wing_numbers) if wing_numbers else None,
        )
        self._graphs_dirty = False

        if not MATPLOTLIB_AVAILABLE:
            self.graph_ci.setText("matplotlib не установлен")
            return

        try:
            plt.style.use('default')

            self.wing_data = []
            if wing_numbers:
                for i, (ci, dsa, hi) in enumerate(zip(ci_values, dsa_values, hi_values)):
                    self.wing_data.append((wing_numbers[i] if i < len(wing_numbers) else i + 1, ci, dsa, hi))

            # 1. Отрисовываем 2D-карту породности / Матрицу 2×2 Карташёва
            self._render_2d_map(ci_values, dsa_values, hi_values, wing_numbers)

            # 2. Отрисовываем 3 графика индексов в выбранном стиле (0, 1 или 2)
            self._render_index_charts(ci_values, dsa_values, hi_values, wing_numbers)

        except Exception as e:
            for graph in (self.graph_map_2d, self.graph_ci, self.graph_dsa, self.graph_hi):
                graph.setText(f"Ошибка построения графиков: {e}")
