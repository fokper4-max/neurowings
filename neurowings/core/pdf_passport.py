#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Генератор одностраничного PDF-Паспорта (Сертификата морфометрии пчелосемьи).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union
import numpy as np

from .constants import (
    APP_NAME, APP_VERSION, APP_TELEGRAM_LABEL,
    BREEDS, BREED_COLORS_HEX, BREED_SHORT_NAMES_RU
)
from .data_models import Wing, ImageData
from .colony_analysis import ColonyAnalysisResult, analyze_colony


def _draw_confidence_ellipse(ax, x_vals, y_vals, color="#d9480f", label="95% эллипс семьи"):
    """Нарисовать 95% доверительный эллипс двумерного распределения (x_vals, y_vals)."""
    from matplotlib.patches import Ellipse

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
    # chi2(df=2, p=0.95) = 5.991 -> sqrt(5.991) = 2.4477
    width, height = 2.0 * 2.4477 * np.sqrt(vals)
    ellipse = Ellipse(
        xy=(float(np.mean(x)), float(np.mean(y))),
        width=float(width),
        height=float(height),
        angle=theta,
        edgecolor=color,
        facecolor=color,
        alpha=0.14,
        linewidth=2.0,
        linestyle="--",
        label=label,
        zorder=4,
    )
    ax.add_patch(ellipse)


