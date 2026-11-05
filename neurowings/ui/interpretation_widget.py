#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Виджет экспертной интерпретации данных (адаптивный для всех пород пчёл, v2.2.0)
"""

import html
from pathlib import Path
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QFileDialog, QMessageBox
)

from ..core.constants import BREEDS, BREED_NAMES_RU, format_breed_ru
from ..core.data_models import ImageData
from ..core.colony_analysis import analyze_colony
from ..core.pdf_passport import generate_pdf_passport


class InterpretationRequest(QThread):
    result = pyqtSignal(str)

    def __init__(self, client, model, payload, parent):
        super().__init__(parent)
        self.client, self.model, self.payload = client, model, payload

    def run(self):
        try:
            client = self.client.with_options(timeout=20, max_retries=0)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': 'Интерпретируй морфометрию крыльев пчелосемьи на русском языке, укажи ограничения данных: ' + str(self.payload)
                }],
                max_tokens=250,
                temperature=0.2,
            )
            self.result.emit(response.choices[0].message.content or '')
        except Exception as exc:
            self.result.emit('Ошибка запроса: ' + str(exc))


def start_interpretation(widget):
    if not (widget.llm_enabled and widget.llm_client and widget.llm_model and widget._last_payload):
        return
    if getattr(widget, '_request', None) and widget._request.isRunning():
        return
    snapshot = dict(widget._last_payload)
    request = InterpretationRequest(widget.llm_client, widget.llm_model, snapshot, widget)
    widget._request = request
    widget._gpt_button.setEnabled(False)

    def ready(text):
        if widget._last_payload == snapshot:
            base = widget.text_edit.toHtml().split('<hr')[0]
            widget.text_edit.setHtml(base + widget._render_llm_block(text))

    request.result.connect(ready)
    request.finished.connect(lambda: widget._gpt_button.setEnabled(bool(widget.llm_enabled and widget._last_payload)))
    request.start()


class InterpretationWidget(QWidget):
    """Виджет экспертной интерпретации данных (поддерживает все породы справочника)"""

    target_breed_changed = pyqtSignal(str)

    def __init__(self, parent=None, title: str = "🐝 Интерпретация данных и вердикт по семье"):
        super().__init__(parent)
        self.title_text = title
        self.llm_client = None
        self.llm_model = None
        self.llm_enabled = False
        self._last_payload = None
        self._current_data = None
        self._last_result = None
        self.target_breed = "auto"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel(self.title_text)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c5aa0;")
        header.addWidget(title)
        header.addStretch()

        lbl_target = QLabel("Целевая порода для оценки:")
        lbl_target.setStyleSheet("font-weight: bold; color: #222222;")
        header.addWidget(lbl_target)

        self.breed_combo = QComboBox()
        self.breed_combo.addItem("Авто (по преобладающей породе)", "auto")
        for b_key, b_name_ru in BREED_NAMES_RU.items():
            self.breed_combo.addItem(b_name_ru, b_key)
        self.breed_combo.currentIndexChanged.connect(self._on_breed_combo_changed)
        header.addWidget(self.breed_combo)

        self.btn_pdf = QPushButton("📄 PDF-Паспорт")
        self.btn_pdf.setToolTip("Сохранить одностраничный сертификат (паспорт) пчелосемьи в PDF")
        self.btn_pdf.clicked.connect(self._export_pdf)
        header.addWidget(self.btn_pdf)

        layout.addLayout(header)

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

        self._gpt_button = QPushButton("🤖 Получить развёрнутый комментарий ИИ (GPT)")
        self._gpt_button.setEnabled(False)
        self._gpt_button.setVisible(False)
        self._gpt_button.clicked.connect(self.request_llm)
        layout.addWidget(self._gpt_button)

    def _on_breed_combo_changed(self, _index: int):
        self.target_breed = self.breed_combo.currentData() or "auto"
        self.target_breed_changed.emit(self.target_breed)
        if self._current_data is not None:
            self.update_interpretation(self._current_data)

    def set_target_breed(self, breed_key: str):
        idx = self.breed_combo.findData(breed_key or "auto")
        if idx >= 0 and idx != self.breed_combo.currentIndex():
            self.breed_combo.blockSignals(True)
            self.breed_combo.setCurrentIndex(idx)
            self.breed_combo.blockSignals(False)
        self.target_breed = breed_key or "auto"

    def set_message(self, msg: str):
        self._last_payload = None
        self.text_edit.setText(msg)

    def set_llm(self, client, model: str, enabled: bool = True):
        self.llm_client = client
        self.llm_model = model
        self.llm_enabled = enabled
        has_llm = bool(enabled and client and model)
        if hasattr(self, "_gpt_button"):
            self._gpt_button.setEnabled(has_llm)
            self._gpt_button.setVisible(has_llm)

    @staticmethod
    def _evaluate_index_for_breed(val: float, breed_key: str, index_name: str, unit: str = ""):
        """Оценить среднее значение индекса относительно стандарта выбранной породы."""
        if not breed_key or breed_key not in BREEDS:
            return f"Вне эталонных стандартов чистых пород", "bad"

        lo, hi = BREEDS[breed_key][index_name]
        breed_ru = format_breed_ru(breed_key, short=True)
        span = max(1e-6, hi - lo)
        margin_inner = 0.08 * span
        margin_outer = 0.18 * span

        range_str = f"{lo:.2f}…{hi:.2f}{unit}" if index_name != "HI" else f"{lo:.3f}…{hi:.3f}"

        if (lo + margin_inner) <= val <= (hi - margin_inner):
            return f"В уверенном стандарте породы {breed_ru} (норма {range_str})", "good"
        if lo <= val <= hi:
            return f"Укладывается в границы породы {breed_ru} (норма {range_str}, ближе к краю диапазона)", "good"
        if (lo - margin_outer) <= val <= (hi + margin_outer):
            return f"Небольшое отклонение от стандарта {breed_ru} (норма {range_str}) — возможна лёгкая примесь", "warn"
        return f"Выходит за пределы стандарта породы {breed_ru} (норма {range_str})", "bad"

    def update_data(self, image_data, target_breed: str = None):
        """Алиас для update_interpretation."""
        return self.update_interpretation(image_data, target_breed=target_breed)

    def update_interpretation(self, image_data, target_breed: str = None):
        """Обновить интерпретацию для изображения или списка крыльев."""
        if target_breed is not None:
            self.set_target_breed(target_breed)
        self._current_data = image_data

        if not image_data or (isinstance(image_data, ImageData) and not image_data.wings):
            self._last_payload = None
            self._last_result = None
            self.text_edit.setText("Нет данных для интерпретации")
            return

        if isinstance(image_data, list):
            wings = image_data
        else:
            image_data.analyze_all_wings()
            wings = image_data.wings

        if not wings:
            self._last_payload = None
            self._last_result = None
            self.text_edit.setText("Нет данных для интерпретации")
            return

        res = analyze_colony(wings, target_breed=self.target_breed, reanalyze_wings=False)
        self._last_result = res

        if not res.ci.values:
            self.text_edit.setText("Недостаточно данных для анализа")
            return

        eval_breed = res.eval_breed or res.closest_breed
        eval_breed_ru = format_breed_ru(res.eval_breed) if res.eval_breed else (
            f"Помесь / Бакфаст (ближайший профиль: {format_breed_ru(res.closest_breed, short=True)})"
            if res.closest_breed else "Помесь / Бакфаст (вне стандарта)"
        )

        ci_txt, ci_state = self._evaluate_index_for_breed(res.ci.mean, res.eval_breed, "CI")
        dsa_txt, dsa_state = self._evaluate_index_for_breed(res.dsa.mean, res.eval_breed, "DsA", "°")
        hi_txt, hi_state = self._evaluate_index_for_breed(res.hi.mean, res.eval_breed, "HI")

        def icon(state):
            return {"good": "✅", "warn": "⚠️", "bad": "❌"}.get(state, "ℹ️")

        card_colors = {
            "elite": ("#ebfbee", "#2b8a3e", "🏆"),
            "good": ("#ebfbee", "#2b8a3e", "✅"),
            "warn": ("#fff9db", "#e67700", "⚠️"),
            "bad": ("#fff5f5", "#c92a2a", "❌"),
            "neutral": ("#f8f9fa", "#495057", "ℹ️"),
        }
        bg_hex, border_hex, badge_icon = card_colors.get(res.verdict_level, ("#f8f9fa", "#2c5aa0", "🐝"))

        in_cnt = len(res.wings_in_eval_breed)
        in_pct = 100.0 * in_cnt / res.total if res.total > 0 else 0.0
        out_wings = res.wings_out_of_eval_breed
        if out_wings:
            out_str = ", ".join(f"№{n}" for n in out_wings[:15])
            if len(out_wings) > 15:
                out_str += f" … (всего {len(out_wings)})"
        else:
            out_str = "нет (все крылья в стандарте)"

        rutt = res.ruttner
        rutt_html = (
            f"отрицательное (<b>−</b>): <b>{rutt.get('minus', 0)}</b> ({rutt.get('pct_minus', 0.0):.0f}%), "
            f"нулевое (<b>0</b>): <b>{rutt.get('zero', 0)}</b> ({rutt.get('pct_zero', 0.0):.0f}%), "
            f"положительное (<b>+</b>): <b>{rutt.get('plus', 0)}</b> ({rutt.get('pct_plus', 0.0):.0f}%)"
        )

        other_breeds_list = []
        for b_key, cnt in sorted(res.breed_counts.items(), key=lambda kv: -kv[1]):
            if cnt > 0:
                other_breeds_list.append(f"{format_breed_ru(b_key, short=True)}: <b>{cnt}</b> кр.")
        breeds_breakdown_html = ", ".join(other_breeds_list) if other_breeds_list else "крылья не попали в чистые эталоны"

        text = f"""
