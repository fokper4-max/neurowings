#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет графиков (2D-карта породности + гистограммы распределения CI, DsA, HI).
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ..core.constants import (
    BREEDS, BREED_COLORS_HEX, BREED_SHORT_NAMES_RU
)
from ..core.calculations import identify_breed

# Проверка matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Ellipse
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


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
    """Виджет с 2D-картой породности семьи и гистограммами CI, DsA, HI"""

    wing_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.wing_data = []
        self._pending_data = None
        self._graphs_dirty = False

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
        lbl_map = QLabel("🗺 <b>Режим 2D-карты породности:</b>")
        lbl_map.setStyleSheet("color: #222222;")
        top_bar.addWidget(lbl_map)
        self.combo_2d_mode = QComboBox()
        self.combo_2d_mode.addItems([
            "Двойная карта: DsA ↔ CI и HI ↔ CI (95% эллипс)",
            "Крупно: Дискоидальное смещение (DsA) ↔ Кубитальный индекс (CI)",
            "Крупно: Гантельный индекс (HI) ↔ Кубитальный индекс (CI)",
        ])
        self.combo_2d_mode.currentIndexChanged.connect(self._on_2d_mode_changed)
        top_bar.addWidget(self.combo_2d_mode)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.graph_map_2d = ScalableGraphLabel(
            "2D-КАРТА ПОРОДНОСТИ СЕМЬИ (DsA ↔ CI и HI ↔ CI)\n\nДанные не загружены",
            min_height=460,
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

    def clear_graphs(self, message: str = "Нет данных"):
        self._pending_data = None
        self._graphs_dirty = False
        for graph in (self.graph_map_2d, self.graph_ci, self.graph_dsa, self.graph_hi):
            graph.setText(message)

    def schedule_update(self, ci_values, dsa_values, hi_values, wing_numbers=None, force: bool = False):
        """Отложенное (ленивое) обновление графиков: рендерит сразу только если вкладка открыта или force=True."""
        self._pending_data = (list(ci_values or []), list(dsa_values or []), list(hi_values or []), list(wing_numbers) if wing_numbers else None)
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

    def _render_2d_map(self, ci_values, dsa_values, hi_values, wing_numbers):
        import numpy as np
        from io import BytesIO

        if not (ci_values and dsa_values and hi_values):
            self.graph_map_2d.setText("2D-КАРТА ПОРОДНОСТИ СЕМЬИ\n\nНет данных")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.6), dpi=115)
        fig.patch.set_facecolor('#ffffff')
        fig.suptitle(
            "2D-КАРТА ПОРОДНОСТИ СЕМЬИ (ЭТАЛОННЫЕ ЗОНЫ И ДОВЕРИТЕЛЬНЫЙ ЭЛЛИПС)",
            fontsize=15, color='#222222', fontweight='bold', y=0.98
        )

        for ax in (ax1, ax2):
            ax.set_facecolor('#f9f9f9')
            for spine in ax.spines.values():
                spine.set_edgecolor('#cccccc')

        for breed, ranges in BREEDS.items():
            color = BREED_COLORS_HEX.get(breed, '#888888')
            label_ru = f"{BREED_SHORT_NAMES_RU.get(breed, breed)} ({breed})"
            dsa_lo, dsa_hi = ranges['DsA']
            ci_lo, ci_hi = ranges['CI']
            hi_lo, hi_hi = ranges['HI']

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

            ax1.scatter(dsa_v, ci_v, c=pt_color, s=42, edgecolors='white', linewidth=0.8, zorder=5)
            ax1.annotate(
                f"№{w_num}", (dsa_v, ci_v),
                textcoords="offset points", xytext=(4, 3),
                fontsize=8, color='#222222', fontweight='bold', zorder=6
            )

            ax2.scatter(hi_v, ci_v, c=pt_color, s=42, edgecolors='white', linewidth=0.8, zorder=5)
            ax2.annotate(
                f"№{w_num}", (hi_v, ci_v),
                textcoords="offset points", xytext=(4, 3),
                fontsize=8, color='#222222', fontweight='bold', zorder=6
            )

        mean_ci = float(np.mean(ci_values[:n_pts]))
        mean_dsa = float(np.mean(dsa_values[:n_pts]))
        mean_hi = float(np.mean(hi_values[:n_pts]))

        self._add_confidence_ellipse(ax1, dsa_values[:n_pts], ci_values[:n_pts], color="#d9480f")
        ax1.scatter(
            [mean_dsa], [mean_ci], c='#d9480f', marker='X', s=110,
            edgecolors='black', linewidth=1.0,
            label=f'Центроид семьи ({mean_dsa:+.2f}°, {mean_ci:.2f})', zorder=7
        )

        self._add_confidence_ellipse(ax2, hi_values[:n_pts], ci_values[:n_pts], color="#d9480f")
        ax2.scatter(
            [mean_hi], [mean_ci], c='#d9480f', marker='X', s=110,
            edgecolors='black', linewidth=1.0,
            label=f'Центроид семьи ({mean_hi:.3f}, {mean_ci:.2f})', zorder=7
        )

        ax1.axvline(0.0, color='#666666', linestyle=':', linewidth=1.2)
        ax1.set_title("Дискоидальное смещение (DsA) ↔ Кубитальный индекс (CI)", fontsize=11.5, fontweight='bold')
        ax1.set_xlabel("Дискоидальное смещение DsA (°)", fontsize=10.5)
        ax1.set_ylabel("Кубитальный индекс CI", fontsize=10.5)
        ax1.set_xlim(min(-16.0, min(dsa_values[:n_pts]) - 1.5), max(13.5, max(dsa_values[:n_pts]) + 1.5))
        ax1.set_ylim(min(0.7, min(ci_values[:n_pts]) - 0.2), max(5.8, max(ci_values[:n_pts]) + 0.3))
        ax1.grid(True, alpha=0.3, linestyle='--')
        ax1.legend(fontsize=8.0, loc='upper left', ncol=2, facecolor='#ffffff', framealpha=0.9)

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

    def update_graphs(self, ci_values, dsa_values, hi_values, wing_numbers=None, **kwargs):
        """Обновить 2D-карту породности и гистограммы с данными о крыльях"""
        self._pending_data = (list(ci_values or []), list(dsa_values or []), list(hi_values or []), list(wing_numbers) if wing_numbers else None)
        self._graphs_dirty = False

        if not MATPLOTLIB_AVAILABLE:
            self.graph_ci.setText("matplotlib не установлен")
            return

        try:
            import numpy as np
            from io import BytesIO

            plt.style.use('default')

            self.wing_data = []
            if wing_numbers:
                for i, (ci, dsa, hi) in enumerate(zip(ci_values, dsa_values, hi_values)):
                    self.wing_data.append((wing_numbers[i] if i < len(wing_numbers) else i + 1, ci, dsa, hi))

            # 1. Отрисовываем 2D-карту породности
            self._render_2d_map(ci_values, dsa_values, hi_values, wing_numbers)

            # 2. Отрисовываем 3 гистограммы
            def create_histogram(values, title, xlabel, breed_ranges, label_widget, color):
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

            ci_ranges = {b: r['CI'] for b, r in BREEDS.items()}
            create_histogram(ci_values, 'КУБИТАЛЬНЫЙ ИНДЕКС (CI)', 'Кубитальный индекс (CI)', ci_ranges, self.graph_ci, '#5dade2')

            dsa_ranges = {b: r['DsA'] for b, r in BREEDS.items()}
            create_histogram(dsa_values, 'ДИСКОИДАЛЬНОЕ СМЕЩЕНИЕ (DsA)', 'Градусы (°)', dsa_ranges, self.graph_dsa, '#58d68d')

            hi_ranges = {b: r['HI'] for b, r in BREEDS.items()}
            create_histogram(hi_values, 'ГАНТЕЛЬНЫЙ ИНДЕКС (HI)', 'Гантельный индекс (HI)', hi_ranges, self.graph_hi, '#f5b041')

        except Exception as e:
            for graph in (self.graph_map_2d, self.graph_ci, self.graph_dsa, self.graph_hi):
                graph.setText(f"Ошибка построения графиков: {e}")
