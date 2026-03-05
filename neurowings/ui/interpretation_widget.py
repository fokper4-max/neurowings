#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет интерпретации данных
"""

import numpy as np
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton

from ..core.constants import BREEDS
from ..core.data_models import ImageData


class InterpretationWidget(QWidget):
    """Виджет экспертной интерпретации данных"""
    
    def __init__(self, parent=None, title: str = "🐝 Интерпретация данных"):
        super().__init__(parent)
        self.title_text = title
        self.llm_client = None
        self.llm_model = None
        self.llm_enabled = False
        self._last_payload = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(self.title_text)
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

        # Кнопка ручного вызова GPT
        self._gpt_button = QPushButton("Получить ответ GPT")
        self._gpt_button.setEnabled(False)
        self._gpt_button.clicked.connect(self.request_llm)
        layout.addWidget(self._gpt_button)

    def set_message(self, msg: str):
        self.text_edit.setText(msg)

    def set_llm(self, client, model: str, enabled: bool = True):
        self.llm_client = client
        self.llm_model = model
        self.llm_enabled = enabled
        # Когда GPT выключен, прячем блок; включаем по кнопке при запросе
        if not enabled or not client or not model:
            if hasattr(self, "_gpt_button"):
                self._gpt_button.setEnabled(False)
        else:
            if hasattr(self, "_gpt_button"):
                self._gpt_button.setEnabled(True)

    def _classify_ci(self, ci: float):
        if ci <= 1.6:
            return "Эталонная Mellifera (1.3–1.6)", "good"
        if ci <= 1.7:
            return "Хорошая Mellifera (1.6–1.7)", "good"
        if ci <= 1.9:
            return "Начало метизации (1.7–1.9)", "warn"
        if ci <= 2.1:
            return "Явная метизация (1.9–2.1)", "warn"
        if ci <= 2.3:
            return "Гибрид SR×южные (2.1–2.3)", "bad"
        return "Карника/Кавказянка (>2.3)", "bad"

    def _classify_dsa(self, dsa: float):
        if dsa < -5:
            return "Чистая Mellifera (< -5°)", "good"
        if dsa < -3:
            return "Хорошая Mellifera (-5…-3°)", "good"
        if dsa < -1:
            return "Лёгкая метизация (-3…-1°)", "warn"
        if dsa <= 1:
            return "Значительная метизация (-1…+1°)", "warn"
        return "Южные породы (> +1°)", "bad"

    def _classify_hi(self, hi: float):
        if hi < 0.70:
            return "Ниже эталона (<0.70)", "warn"
        if hi <= 0.80:
            return "Эталонная Mellifera (0.70–0.80)", "good"
        if hi <= 0.85:
            return "Хорошая Mellifera (0.80–0.85)", "good"
        if hi <= 0.90:
            return "Начало метизации (0.85–0.90)", "warn"
        return "Южные породы (>0.90)", "bad"

    def update_interpretation(self, image_data):
        """Обновить интерпретацию для изображения или агрегата"""
        if not image_data or (isinstance(image_data, ImageData) and not image_data.wings):
            self.text_edit.setText("Нет данных для интерпретации")
            return

        # Поддержка списка крыльев
        if isinstance(image_data, list):
            wings = image_data
        else:
            image_data.analyze_all_wings()
            wings = image_data.wings
        if not wings:
            self.text_edit.setText("Нет данных для интерпретации")
            return
        
        ci_values = [w.analysis.CI for w in wings if w.analysis and w.analysis.CI > 0]
        dsa_values = [w.analysis.DsA for w in wings if w.analysis]
        hi_values = [w.analysis.HI for w in wings if w.analysis and w.analysis.HI > 0]
        
        if not ci_values:
            self.text_edit.setText("Недостаточно данных для анализа")
            return
        
        mean_ci = float(np.mean(ci_values))
        mean_dsa = float(np.mean(dsa_values))
        mean_hi = float(np.mean(hi_values))
        
        identified = sum(1 for w in wings if w.analysis and w.analysis.is_identified)
        total = len(wings)
        id_pct = 100 * identified / total if total > 0 else 0

        ci_txt, ci_state = self._classify_ci(mean_ci)
        dsa_txt, dsa_state = self._classify_dsa(mean_dsa)
        hi_txt, hi_state = self._classify_hi(mean_hi)

        def icon(state):
            return {"good": "✅", "warn": "⚠️", "bad": "❌"}.get(state, "ℹ️")

        text = f"""<h3>📊 Экспертный анализ</h3>