<div style="background-color:{bg_hex}; border:2px solid {border_hex}; border-radius:8px; padding:12px; margin-bottom:12px;">
  <h3 style="margin:0 0 6px 0; color:{border_hex};">{badge_icon} {html.escape(res.verdict_title)} — {res.total_score} из {res.max_possible_score} баллов</h3>
  <p style="margin:4px 0; font-size:14px;"><b>Определённая / оцениваемая порода:</b> {html.escape(eval_breed_ru)}</p>
  <p style="margin:4px 0;"><b>Рекомендация пасечнику:</b> {html.escape(res.verdict_recommendation)}</p>
</div>

<h4>📋 Сводка по крыльям пробы:</h4>
<ul>
  <li><b>Крыльев в расчёте:</b> {res.total} {f'(исключено галочкой: {res.disabled_wings_count})' if res.disabled_wings_count else ''}</li>
  <li><b>В стандарте породы ({html.escape(format_breed_ru(res.eval_breed, short=True))}):</b> {in_cnt} из {res.total} ({in_pct:.1f}%)</li>
  <li><b>Крылья с отклонением от стандарта:</b> {out_str}</li>
  <li><b>Попадание крыльев в породные диапазоны:</b> {breeds_breakdown_html}</li>
  <li><b>Вероятностное соответствие породе (с учётом 95% эллипса семьи):</b> {res.breed_match_pct:.1f}% (+{res.breed_score} балл.)</li>
