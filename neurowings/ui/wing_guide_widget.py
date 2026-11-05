#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Наглядная схема крыла пчелы (точки 1–8) и Памятка пчеловода.
"""

from __future__ import annotations

from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QTextBrowser, QDialogButtonBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF
)


POINT_DESCRIPTIONS_RU = {
    0: "Точка 1: Основание базовой радиомедиальной жилки (ближе к телу пчелы).",
    1: "Точка 2: Дальний (внешний) узел базовой жилки — задаёт опорную ось 1–2.",
    2: "Точка 3: Верхний (дальний от основания) конец гантельной жилки.",
    3: "Точка 4: Нижний (ближний к основанию) конец гантельной жилки.",
    4: "Точка 5: Левый (ближний) угол 3-й кубитальной ячейки (начало отрезка a).",
    5: "Точка 6: Нижний излом 3-й кубитальной ячейки (между отрезками a и b).",
    6: "Точка 7: Правый (дальний) угол 3-й кубитальной ячейки (конец отрезка b).",
    7: "Точка 8: Узел дискоидальной ячейки (снизу) для расчёта смещения DsA.",
}


class WingSchematicCanvas(QWidget):
    """Векторная схема переднего крыла пчелы с жилками и точками 1..8."""

    # Нормализованные координаты (0..1) 8 точек по стандарту WingsDig
    NORM_POINTS = [
        (0.10, 0.44),  # 1: База левая
        (0.88, 0.34),  # 2: База правая
        (0.50, 0.48),  # 3: Гантельная правая/верхняя
        (0.28, 0.50),  # 4: Гантельная левая/нижняя
        (0.50, 0.64),  # 5: Кубитальная начало a
        (0.61, 0.72),  # 6: Кубитальная излом (a/b)
        (0.69, 0.70),  # 7: Кубитальная конец b
        (0.47, 0.87),  # 8: Дискоидальная точка
    ]

    def __init__(self, parent=None, compact: bool = True):
        super().__init__(parent)
        self.compact = compact
        self.active_point_idx: Optional[int] = None
        self.setMinimumHeight(135 if compact else 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_active_point(self, idx: Optional[int]):
        if idx is not None and (idx < 0 or idx >= 8):
            idx = None
        self.active_point_idx = idx
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        painter.fillRect(self.rect(), QColor("#fcfcfc"))

        # Рамка
        painter.setPen(QPen(QColor("#dee2e6"), 1))
        painter.drawRoundedRect(1, 1, int(w - 2), int(h - 2), 6, 6)

        def pt(nx: float, ny: float) -> QPointF:
            return QPointF(nx * (w - 16) + 8, ny * (h - 16) + 8)

        # Контур крыла (плавный силуэт)
        wing_path = QPainterPath()
        wing_path.moveTo(pt(0.03, 0.42))
        wing_path.cubicTo(pt(0.25, 0.08), pt(0.78, 0.04), pt(0.96, 0.28))
        wing_path.cubicTo(pt(0.98, 0.55), pt(0.76, 0.94), pt(0.40, 0.96))
        wing_path.cubicTo(pt(0.18, 0.94), pt(0.05, 0.72), pt(0.03, 0.42))
        painter.setPen(QPen(QColor("#adb5bd"), 1.5))
        painter.setBrush(QBrush(QColor(235, 246, 255, 90)))
        painter.drawPath(wing_path)

        coords = [pt(nx, ny) for nx, ny in self.NORM_POINTS]
        p1, p2, p3, p4, p5, p6, p7, p8 = coords

        # Вспомогательные жилки крыла
        vein_pen = QPen(QColor("#868e96"), 1.5, Qt.SolidLine)
        painter.setPen(vein_pen)
        painter.drawLine(p1, p4)
        painter.drawLine(p3, p5)
        painter.drawLine(p4, QPointF(p8.x() - 18, p8.y() - 6))
        painter.drawLine(p5, p8)
        painter.drawLine(p7, QPointF(p2.x() - 10, p2.y() + 18))
        painter.drawLine(p3, QPointF((p1.x() + p2.x()) * 0.55, p2.y() + 2))

        # Опорная линия 1-2 (синяя)
        painter.setPen(QPen(QColor("#1971c2"), 2.0, Qt.DashLine))
        painter.drawLine(p1, p2)

        # Гантельная линия 3-4 (фиолетовая) и 5-7
        painter.setPen(QPen(QColor("#9c36b5"), 2.0, Qt.SolidLine))
        painter.drawLine(p3, p4)

        # Кубитальная ячейка: отрезок a (5-6) и отрезок b (6-7)
        painter.setPen(QPen(QColor("#e03131"), 2.6, Qt.SolidLine))
        painter.drawLine(p5, p6)
        painter.setPen(QPen(QColor("#2f9e44"), 2.6, Qt.SolidLine))
        painter.drawLine(p6, p7)

        # Подписи отрезков a и b
        font_small = QFont("Arial", 8 if self.compact else 10, QFont.Bold)
        painter.setFont(font_small)
        painter.setPen(QColor("#c92a2a"))
        painter.drawText(QPointF((p5.x() + p6.x()) / 2 - 4, (p5.y() + p6.y()) / 2 + 12), "a")
        painter.setPen(QColor("#2b8a3e"))
        painter.drawText(QPointF((p6.x() + p7.x()) / 2 + 2, (p6.y() + p7.y()) / 2 + 12), "b")

        # Перпендикуляр DsA от линии 1-2 через точку 3 к точке 8
        proj_x = p3.x()
        proj_y = p1.y() + (p2.y() - p1.y()) * ((p3.x() - p1.x()) / max(1.0, p2.x() - p1.x()))
        proj_pt = QPointF(proj_x, proj_y)
        painter.setPen(QPen(QColor("#f08c00"), 1.5, Qt.DotLine))
        painter.drawLine(proj_pt, p8)

        # Рисуем 8 точек с номерами 1..8
        radius = 8.0 if self.compact else 10.5
        font_num = QFont("Arial", 8 if self.compact else 9, QFont.Bold)
        painter.setFont(font_num)

        for idx, c in enumerate(coords):
            is_active = (self.active_point_idx == idx)
            r = radius * (1.28 if is_active else 1.0)
            fill = QColor("#ffd43b") if is_active else QColor("#228be6")
            border = QColor("#d9480f") if is_active else QColor("#ffffff")
            painter.setPen(QPen(border, 2.0 if is_active else 1.5))
            painter.setBrush(QBrush(fill))
            painter.drawEllipse(c, r, r)

            painter.setPen(QColor("#111111") if is_active else QColor("#ffffff"))
            text_rect = painter.fontMetrics().boundingRect(str(idx + 1))
            painter.drawText(
                QPointF(c.x() - text_rect.width() / 2.0, c.y() + text_rect.height() / 3.2),
                str(idx + 1),
            )


class WingGuideWidget(QWidget):
    """Компактный виджет-подсказка со схемой точек 1–8 для правой панели."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.canvas = WingSchematicCanvas(self, compact=True)
        layout.addWidget(self.canvas)

        self.lbl_hint = QLabel(
            "💡 <b>Подсказка:</b> точки нумеруются от <b>1 до 8</b> на каждом крыле. "
            "Зажмите точку мышкой, чтобы подвинуть её на перекрестие жилок."
        )
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(
            "font-size: 11px; color: #333333; background-color: #f8f9fa; "
            "border: 1px solid #e9ecef; border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self.lbl_hint)

        self.btn_help = QPushButton("❓ Памятка: Как определить породу за 3 шага")
        self.btn_help.setStyleSheet(
            "QPushButton { background-color: #e7f5ff; color: #1864ab; font-weight: bold; "
            "border: 1px solid #74c0fc; padding: 5px; }"
            "QPushButton:hover { background-color: #d0ebff; }"
        )
        self.btn_help.clicked.connect(self.show_beekeeper_guide)
        layout.addWidget(self.btn_help)

    def set_active_point(self, point_idx: Optional[int]):
        self.canvas.set_active_point(point_idx)
        if point_idx is not None and point_idx in POINT_DESCRIPTIONS_RU:
            self.lbl_hint.setText(f"📍 <b>{POINT_DESCRIPTIONS_RU[point_idx]}</b>")
        else:
            self.lbl_hint.setText(
                "💡 <b>Подсказка:</b> точки нумеруются от <b>1 до 8</b> на каждом крыле. "
                "Зажмите точку мышкой, чтобы подвинуть её на перекрестие жилок."
            )

    def show_beekeeper_guide(self):
        dlg = BeekeeperGuideDialog(self.window())
        dlg.exec_()


class BeekeeperGuideDialog(QDialog):
    """Иллюстрированная пошаговая памятка для обычного пчеловода."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("❓ Памятка пчеловода: Определяем породу пчёл за 3 шага")
        self.resize(780, 680)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QLabel("🐝 Как определить породу пчёл по крыльям за 3 минуты")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #1864ab;")
        layout.addWidget(header)

        canvas_box = QWidget()
        cb_layout = QVBoxLayout(canvas_box)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        lbl_schema = QLabel("📌 Образец правильной расстановки 8 точек на переднем крыле пчелы:")
        lbl_schema.setStyleSheet("font-weight: bold; font-size: 13px; color: #222222;")
        cb_layout.addWidget(lbl_schema)
        self.schematic = WingSchematicCanvas(self, compact=False)
        cb_layout.addWidget(self.schematic)
        layout.addWidget(canvas_box)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            "QTextBrowser { background-color: #ffffff; color: #222222; "
            "border: 1px solid #ced4da; border-radius: 6px; padding: 10px; font-size: 13px; }"
        )
        browser.setHtml(self._build_guide_html())
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        btn_close = buttons.button(QDialogButtonBox.Close)
        if btn_close:
            btn_close.setText("Понятно, закрыть")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _build_guide_html() -> str:
        return """
        <h3 style="color:#2b8a3e; margin-top:4px;">Шаг 1. Подготовьте и загрузите скан крыльев</h3>
        <ul>
          <li>Возьмите <b>25–30 рабочих пчёл</b> из одного улья (используются большие <b>передние крылья</b>).</li>
          <li>Разложите крылышки рядами на прозрачном скотче или стекле сканера так, чтобы они не наезжали друг на друга.</li>
          <li>Отсканируйте с разрешением <b>1200–2400 DPI</b> (подходят форматы <code>JPG, PNG, TIF, BMP</code>) или сфотографируйте через микроскоп.</li>
          <li>Нажмите кнопку <b>«📂 Открыть скан/фото»</b> (или просто <b>перетащите файл мышкой</b> прямо в окно программы).</li>
        </ul>

        <h3 style="color:#1971c2;">Шаг 2. Нажмите «⚡ Обработать» и проверьте точки 1–8</h3>
        <ul>
          <li>Нажмите <b>«⚡ Обработать»</b> (или клавишу <code>Пробел</code>) — нейросеть сама найдёт все крылья и расставит на каждом <b>8 точек</b>.</li>
          <li>Если точка чуть съехала с жилки — просто <b>возьмите точку мышкой и перетащите</b> в центр перекрестия жилок (переключать режим не нужно!).</li>
          <li>Если программа пропустила крыло — нажмите <b>«⬜ Рамка»</b> и обведите крыло прямоугольником: программа сама расставит внутри него 8 точек!</li>
          <li>Если на скан попало рваное крыло или мусор — снимите галочку в таблице справа (колонка <b>«В расчёте»</b>) или нажмите <b>«🗑 Удалить крыло»</b>.</li>
        </ul>

        <h3 style="color:#e67700;">Куда ставятся точки 1–8 (памятка по жилкам):</h3>
        <ol>
          <li><b>Точки 1 и 2</b> — начало и конец длинной прямой опорной жилки вдоль крыла.</li>
          <li><b>Точка 3</b> — верхний (дальний) узел гантельной жилки, <b>Точка 4</b> — нижний (ближний к основанию крыла) узел. <i>Важно не перепутать 3 и 4 местами!</i></li>
          <li><b>Точки 5, 6, 7</b> — три нижних угла 3-й кубитальной ячейки по порядку слева направо (отрезок <b>5–6</b> — это <b>a</b>, отрезок <b>6–7</b> — это <b>b</b>, кубитальный индекс <b>CI = a / b</b>).</li>
          <li><b>Точка 8</b> — нижний узел дискоидальной ячейки (определяет угол дискоидального смещения <b>DsA</b>: отрицательный у Среднерусской, положительный у Карники и Карпатки).</li>
        </ol>

        <h3 style="color:#9c36b5;">Шаг 3. Посмотрите диагноз по улью и скачайте PDF-Паспорт</h3>
        <ul>
          <li>Откройте вкладку <b>«📊 Анализ результатов»</b> или <b>«🐝 Интерпретация»</b>:</li>
          <li><b>17 баллов</b> — <b>Элита</b> (родоначальница линии, эталон породы);</li>
          <li><b>15–16 баллов</b> — <b>Чистопородная семья</b> (отлично подходит для вывода маток);</li>
          <li><b>10–14 баллов</b> — <b>Хорошая семья</b> (пригодна для селекции и закрепления признаков);</li>
          <li><b>5–9 баллов</b> — <b>Пользовательная семья</b> (на мёд, есть заметная примесь других пород);</li>
          <li><b>менее 5 баллов</b> — <b>Сильная помесь / гибрид</b> (рекомендуется плановая замена матки).</li>
          <li>Нажмите <b>«📄 PDF-Паспорт»</b> на верхней панели, чтобы сохранить красивый одностраничный сертификат семьи с таблицей, 2D-картой породности и графиками!</li>
        </ul>
        """