def generate_pdf_passport(
    data: Union[ImageData, List[Wing]],
    output_path: Union[str, Path],
    sample_name: Optional[str] = None,
    target_breed: Optional[str] = None,
    analysis_result: Optional[ColonyAnalysisResult] = None,
) -> Path:
    """
    Сгенерировать одностраничный PDF-Паспорт морфометрии пчелосемьи (формат A4).

    Возвращает путь к созданному PDF-файлу.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.gridspec import GridSpec

    # Поддержка обоих порядков аргументов: (data, output_path) и (output_path, data)
    if isinstance(data, (str, Path)) and not isinstance(output_path, (str, Path)):
        data, output_path = output_path, data

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, ImageData):
        wings = data.wings
        default_title = data.path.stem
    else:
        wings = list(data or [])
        default_title = "Сводная проба"

    title_str = sample_name or default_title
    res = analysis_result or analyze_colony(
        data, target_breed=target_breed, reanalyze_wings=not isinstance(data, list)
    )

    plt.style.use("default")
    # Лист A4 вертикальный (8.27 x 11.69 дюймов)
    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
    fig.patch.set_facecolor("#ffffff")

    gs = GridSpec(
        4, 3,
        figure=fig,
        height_ratios=[1.25, 1.35, 2.2, 1.45],
        hspace=0.38,
        wspace=0.28,
        left=0.07,
        right=0.95,
        top=0.94,
        bottom=0.06,
    )

    # 1. ШАПКА ПАСПОРТА
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.axis("off")

    level_colors = {
        "elite": ("#ebfbee", "#2b8a3e"),
        "good": ("#ebfbee", "#2b8a3e"),
        "warn": ("#fff9db", "#e67700"),
        "bad": ("#fff5f5", "#c92a2a"),
        "neutral": ("#f8f9fa", "#495057"),
    }
    bg_hex, border_hex = level_colors.get(res.verdict_level, ("#f8f9fa", "#2c5aa0"))

    header_box = Rectangle(
        (0.0, 0.02), 1.0, 0.96,
        transform=ax_header.transAxes,
        facecolor=bg_hex,
        edgecolor=border_hex,
        linewidth=1.8,
        zorder=1,
    )
    ax_header.add_patch(header_box)

    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    ax_header.text(
        0.03, 0.80,
        f"ПАСПОРТ МОРФОМЕТРИИ ПЧЕЛОСЕМЬИ: «{title_str}»",
        fontsize=13, fontweight="bold", color="#1a1a1a",
        transform=ax_header.transAxes, zorder=2,
    )
    ax_header.text(
        0.97, 0.80,
        f"Дата: {date_str}",
        fontsize=9.5, color="#444444", ha="right",
        transform=ax_header.transAxes, zorder=2,
    )

    breed_line = (
        f"Определённая порода: {res.eval_breed_ru}   |   "
        f"Итоговый балл: {res.total_score} из {res.max_possible_score}   |   "
        f"Крыльев в расчёте: {res.total} (в стандарте: {len(res.wings_in_eval_breed)}, {res.id_wings_pct:.1f}%)"
    )
    ax_header.text(
        0.03, 0.50,
        breed_line,
        fontsize=10.5, fontweight="bold", color=border_hex,
        transform=ax_header.transAxes, zorder=2,
    )

    ax_header.text(
        0.03, 0.20,
        f"Заключение: {res.verdict_title}. {res.verdict_recommendation}",
        fontsize=9.0, color="#222222",
        transform=ax_header.transAxes, zorder=2,
        wrap=True,
    )

    # 2. СВОДНАЯ ТАБЛИЦА ПОКАЗАТЕЛЕЙ И КЛАССОВ РУТТНЕРА
    ax_table = fig.add_subplot(gs[1, :])
    ax_table.axis("off")
    ax_table.set_title(
        "Сводные биометрические показатели крыльев рабочей пчелы",
        fontsize=11, fontweight="bold", color="#2c5aa0", loc="left", pad=6,
    )

    rutt = res.ruttner
    rutt_str = (
        f"− : {rutt.get('minus', 0)} ({rutt.get('pct_minus', 0.0):.0f}%) / "
        f"0 : {rutt.get('zero', 0)} ({rutt.get('pct_zero', 0.0):.0f}%) / "
        f"+ : {rutt.get('plus', 0)} ({rutt.get('pct_plus', 0.0):.0f}%)"
    )

    eval_ranges = BREEDS.get(res.eval_breed or "", {})
    ci_std_str = f"{eval_ranges['CI'][0]:.2f} .. {eval_ranges['CI'][1]:.2f}" if "CI" in eval_ranges else "—"
    dsa_std_str = f"{eval_ranges['DsA'][0]:+.2f}° .. {eval_ranges['DsA'][1]:+.2f}°" if "DsA" in eval_ranges else "—"
    hi_std_str = f"{eval_ranges['HI'][0]:.3f} .. {eval_ranges['HI'][1]:.3f}" if "HI" in eval_ranges else "—"

    col_labels = [
        "Показатель",
        "Среднее ± ошибка",
        "СКО (σ)",
        "Разброс (Kvar)",
        "Мин .. Макс",
        "Стандарт породы",
        "Баллы (цел./гибр.)",
    ]
    table_rows = [
        [
            "Кубит. индекс (CI)",
            f"{res.ci.mean:.3f} ± {res.ci.sem:.3f}\n({res.alpatov_pct:.1f}% Алпатова)",
            f"{res.ci.std:.3f}",
            f"{res.ci.cv:.1f}%\n({res.ci_integrity})",
            f"{res.ci.min_val:.2f} .. {res.ci.max_val:.2f}",
            ci_std_str,
            f"+{res.ci_score} / +{res.ci_hyb_score}",
        ],
        [
            "Дискоид. смещение (DsA)",
            f"{res.dsa.mean:+.2f}° ± {res.dsa.sem:.2f}°",
            f"{res.dsa.std:.2f}°",
            f"Классы Руттнера:\n{rutt_str}",
            f"{res.dsa.min_val:+.2f}° .. {res.dsa.max_val:+.2f}°",
            dsa_std_str,
            f"— / +{res.dsa_hyb_score}",
        ],
        [
            "Гантельный индекс (HI)",
            f"{res.hi.mean:.3f} ± {res.hi.sem:.3f}",
            f"{res.hi.std:.3f}",
            f"{res.hi.cv:.1f}%\n({res.hi_integrity})",
            f"{res.hi.min_val:.3f} .. {res.hi.max_val:.3f}",
            hi_std_str,
            f"+{res.hi_score} / +{res.hi_hyb_score}",
        ],
    ]

    tbl = ax_table.table(
        cellText=table_rows,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
        bbox=[0.0, 0.0, 1.0, 0.90],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.0)
    for (row_i, col_i), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if row_i == 0:
            cell.set_facecolor("#e7f5ff")
            cell.set_text_props(weight="bold", color="#1864ab")
        elif row_i % 2 == 0:
            cell.set_facecolor("#f8f9fa")
        else:
            cell.set_facecolor("#ffffff")

    # 3. 2D-КАРТА ПОРОДНОСТИ (DsA vs CI и HI vs CI)
    ax_2d_dsa = fig.add_subplot(gs[2, 0:2])
    ax_2d_hi = fig.add_subplot(gs[2, 2])

    for b_key, b_ranges in BREEDS.items():
        color = BREED_COLORS_HEX.get(b_key, "#888888")
        short_ru = BREED_SHORT_NAMES_RU.get(b_key, b_key)
        dsa_lo, dsa_hi = b_ranges["DsA"]
        ci_lo, ci_hi = b_ranges["CI"]
        hi_lo, hi_hi = b_ranges["HI"]

        rect1 = Rectangle(
            (dsa_lo, ci_lo), dsa_hi - dsa_lo, ci_hi - ci_lo,
            facecolor=color, edgecolor=color, alpha=0.12, linewidth=1.2,
            label=short_ru, zorder=1,
        )
        ax_2d_dsa.add_patch(rect1)
        ax_2d_dsa.text(
            dsa_lo + 0.3, ci_hi - 0.12, short_ru,
            fontsize=7.5, color=color, fontweight="bold", alpha=0.85, zorder=2,
        )

        rect2 = Rectangle(
            (hi_lo, ci_lo), hi_hi - hi_lo, ci_hi - ci_lo,
            facecolor=color, edgecolor=color, alpha=0.12, linewidth=1.2,
            zorder=1,
        )
        ax_2d_hi.add_patch(rect2)

    if res.ci.values and res.dsa.values:
        in_set = set(res.wings_in_eval_breed)
        for w_num, ci_v, dsa_v, hi_v in zip(
            res.wing_numbers_valid, res.ci.values, res.dsa.values, res.hi.values
        ):
            ok = w_num in in_set
            pt_color = "#2b8a3e" if ok else "#e03131"
            ax_2d_dsa.scatter(dsa_v, ci_v, c=pt_color, s=26, edgecolors="white", linewidth=0.6, zorder=5)
            ax_2d_dsa.annotate(
                str(w_num), (dsa_v, ci_v),
                textcoords="offset points", xytext=(3, 2),
                fontsize=6.5, color="#222222", zorder=6,
            )
            ax_2d_hi.scatter(hi_v, ci_v, c=pt_color, s=22, edgecolors="white", linewidth=0.5, zorder=5)

        _draw_confidence_ellipse(ax_2d_dsa, res.dsa.values, res.ci.values, color="#d9480f")
        ax_2d_dsa.scatter(
            [res.dsa.mean], [res.ci.mean],
            c="#d9480f", marker="X", s=70, edgecolors="black", linewidth=0.8,
            label=f"Центр ({res.dsa.mean:+.1f}°, {res.ci.mean:.2f})", zorder=7,
        )
        _draw_confidence_ellipse(ax_2d_hi, res.hi.values, res.ci.values, color="#d9480f")
        ax_2d_hi.scatter(
            [res.hi.mean], [res.ci.mean],
            c="#d9480f", marker="X", s=60, edgecolors="black", linewidth=0.8, zorder=7,
        )

    ax_2d_dsa.axvline(0.0, color="#666666", linestyle=":", linewidth=1.0)
    ax_2d_dsa.set_title("2D-Карта породности: DsA (°) ↔ CI", fontsize=10, fontweight="bold", color="#222222")
    ax_2d_dsa.set_xlabel("Дискоидальное смещение DsA (°)", fontsize=8.5)
    ax_2d_dsa.set_ylabel("Кубитальный индекс CI", fontsize=8.5)
    ax_2d_dsa.set_xlim(-16.0, 13.5)
    ax_2d_dsa.set_ylim(0.7, 5.8)
    ax_2d_dsa.tick_params(labelsize=8)
    ax_2d_dsa.grid(True, linestyle="--", alpha=0.3)
    ax_2d_dsa.legend(loc="upper left", fontsize=7.0, ncol=2, framealpha=0.85)

    ax_2d_hi.set_title("Карта: HI ↔ CI", fontsize=10, fontweight="bold", color="#222222")
    ax_2d_hi.set_xlabel("Гантельный индекс HI", fontsize=8.5)
    ax_2d_hi.set_ylabel("CI", fontsize=8.5)
    ax_2d_hi.set_xlim(0.60, 1.45)
    ax_2d_hi.set_ylim(0.7, 5.8)
    ax_2d_hi.tick_params(labelsize=8)
    ax_2d_hi.grid(True, linestyle="--", alpha=0.3)

    # 4. ТРИ ГИСТОГРАММЫ РАСПРЕДЕЛЕНИЯ (CI, DsA, HI)
    hist_specs = [
        (gs[3, 0], res.ci.values, "Распределение CI", "CI", "#4dabf7", "CI"),
        (gs[3, 1], res.dsa.values, "Распределение DsA (°)", "Градусы", "#69db7c", "DsA"),
        (gs[3, 2], res.hi.values, "Распределение HI", "HI", "#ffa94d", "HI"),
    ]
    for subplot_spec, vals, h_title, xlabel, bar_color, idx_key in hist_specs:
        ax_h = fig.add_subplot(subplot_spec)
        if vals:
            bins_cnt = min(12, max(5, len(vals) // 2))
            ax_h.hist(vals, bins=bins_cnt, color=bar_color, edgecolor="#333333", alpha=0.75)
            mean_v = float(np.mean(vals))
            ax_h.axvline(mean_v, color="#d9480f", linestyle="--", linewidth=1.5, label=f"Ср.={mean_v:.2f}")
            if res.eval_breed and res.eval_breed in BREEDS:
                lo, hi_b = BREEDS[res.eval_breed][idx_key]
                ax_h.axvspan(lo, hi_b, color="#2b8a3e", alpha=0.15, label="Норма")
            ax_h.legend(fontsize=7.0, loc="upper right")
        else:
            ax_h.text(0.5, 0.5, "Нет данных", ha="center", va="center", transform=ax_h.transAxes)
        ax_h.set_title(h_title, fontsize=9.5, fontweight="bold")
        ax_h.set_xlabel(xlabel, fontsize=8.0)
        ax_h.set_ylabel("Крыльев", fontsize=8.0)
        ax_h.tick_params(labelsize=7.5)
        ax_h.grid(True, linestyle="--", alpha=0.3)

    # 5. ПОДВАЛ
    fig.text(
        0.5, 0.015,
        f"Создано в программе {APP_NAME} (NeuroWings) v{APP_VERSION} • {APP_TELEGRAM_LABEL}",
        ha="center", va="bottom", fontsize=8.5, color="#555555", style="italic",
    )

    fd, temp_pdf = tempfile.mkstemp(dir=target.parent, prefix=target.stem + "_", suffix=".pdf")
    os.close(fd)
    try:
        fig.savefig(temp_pdf, format="pdf", facecolor="#ffffff")
        plt.close(fig)
        os.replace(temp_pdf, target)
    finally:
        plt.close(fig)
        if os.path.exists(temp_pdf):
            os.unlink(temp_pdf)

    return target