</ul>

<h4>🔬 Оценка морфометрических индексов семьи:</h4>
<ul>
  <li><b>Кубитальный индекс (CI):</b> <b>{res.ci.mean:.3f} ± {res.ci.sem:.3f}</b> ({res.alpatov_pct:.1f}% Алпатова, разброс {res.ci.cv:.1f}%) — {icon(ci_state)} {ci_txt} <i>(целостность: +{res.ci_score}, чистота: +{res.ci_hyb_score})</i></li>
  <li><b>Дискоидальное смещение (DsA):</b> <b>{res.dsa.mean:+.2f}° ± {res.dsa.sem:.2f}°</b> — {icon(dsa_state)} {dsa_txt} <i>(чистота: +{res.dsa_hyb_score})</i><br>
      <span style="color:#444444;">Распределение по классам Руттнера: {rutt_html}</span></li>
  <li><b>Гантельный индекс (HI):</b> <b>{res.hi.mean:.3f} ± {res.hi.sem:.3f}</b> (разброс {res.hi.cv:.1f}%) — {icon(hi_state)} {hi_txt} <i>(целостность: +{res.hi_score}, чистота: +{res.hi_hyb_score})</i></li>
</ul>
"""

        self._last_payload = {
            "wings": res.total,
            "breed": res.eval_breed_ru,
            "score": res.total_score,
            "identified_pct": res.id_wings_pct,
            "breed_match_pct": res.breed_match_pct,
            "mean_ci": res.ci.mean,
            "mean_dsa": res.dsa.mean,
            "mean_hi": res.hi.mean,
            "ci_state": ci_state,
            "dsa_state": dsa_state,
            "hi_state": hi_state,
        }
        self.text_edit.setHtml(text + self._render_llm_block())

    def _export_pdf(self):
        if not self._current_data:
            QMessageBox.warning(self, "PDF-Паспорт", "Нет данных для формирования PDF-Паспорта.")
            return
        if isinstance(self._current_data, ImageData):
            default_path = str(self._current_data.path.with_name(f"{self._current_data.path.stem}_паспорт.pdf"))
            sample_name = self._current_data.path.stem
        else:
            default_path = "Паспорт_пчелосемьи.pdf"
            sample_name = "Сводная проба"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF-Паспорт пчелосемьи", default_path, "PDF Документ (*.pdf)"
        )
        if not path:
            return
        try:
            generate_pdf_passport(
                self._current_data,
                path,
                sample_name=sample_name,
                target_breed=self.target_breed,
                analysis_result=self._last_result,
            )
            QMessageBox.information(self, "PDF-Паспорт готов", f"PDF-Паспорт успешно сохранён:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка создания PDF", str(exc))

    def _render_llm_block(self, content: str = ""):
        """Вернуть HTML для блока GPT"""
        if content:
            return f"<hr><p><b>🤖 Комментарий GPT:</b> {html.escape(str(content))}</p>"
        if self.llm_enabled and self.llm_client and self.llm_model:
            return "<hr><p><i>Комментарий GPT не запрашивался.</i></p>"
        return ""

    def request_llm(self):
        start_interpretation(self)


class GlobalInterpretationWidget(QWidget):
    """Агрегированная интерпретация по всем открытым пробам пасеки (адаптивная ко всем породам)"""

    def __init__(self, parent=None, title: str = "🌐 Общая интерпретация по пасеке"):
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

        self._gpt_button = QPushButton("🤖 Получить ответ GPT по пасеке")
        self._gpt_button.setEnabled(False)
        self._gpt_button.setVisible(False)
        self._gpt_button.clicked.connect(self.request_llm)
        layout.addWidget(self._gpt_button)

    def set_message(self, msg: str):
        self._last_payload = None
        self.text_edit.setText(msg)

    def set_llm(self, client, model: str, enabled: bool = True):
        self.llm_client = client
        self.llm_model = model
        self.llm_enabled = enabled
        has_llm = bool(enabled and client and model)
        if hasattr(self, "_gpt_button"):
            self._gpt_button.setEnabled(has_llm)
            self._gpt_button.setVisible(has_llm)

    def _detect_shape(self, values):
        issues = []
        if len(values) < 3:
            return issues
        counts, _ = np.histogram(values, bins=10)
        for i in range(1, len(counts) - 1):
            if counts[i] == 0 and counts[i - 1] > 0 and counts[i + 1] > 0:
                issues.append("провал/расщепление")
                break
        peaks = 0
        for i in range(1, len(counts) - 1):
            if counts[i] > counts[i - 1] and counts[i] > counts[i + 1] and counts[i] > 0:
                peaks += 1
        if peaks > 1:
            issues.append("два пика (признак гибридизации)")
        if np.std(values) < 0.03 * abs(np.mean(values)):
            issues.append("очень узкий разброс (высокая однородность)")
        return issues

    def update_global(self, images: dict, single_mode: bool = False):
        if single_mode:
            self.set_message("Режим одиночного крыла (1 фото = 1 крыло): сводный результат смотрите во вкладках «📊 Анализ результатов» и «🐝 Интерпретация».")
            return
        if not images:
            self.set_message("Нет данных для интерпретации.")
            return

        summaries = []
        for path_str, img in images.items():
            if not img or not img.wings:
                continue
            res = analyze_colony(img, reanalyze_wings=True)
            if not res.ci.values:
                continue
            issues = []
            issues += [f"CI — {p}" for p in self._detect_shape(res.ci.values)]
            issues += [f"DsA — {p}" for p in self._detect_shape(res.dsa.values)]
            issues += [f"HI — {p}" for p in self._detect_shape(res.hi.values)]
            summaries.append({
                "name": Path(path_str).name if hasattr(Path(path_str), 'name') else str(path_str),
                "breed_ru": res.dominant_breed_ru,
                "score": res.total_score,
                "verdict": res.verdict_title,
                "ci": res.ci.mean,
                "dsa": res.dsa.mean,
                "hi": res.hi.mean,
                "id_pct": res.id_wings_pct,
                "match_pct": res.breed_match_pct,
                "issues": issues,
            })

        if not summaries:
            self.set_message("Нет данных для интерпретации.")
            return

        # Сортируем семьи от лучших к худшим по итоговому баллу и вероятности соответствия своей породе
        summaries.sort(key=lambda x: (x["score"], x["match_pct"], x["id_pct"]), reverse=True)
        worst = summaries[-1]

        def fmt_item(s):
            probs = "; ".join(s["issues"]) if s["issues"] else "однородное распределение"
            return (
                f"<b>{html.escape(s['name'])}</b> — порода: <b>{html.escape(s['breed_ru'])}</b>, "
                f"балл: <b>{s['score']}/17</b> ({html.escape(s['verdict'])}), "
                f"CI {s['ci']:.3f}, DsA {s['dsa']:+.2f}°, HI {s['hi']:.3f}, "
                f"в стандарте {s['id_pct']:.1f}%, распределение: {html.escape(probs)}"
            )

        lines = ["<h3>🌐 Сводный рейтинг семей по пасеке</h3>"]
        lines.append("<p><b>🏆 Лучшие чистопородные семьи (кандидаты для репродукции и вывода маток):</b></p><ul>")
        for s in summaries[:3]:
            lines.append(f"<li>{fmt_item(s)}</li>")
        lines.append("</ul>")

        if len(summaries) > 1:
            lines.append("<p><b>⚠️ Семья с наибольшей метизацией / разбросом (кандидат на замену матки):</b></p>")
            lines.append(f"<p>{fmt_item(worst)}</p>")

        lines.append("<p><b>📊 Анализ однородности распределений по семьям:</b></p><ul>")
        any_issues = False
        for s in summaries:
            if s['issues']:
                any_issues = True
                lines.append(f"<li><b>{html.escape(s['name'])}</b> ({html.escape(s['breed_ru'])}): {', '.join(s['issues'])}</li>")
        if not any_issues:
            lines.append("<li>Во всех семьях распределения ровные, без расщепления на несколько породных групп.</li>")
        lines.append("</ul>")

        self._last_payload = {
            "best": summaries[0],
            "worst": summaries[-1],
            "issues": {s['name']: s['issues'] for s in summaries if s['issues']},
        }
        self.text_edit.setHtml("\n".join(lines) + self._render_llm_block())

    def _render_llm_block(self, content: str = ""):
        if content:
            return f"<hr><p><b>🤖 Комментарий GPT:</b> {html.escape(str(content))}</p>"
        if self.llm_enabled and self.llm_client and self.llm_model:
            return "<hr><p><i>Комментарий GPT не запрашивался.</i></p>"
        return ""

    def request_llm(self):
        start_interpretation(self)
