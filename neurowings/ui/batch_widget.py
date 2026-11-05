#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет сводной таблицы по пасеке (v2.2.0)
"""

from pathlib import Path
from typing import Dict
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QHeaderView, QFileDialog, QMessageBox
)
from PyQt5.QtGui import QColor

from ..core.constants import format_breed_ru
from ..core.data_models import ImageData
from ..core.colony_analysis import ColonyAnalysisService


class BatchResultsWidget(QWidget):
    """Виджет сводной таблицы по всем файлам"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.batch_results = {}
        self._refresh_callback = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("📋 Сводная таблица по пасеке")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0;")
        header.addWidget(title)
        header.addStretch()

        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_refresh.clicked.connect(self._request_refresh)
        header.addWidget(self.btn_refresh)

        self.btn_export_all = QPushButton("💾 Экспорт в Excel")
        self.btn_export_all.clicked.connect(self._export_batch_to_excel)
        header.addWidget(self.btn_export_all)

        layout.addLayout(header)

        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(10)
        self.batch_table.setHorizontalHeaderLabels([
            "Файл", "Крыльев", "Идент.", "% соответствия",
            "Кубитальный индекс", "% Алпатова", "Дискоид. смещение", "Гантельный индекс",
            "Породность", "Баллы (из 17)"
        ])
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.batch_table.setAlternatingRowColors(True)
        layout.addWidget(self.batch_table)

        self.info_label = QLabel("Откройте папку со сканами или перетащите файлы крыльев в окно")
        self.info_label.setStyleSheet("color: #444444; font-style: italic;")
        layout.addWidget(self.info_label)

    def set_refresh_callback(self, callback):
        """Установить callback для обновления"""
        self._refresh_callback = callback

    def _request_refresh(self):
        """Запросить обновление"""
        if self._refresh_callback:
            self._refresh_callback()

    def update_batch_results(self, images: Dict[str, ImageData]):
        """Обновить результаты по всем изображениям через единый ColonyAnalysisService"""
        self.batch_results = {}

        with_wings = [(path, img) for path, img in images.items() if img.wings]

        if not with_wings:
            self.batch_table.setRowCount(0)
            self.info_label.setText("Нет данных")
            return

        self.info_label.setText(f"Проб (семей): {len(with_wings)}")
        self.batch_table.setRowCount(len(with_wings))

        for row, (path, img_data) in enumerate(with_wings):
            res = ColonyAnalysisService.analyze_image(img_data, reanalyze_wings=True)
            analysis_results = img_data.analysis_results

            total = analysis_results.get('total', res.total)
            identified = analysis_results.get('identified', res.identified)
            breed_match_pct = analysis_results.get('breed_match_pct', res.breed_match_pct)
            mean_ci = analysis_results.get('mean_ci', res.ci.mean)
            alpatov_pct = analysis_results.get('alpatov_pct', res.alpatov_pct)
            mean_dsa = analysis_results.get('mean_dsa', res.dsa.mean)
            mean_hi = analysis_results.get('mean_hi', res.hi.mean)
            breed_key = analysis_results.get('breed', res.dominant_breed_str)
            breed_display = format_breed_ru(breed_key) if breed_key != "—" else "Помесь / вне стандарта"
            score = analysis_results.get('score', res.total_score)

            self.batch_table.setItem(row, 0, QTableWidgetItem(Path(path).name))
            self.batch_table.setItem(row, 1, QTableWidgetItem(str(total)))
            self.batch_table.setItem(row, 2, QTableWidgetItem(str(identified)))
            self.batch_table.setItem(row, 3, QTableWidgetItem(f"{breed_match_pct:.1f}%"))
            self.batch_table.setItem(row, 4, QTableWidgetItem(f"{mean_ci:.3f}"))
            self.batch_table.setItem(row, 5, QTableWidgetItem(f"{alpatov_pct:.1f}%"))
            self.batch_table.setItem(row, 6, QTableWidgetItem(f"{mean_dsa:.2f}"))
            self.batch_table.setItem(row, 7, QTableWidgetItem(f"{mean_hi:.3f}"))
            self.batch_table.setItem(row, 8, QTableWidgetItem(breed_display))
            self.batch_table.setItem(row, 9, QTableWidgetItem(str(score)))

            if score >= 10:
                bg_color = QColor("#e8f5e9")
            elif score >= 5:
                bg_color = QColor("#fff8e1")
            else:
                bg_color = QColor("#ffebee")
            text_color = QColor("#1a1a1a")

            for col in range(10):
                item = self.batch_table.item(row, col)
                if item:
                    item.setBackground(bg_color)
                    item.setForeground(text_color)

            self.batch_results[path] = {
                'filename': Path(path).name,
                'total': total,
                'identified': identified,
                'breed_match_pct': breed_match_pct,
                'mean_ci': mean_ci,
                'alpatov_pct': alpatov_pct,
                'mean_dsa': mean_dsa,
                'mean_hi': mean_hi,
                'breed': breed_display,
                'breed_key': breed_key,
                'score': score,
            }

    def _calc_score(self, total, identified, mean_ci, mean_dsa, mean_hi, cv_ci, cv_hi):
        """
        Рассчитать балл по унифицированной 17-балльной шкале (для обратной совместимости).
        """
        if total <= 0 or identified <= 0:
            return -int(np.ceil(100.0 / 5.0)) if total > 0 else 0

        score = 0

        # 1. Штраф за неидентифицированные крылья
        not_id_pct = 100.0 * (total - identified) / total
        score -= int(np.ceil(not_id_pct / 5.0))

        # 2. Вероятностная оценка (0..5 баллов)
        id_pct = 100.0 * identified / total
        diff = (id_pct - 100.0) / 10.0
        roundup_val = int(np.ceil(diff)) if diff >= 0 else int(np.floor(diff))
        score += max(0, 5 + roundup_val)

        # 3. Целостность по кубитальному индексу (0..2 балла, как в AnalysisWidget)
        if cv_ci < 12.5:
            score += 2
        elif cv_ci < 20.0:
            score += 1

        # 4. Целостность по гантельному индексу (0..2 балла, как в AnalysisWidget)
        if cv_hi < 6.5:
            score += 2
        elif cv_hi < 7.5:
            score += 1

        # 5. Гибридизация по индексам (до 9 баллов суммарно)
        if mean_ci < 1.7 or mean_ci >= 2.3:
            score += 3
        elif mean_ci < 1.9 or mean_ci >= 2.16:
            score += 2
        else:
            score += 1

        if mean_dsa <= -3 or mean_dsa >= 1.5:
            score += 3
        elif mean_dsa <= -1 or mean_dsa >= 0.5:
            score += 2
        else:
            score += 1

        if mean_hi < 0.85 or mean_hi >= 0.95:
            score += 3
        elif mean_hi < 0.90 or mean_hi >= 0.923:
            score += 2
        else:
            score += 1

        return score

    def _export_batch_to_excel(self):
        """Экспорт сводной таблицы в Excel"""
        if not self.batch_results:
            QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить сводную таблицу",
            "сводная_таблица.xlsx",
            "Excel Files (*.xlsx)"
        )

        if not path:
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Сводная таблица"

            headers = [
                "Файл", "Крыльев", "Идент.", "% соответствия",
                "Кубитальный индекс", "% Алпатова", "Дискоид. смещение", "Гантельный индекс",
                "Породность", "Баллы"
            ]
            for col, h in enumerate(headers, 1):
                cell = ws.cell(1, col, h)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="1a5276", end_color="1a5276", fill_type="solid")

            for row, (_, data) in enumerate(self.batch_results.items(), 2):
                ws.cell(row, 1, data['filename'])
                ws.cell(row, 2, data['total'])
                ws.cell(row, 3, data['identified'])
                ws.cell(row, 4, f"{data['breed_match_pct']:.1f}%")
                ws.cell(row, 5, round(data['mean_ci'], 3))
                ws.cell(row, 6, f"{data['alpatov_pct']:.1f}%")
                ws.cell(row, 7, f"{round(data['mean_dsa'], 2)}")
                ws.cell(row, 8, round(data['mean_hi'], 3))
                ws.cell(row, 9, data['breed'])
                ws.cell(row, 10, data['score'])

            for col in ws.columns:
                max_length = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = max_length + 2

            wb.save(path)
            QMessageBox.information(self, "Успех", f"Сохранено:\n{path}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {str(e)}")
