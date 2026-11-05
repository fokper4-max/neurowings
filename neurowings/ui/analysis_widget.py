#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет анализа результатов исследований (v2.2.0)
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QHeaderView, QScrollArea, QFileDialog, QMessageBox,
    QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from ..core.constants import BREEDS, BREED_NAMES_RU, format_breed_ru
from ..core.calculations import ci_to_alpatov
from ..core.data_models import ImageData
from ..core.colony_analysis import ColonyAnalysisService, analyze_colony
from ..core.pdf_passport import generate_pdf_passport


class AnalysisWidget(QWidget):
    """Виджет анализа результатов исследований"""

    goto_wing_signal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.current_data = None
        self.aggregate_mode = False
        self.graphs_widget = None
        self.save_tps_callback = None
        self.target_breed = "auto"
        self.last_result = None

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget()
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        header = QHBoxLayout()
        title = QLabel("📊 Анализ результатов исследований")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0;")
        header.addWidget(title)
        header.addStretch()

        self.btn_pdf = QPushButton("📄 PDF-Паспорт")
        self.btn_pdf.setToolTip("Сохранить одностраничный сертификат (паспорт) пчелосемьи в PDF")
        self.btn_pdf.clicked.connect(self._export_to_pdf)
        header.addWidget(self.btn_pdf)

        self.btn_export = QPushButton("📊 Экспорт в Excel")
        self.btn_export.clicked.connect(self._export_to_excel)
        header.addWidget(self.btn_export)

        main_layout.addLayout(header)

        self.analysis_table = QTableWidget()
        self.analysis_table.setColumnCount(4)
        self.analysis_table.setHorizontalHeaderLabels(["№", "Показатель", "Значение", "Баллы"])
        self.analysis_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.analysis_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.analysis_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.analysis_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.analysis_table.setColumnWidth(0, 40)
        self.analysis_table.setColumnWidth(3, 85)
        self.analysis_table.setAlternatingRowColors(True)
        self.analysis_table.setStyleSheet("""
            QTableWidget { background-color: #ffffff; gridline-color: #dddddd; font-size: 12px; color: #1a1a1a; }
            QTableWidget::item { padding: 5px; }
            QHeaderView::section { background-color: #e0e0e0; color: #222222; font-weight: bold; padding: 5px; }
        """)
        self.analysis_table.setMinimumHeight(420)
        main_layout.addWidget(self.analysis_table)

        wings_label = QLabel("📋 Результаты по крыльям (клик по строке приблизит крыло на скане)")
        wings_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px; color: #222222;")
        main_layout.addWidget(wings_label)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels([
            "№", "Кубит. индекс", "% Алпатова", "Дискоид. смещ.",
            "Гантел. индекс", "Порода", "Статус"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.cellClicked.connect(self._on_table_clicked)
        self.results_table.setMinimumHeight(350)
        main_layout.addWidget(self.results_table)

        main_layout.addStretch()
        scroll.setWidget(scroll_content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

    def set_graphs_widget(self, widget):
        """Установить связанный виджет графиков"""
        self.graphs_widget = widget

    def _on_table_clicked(self, row, col):
        """Переход к крылу по клику"""
        if getattr(self, "aggregate_mode", False):
            return
        self.goto_wing_signal.emit(row)

    def _add_row(self, num, param, value, score=""):
        row = self.analysis_table.rowCount()
        self.analysis_table.insertRow(row)

        item_num = QTableWidgetItem(str(num) if num else "")
        item_num.setTextAlignment(Qt.AlignCenter)
        item_num.setForeground(QColor("#1a1a1a"))
        self.analysis_table.setItem(row, 0, item_num)

        item_param = QTableWidgetItem(param)
        item_param.setForeground(QColor("#1a1a1a"))
        font_b = QFont("Arial", 11, QFont.Bold) if num else QFont("Arial", 11)
        item_param.setFont(font_b)
        self.analysis_table.setItem(row, 1, item_param)

        item_value = QTableWidgetItem(str(value))
        item_value.setTextAlignment(Qt.AlignCenter)
        item_value.setForeground(QColor("#1a1a1a"))
        self.analysis_table.setItem(row, 2, item_value)

        item_score = QTableWidgetItem(str(score) if score != "" else "")
        item_score.setTextAlignment(Qt.AlignCenter)
        if score != "" and isinstance(score, (int, float)):
            if score > 0:
                item_score.setForeground(QColor("#2b8a3e"))
            elif score < 0:
                item_score.setForeground(QColor("#c92a2a"))
            else:
                item_score.setForeground(QColor("#444444"))
        else:
            item_score.setForeground(QColor("#444444"))
        self.analysis_table.setItem(row, 3, item_score)
        return row

    def _add_subrow(self, param, value, score=""):
        row = self.analysis_table.rowCount()
        self.analysis_table.insertRow(row)

        self.analysis_table.setItem(row, 0, QTableWidgetItem(""))

        item_param = QTableWidgetItem(f"  • {param}")
        item_param.setForeground(QColor("#444444"))
        self.analysis_table.setItem(row, 1, item_param)

        item_value = QTableWidgetItem(str(value))
        item_value.setTextAlignment(Qt.AlignCenter)
        item_value.setForeground(QColor("#1a1a1a"))
        self.analysis_table.setItem(row, 2, item_value)

        item_score = QTableWidgetItem(str(score) if score != "" else "")
        item_score.setTextAlignment(Qt.AlignCenter)
        if score != "" and isinstance(score, (int, float)):
            if score > 0:
                item_score.setForeground(QColor("#2b8a3e"))
            elif score < 0:
                item_score.setForeground(QColor("#c92a2a"))
            else:
                item_score.setForeground(QColor("#444444"))
        else:
            item_score.setForeground(QColor("#444444"))
        self.analysis_table.setItem(row, 3, item_score)
        return row

    @staticmethod
    def calculate_analysis_results(image_data: ImageData, target_breed: str = None):
        """Рассчитать результаты анализа без обновления UI (через единый ColonyAnalysisService)."""
        if not image_data or not getattr(image_data, "wings", None):
            return None
        return ColonyAnalysisService.analyze_image(image_data, target_breed=target_breed, reanalyze_wings=True)

    def update_statistics(self, image_data, target_breed: str = None):
        """Обновить статистику для изображения или списка крыльев."""
        if target_breed is not None:
            self.target_breed = target_breed
        self.current_data = image_data
        self.aggregate_mode = isinstance(image_data, list)
        if self.aggregate_mode:
            image_data_obj = SimpleNamespace(
                wings=image_data, analysis_results={}, analyze_all_wings=lambda: None
            )
        else:
            image_data_obj = image_data

        self.analysis_table.setRowCount(0)
        self.results_table.setRowCount(0)

        if (
            not image_data_obj
            or not getattr(image_data_obj, "wings", None)
            or len(image_data_obj.wings) == 0
        ):
            self.last_result = None
            if self.graphs_widget:
                self.graphs_widget.clear_graphs("Нет данных")
            return

        if not self.aggregate_mode and hasattr(image_data_obj, "analyze_all_wings"):
            image_data_obj.analyze_all_wings()

        res = analyze_colony(
            image_data_obj.wings,
            target_breed=self.target_breed,
            reanalyze_wings=False,
        )
        self.last_result = res
        if hasattr(image_data_obj, "analysis_results") and isinstance(image_data_obj.analysis_results, dict):
            image_data_obj.analysis_results.update(res.to_summary_dict())

        # Заполняем таблицу анализа
        wings_info = str(res.total)
        if res.disabled_wings_count > 0:
            wings_info = f"{res.total} (отключено: {res.disabled_wings_count})"
        self._add_row(1, "Количество крыльев в расчёте", wings_info)

        self._add_row(
            2,
            "Неидентифицированные крылья (вне стандартов)",
            f"{res.not_identified} ({res.not_id_pct:.1f}%)",
            res.penalty_not_id,
        )

        self._add_row(3, "Морфометрические показатели (среднее ± ошибка):", "")
        self._add_subrow(
            "кубитальный индекс (CI)",
            f"{res.ci.mean:.3f} ± {res.ci.sem:.3f}",
            f"{res.alpatov_pct:.1f}% Алпатов",
        )
        rutt = res.ruttner
        rutt_badge = f"−:{rutt.get('minus', 0)} / 0:{rutt.get('zero', 0)} / +:{rutt.get('plus', 0)}"
        self._add_subrow(
            "дискоидальное смещение (DsA)",
            f"{res.dsa.mean:+.3f}° ± {res.dsa.sem:.3f}°",
            rutt_badge,
        )
        self._add_subrow(
            "гантельный индекс (HI)",
            f"{res.hi.mean:.3f} ± {res.hi.sem:.3f}",
        )

        self._add_row(4, "Распределение крыльев по породам:", "")
        for breed_name in BREEDS:
            self._add_subrow(
                format_breed_ru(breed_name),
                res.breed_counts.get(breed_name, 0),
            )

        self._add_row(
            5,
            "Преобладающая порода",
            res.dominant_breed_ru if res.dominant_breed else "Помесь / Бакфаст (вне стандарта)",
        )

        id_pct_display = round(res.breed_match_pct, 1)
        self._add_row(
            6,
            "Вероятностная оценка соответствия породе",
            f"{id_pct_display:.1f}%",
            res.breed_score,
        )

        self._add_row(7, "Однородность (целостность) семьи по:", "")
        self._add_subrow(
            "кубитальному индексу",
            f"{res.ci_integrity} (разброс {res.ci.cv:.1f}%)",
            res.ci_score,
        )
        self._add_subrow(
            "дискоидальному смещению",
            f"{res.dsa_integrity} (разброс {res.dsa.cv:.1f}%)",
        )
        self._add_subrow(
            "гантельному индексу",
            f"{res.hi_integrity} (разброс {res.hi.cv:.1f}%)",
            res.hi_score,
        )

        self._add_row(8, "Степень чистопородности (отсутствие гибридизации) по:", "")
        self._add_subrow("кубитальному индексу", res.ci_hybrid, res.ci_hyb_score)
        self._add_subrow("дискоидальному смещению", res.dsa_hybrid, res.dsa_hyb_score)
        self._add_subrow("гантельному индексу", res.hi_hybrid, res.hi_hyb_score)

        row = self._add_row(9, "ИТОГО БАЛЛОВ", f"{res.total_score} из {res.max_possible_score}", res.total_score)
        item = self.analysis_table.item(row, 2)
        if item:
            item.setFont(QFont("Arial", 13, QFont.Bold))
            item.setForeground(QColor("#2c5aa0"))

        self._add_row(10, "Заключение о пригодности семьи:", res.verdict_title)
        self._add_subrow("родоначальница линии (≥17 баллов)", "✅ пригодна" if res.total_score >= 17 else "❌ не пригодна")
        self._add_subrow("вывод племенных маток (≥15 баллов)", "✅ пригодна" if res.total_score >= 15 else "❌ не пригодна")
        self._add_subrow("для селекции (≥10 баллов)", "✅ пригодна" if res.total_score >= 10 else "❌ не пригодна")
        self._add_subrow("пользовательная на мёд (≥5 баллов)", "✅ пригодна" if res.total_score >= 5 else "❌ не пригодна")

        # Обновляем графики (лениво, если вкладка графиков сейчас не открыта)
        if self.graphs_widget:
            self.graphs_widget.schedule_update(
                res.ci.values, res.dsa.values, res.hi.values, res.wing_numbers_valid
            )

        # Таблица результатов по крыльям
        wings = image_data_obj.wings
        if self.aggregate_mode:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QTableWidgetItem("—"))
            self.results_table.setItem(0, 1, QTableWidgetItem(f"{res.ci.mean:.3f}"))
            self.results_table.setItem(0, 2, QTableWidgetItem(f"{res.alpatov_pct:.1f}%"))
            self.results_table.setItem(0, 3, QTableWidgetItem(f"{res.dsa.mean:.3f}"))
            self.results_table.setItem(0, 4, QTableWidgetItem(f"{res.hi.mean:.3f}"))
            breeds_present = [format_breed_ru(b, short=True) for b, c in res.breed_counts.items() if c > 0]
            self.results_table.setItem(0, 5, QTableWidgetItem(", ".join(breeds_present) or "—"))
            status_item = QTableWidgetItem("—")
            status_item.setBackground(QColor("#e9ecef"))
            status_item.setForeground(QColor("#1a1a1a"))
            self.results_table.setItem(0, 6, status_item)
        else:
            self.results_table.setRowCount(len(wings))
            for i, wing in enumerate(wings):
                enabled = getattr(wing, "is_enabled", True)
                a = wing.analysis
                self.results_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                if not a:
                    for col in range(1, 6):
                        self.results_table.setItem(i, col, QTableWidgetItem("—"))
                    status_item = QTableWidgetItem("❌")
                    status_item.setBackground(QColor("#ffebee"))
                    status_item.setForeground(QColor("#1a1a1a"))
                    self.results_table.setItem(i, 6, status_item)
                    continue

                alpatov = ci_to_alpatov(a.CI) * 100.0 if a.CI > 0 else 0.0
                self.results_table.setItem(i, 1, QTableWidgetItem(f"{a.CI:.3f}"))
                self.results_table.setItem(i, 2, QTableWidgetItem(f"{alpatov:.1f}%"))
                self.results_table.setItem(i, 3, QTableWidgetItem(f"{a.DsA:.3f}"))
                self.results_table.setItem(i, 4, QTableWidgetItem(f"{a.HI:.3f}"))
                breeds_text = format_breed_ru(a.breeds, short=True) if a.breeds else "—"
                self.results_table.setItem(i, 5, QTableWidgetItem(breeds_text))

                if not enabled:
                    status = "⏸ Откл."
                    bg = QColor("#f1f3f5")
                elif a.is_identified:
                    status = "✅"
                    bg = QColor("#e8f5e9")
                else:
                    status = "❌"
                    bg = QColor("#ffebee")

                status_item = QTableWidgetItem(status)
                if a.invalid_reason:
                    status_item.setToolTip(a.invalid_reason)
                elif getattr(a, "orientation_warning", ""):
                    status_item.setToolTip(a.orientation_warning)

                self.results_table.setItem(i, 6, status_item)
                for col in range(7):
                    it = self.results_table.item(i, col)
                    if it:
                        it.setBackground(bg)
                        it.setForeground(QColor("#1a1a1a"))

        self.analysis_table.update()
        self.results_table.update()

    def _export_to_pdf(self):
        """Экспорт одностраничного PDF-Паспорта семьи."""
        if not self.aggregate_mode and not self.current_data:
            QMessageBox.warning(self, "PDF-Паспорт", "Нет данных для формирования PDF-Паспорта.")
            return
        if self.aggregate_mode:
            default_path = "Паспорт_пчелосемьи.pdf"
            sample_name = "Сводная проба"
        else:
            default_path = str(self.current_data.path.with_name(f"{self.current_data.path.stem}_паспорт.pdf"))
            sample_name = self.current_data.path.stem

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF-Паспорт пчелосемьи", default_path, "PDF Документ (*.pdf)"
        )
        if not path:
            return
        try:
            generate_pdf_passport(
                self.current_data,
                path,
                sample_name=sample_name,
                target_breed=self.target_breed,
                analysis_result=self.last_result,
            )
            QMessageBox.information(self, "PDF-Паспорт готов", f"PDF-Паспорт пчелосемьи успешно сохранён:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка создания PDF", str(exc))

    def _export_to_excel(self):
        """Export the displayed analysis without changing the project or TPS."""
        if not self.aggregate_mode and not self.current_data:
            QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта")
            return
        default = "aggregate.xlsx" if self.aggregate_mode else str(self.current_data.path.with_suffix('.xlsx'))
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт анализа", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            self._do_export(path)
            QMessageBox.information(self, "Успех", f"Экспортировано:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", str(exc))

    def _do_export(self, path):
        """Выполнить экспорт в Excel (атомарная запись через временный файл)."""
        try:
            import openpyxl
            from openpyxl.styles import Font
        except ImportError:
            raise ImportError("pip install openpyxl")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Анализ"

        ws.cell(1, 1, "Анализ результатов исследований").font = Font(bold=True, size=14)

        for row in range(self.analysis_table.rowCount()):
            for col in range(self.analysis_table.columnCount()):
                item = self.analysis_table.item(row, col)
                if item:
                    ws.cell(row + 3, col + 1, item.text())

        ws2 = wb.create_sheet("Крылья")
        headers = ["№", "Кубитальный индекс", "% Алпатова", "Дискоидальное смещение",
                   "Гантельный индекс", "Порода", "Статус"]
        for col, h in enumerate(headers, 1):
            cell = ws2.cell(1, col, h)
            cell.font = Font(bold=True)

        for row in range(self.results_table.rowCount()):
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                if item:
                    ws2.cell(row + 2, col + 1, item.text())

        target = Path(path)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=target.name, suffix='.xlsx')
        os.close(fd)
        try:
            wb.save(temporary)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