<p><b>Общая характеристика:</b></p>
<ul>
<li>Исследовано крыльев: {total}</li>
<li>Идентифицировано: {identified} ({id_pct:.1f}%)</li>
</ul>

<p><b>Морфометрические показатели (по guide):</b></p>
<ul>
<li>Кубитальный индекс: {mean_ci:.3f} — {icon(ci_state)} {ci_txt}</li>
<li>Дискоидальное смещение: {mean_dsa:.2f} — {icon(dsa_state)} {dsa_txt}</li>
<li>Гантельный индекс: {mean_hi:.3f} — {icon(hi_state)} {hi_txt}</li>
</ul>
"""

        text += "<p><b>Заключение:</b></p>"
        good_count = sum(s == "good" for s in (ci_state, dsa_state, hi_state))
        bad_count = sum(s == "bad" for s in (ci_state, dsa_state, hi_state))
        if good_count == 3 and id_pct >= 90:
            text += "<p style='color:#4CAF50;'>🐝 Совпадает с эталоном Mellifera, рисков метизации не видно.</p>"
        elif bad_count >= 2 or mean_ci > 2.1 or mean_dsa > 0.5:
            text += "<p style='color:#f44336;'>❌ Сильная метизация/южный тип, использовать только на мёд.</p>"
        else:
            text += "<p style='color:#FFC107;'>⚠️ Есть признаки метизации, нужна селекция/контроль трутня.</p>"

        self._last_payload = {
            "wings": total,
            "identified_pct": id_pct,
            "mean_ci": mean_ci,
            "mean_dsa": mean_dsa,
            "mean_hi": mean_hi,
            "ci_state": ci_state,
            "dsa_state": dsa_state,
            "hi_state": hi_state,
        }
        self.text_edit.setHtml(text + self._render_llm_block())

    def _render_llm_block(self, content: str = ""):
        """Вернуть HTML для блока GPT (кнопка + ответ)"""
        # Ответ отображается в тексте, запуск — отдельной кнопкой в окне
        if content:
            return f"<hr><p><b>GPT:</b> {content}</p>"
        if self.llm_enabled and self.llm_client and self.llm_model:
            return "<hr><p><i>GPT не запрашивался.</i></p>"
        return ""

    def request_llm(self):
        """Запросить GPT по последним данным"""
        if not (self.llm_enabled and self.llm_client and self.llm_model and hasattr(self, "_last_payload")):
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + "<hr><p>GPT недоступен.</p>")
            return
        try:
            resp = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[{
                    "role": "user",
                    "content": (
                        "Ты эксперт по морфометрии пчелиных крыльев. Кратко и по делу интерпретируй данные, "
                        "дай вывод и рекомендации. Данные: " + str(self._last_payload)
                    )
                }],
                max_tokens=250,
                temperature=0.2,
            )
            llm_text = resp.choices[0].message.content
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + self._render_llm_block(llm_text))
        except Exception as e:
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + self._render_llm_block(f"ошибка запроса ({e})"))


class GlobalInterpretationWidget(QWidget):
    """Агрегированная интерпретация по всем файлам"""

    def __init__(self, parent=None, title: str = "🌐 Общая интерпретация"):
        super().__init__(parent)
        self.title_text = title
        self.llm_client = None
        self.llm_model = None
        self.llm_enabled = False
        self._last_payload = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel(self.title_text)
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

        # Кнопка ручного вызова GPT
        self._gpt_button = QPushButton("Получить ответ GPT")
        self._gpt_button.setEnabled(False)
        self._gpt_button.clicked.connect(self.request_llm)
        layout.addWidget(self._gpt_button)

    def set_message(self, msg: str):
        self.text_edit.setText(msg)

    def set_llm(self, client, model: str, enabled: bool = True):
        self.llm_client = client
        self.llm_model = model
        self.llm_enabled = enabled
        if hasattr(self, "_gpt_button"):
            self._gpt_button.setEnabled(bool(enabled and client and model))

    def _detect_shape(self, values):
        issues = []
        if len(values) < 3:
            return issues
        counts, bins = np.histogram(values, bins=10)
        # провал: ноль между ненулевыми
        for i in range(1, len(counts) - 1):
            if counts[i] == 0 and counts[i - 1] > 0 and counts[i + 1] > 0:
                issues.append("провал/расщепление")
                break
        # горбы: >1 локального максимума
        peaks = 0
        for i in range(1, len(counts) - 1):
            if counts[i] > counts[i - 1] and counts[i] > counts[i + 1] and counts[i] > 0:
                peaks += 1
        if peaks > 1:
            issues.append("горбы/мультимодальность")
        # плато: низкий разброс и ровное распределение
        if np.std(values) < 0.03 * np.mean(values):
            issues.append("плато (очень узкий разброс)")
        return issues

    def update_global(self, images: dict, single_mode: bool = False):
        if single_mode:
            self.set_message("Режим одиночного крыла: общая интерпретация отключена.")
            return
        if not images:
            self.set_message("Нет данных для интерпретации.")
            return

        summaries = []
        for path_str, img in images.items():
            if not img or not img.wings:
                continue
            img.analyze_all_wings()
            ci = [w.analysis.CI for w in img.wings if w.analysis and w.analysis.CI > 0]
            dsa = [w.analysis.DsA for w in img.wings if w.analysis]
            hi = [w.analysis.HI for w in img.wings if w.analysis and w.analysis.HI > 0]
            if not ci:
                continue
            mean_ci, mean_dsa, mean_hi = float(np.mean(ci)), float(np.mean(dsa)), float(np.mean(hi))
            identified = sum(1 for w in img.wings if w.analysis and w.analysis.is_identified)
            total = len(img.wings)
            id_pct = 100 * identified / total if total else 0
            dist = abs(mean_ci - 1.5) + abs(mean_dsa + 4) / 5 + abs(mean_hi - 0.78)
            issues = []
            issues += [f"CI — {p}" for p in self._detect_shape(ci)]
            issues += [f"DsA — {p}" for p in self._detect_shape(dsa)]
            issues += [f"HI — {p}" for p in self._detect_shape(hi)]
            summaries.append({
                "name": Path(path_str).name if hasattr(Path(path_str), 'name') else str(path_str),
                "ci": mean_ci, "dsa": mean_dsa, "hi": mean_hi,
                "id_pct": id_pct, "dist": dist, "issues": issues
            })

        if not summaries:
            self.set_message("Нет данных для интерпретации.")
            return

        summaries.sort(key=lambda x: x["dist"])
        best = summaries[0]
        worst = summaries[-1]

        def fmt_item(s):
            probs = "; ".join(s["issues"]) if s["issues"] else "нет"
            return (f"<b>{s['name']}</b> — CI {s['ci']:.3f}, DsA {s['dsa']:.2f}, HI {s['hi']:.3f}, "
                    f"идентиф. {s['id_pct']:.1f}%, проблемы: {probs}")

        lines = ["<h3>🌐 Общая интерпретация по всем файлам</h3>"]
        lines.append("<p><b>Лучшие пробы:</b></p><ul>")
        for s in summaries[:3]:
            lines.append(f"<li>{fmt_item(s)}</li>")
        lines.append("</ul>")

        lines.append("<p><b>Хуже всего совпадение:</b></p>")
        lines.append(f"<p>{fmt_item(worst)}</p>")

        lines.append("<p><b>Комментарии по формам распределений:</b></p><ul>")
        any_issues = False
        for s in summaries:
            if s['issues']:
                any_issues = True
                lines.append(f"<li>{s['name']}: {', '.join(s['issues'])}</li>")
        if not any_issues:
            lines.append("<li>Формы распределений без явных провалов/горбов.</li>")
        lines.append("</ul>")

        self._last_payload = {
            "best": summaries[0],
            "worst": summaries[-1],
            "issues": {s['name']: s['issues'] for s in summaries if s['issues']},
        }
        self.text_edit.setHtml("\n".join(lines) + self._render_llm_block())

    def _render_llm_block(self, content: str = ""):
        if content:
            return f"<hr><p><b>GPT:</b> {content}</p>"
        if self.llm_enabled and self.llm_client and self.llm_model:
            return "<hr><p><i>GPT не запрашивался.</i></p>"
        return ""

    def request_llm(self):
        """Запросить GPT по сохранённому payload"""
        if not (self.llm_enabled and self.llm_client and self.llm_model and self._last_payload):
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + "<hr><p>GPT недоступен.</p>")
            return
        try:
            resp = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[{
                    "role": "user",
                    "content": (
                        "Дай краткий вывод по пробам морфометрии крыльев: "
                        "1) итоги в 2-3 предложениях, 2) что лучше/хуже и почему, "
                        "3) одно предложение о проблемах распределений. "
                        "Без Markdown, без лишних подробностей. Данные: " + str(self._last_payload)
                    )
                }],
                max_tokens=220,
                temperature=0.2,
            )
            llm_text = resp.choices[0].message.content
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + self._render_llm_block(llm_text))
        except Exception as e:
            base_html = self.text_edit.toHtml().split("<hr")[0]
            self.text_edit.setHtml(base_html + self._render_llm_block(f"ошибка запроса ({e})"))
