#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Единый доменный сервис морфометрического анализа пчелосемьи.

Устраняет дублирование математических формул между:
- AnalysisWidget (таблица анализа)
- BatchResultsWidget (сводная таблица по пасеке)
- InterpretationWidget / GlobalInterpretationWidget (экспертное заключение)
- PDF-Паспорт пчелосемьи (pdf_passport.py)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from .constants import (
    BREEDS, CLASSIC_BREEDS, BREED_NAMES_RU, format_breed_ru
)
from .calculations import (
    ci_to_alpatov,
    ci_to_alpatov_classic,
    calculate_breed_probability,
    calculate_hybridization_score,
    calculate_ruttner_classes,
    calculate_breed_distance,
)
from .data_models import Wing, ImageData


HYBRIDIZATION_LABELS = {
    3: "отсутствует",
    2: "несущественная",
    1: "допустимая",
    0: "ГИБРИД",
}


@dataclass
class IndexStats:
    """Статистика по одному морфометрическому индексу."""
    values: List[float] = field(default_factory=list)
    mean: float = 0.0
    std: float = 0.0
    sem: float = 0.0
    cv: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0


@dataclass
class ColonyAnalysisResult:
    """Полный результат морфометрического анализа пробы пчелосемьи."""
    total_wings_all: int = 0
    disabled_wings_count: int = 0
    total: int = 0  # Число активных (включённых в расчёт) крыльев
    valid_count: int = 0
    identified: int = 0
    not_identified: int = 0
    id_wings_pct: float = 0.0
    not_id_pct: float = 0.0

    ci: IndexStats = field(default_factory=IndexStats)
    dsa: IndexStats = field(default_factory=IndexStats)
    hi: IndexStats = field(default_factory=IndexStats)
    alpatov: IndexStats = field(default_factory=IndexStats)
    alpatov_pct: float = 0.0
    alpatov_classic_pct: float = 0.0

    breed_counts: Dict[str, int] = field(default_factory=dict)
    breed_probabilities: Dict[str, float] = field(default_factory=dict)
    breed_distances: Dict[str, float] = field(default_factory=dict)

    dominant_breed: Optional[str] = None
    dominant_breed_str: str = "—"
    dominant_breed_ru: str = "Помесь / Бакфаст (вне стандарта)"
    closest_breed: Optional[str] = None
    eval_breed: Optional[str] = None
    eval_breed_ru: str = "Помесь / Бакфаст (вне стандарта)"

    breed_match_pct: float = 0.0
    penalty_not_id: int = 0
    breed_score: int = 0
    ci_integrity: str = "не обеспечена"
    ci_score: int = 0
    dsa_integrity: str = "не оценивается (среднее около 0°)"
    hi_integrity: str = "не обеспечена"
    hi_score: int = 0

    ci_hyb_score: int = 0
    ci_hybrid: str = "ГИБРИД"
    dsa_hyb_score: int = 0
    dsa_hybrid: str = "ГИБРИД"
    hi_hyb_score: int = 0
    hi_hybrid: str = "ГИБРИД"

    total_score: int = 0
    max_possible_score: int = 17
    verdict_title: str = "Нет данных"
    verdict_recommendation: str = ""
    verdict_level: str = "neutral"  # 'elite', 'good', 'warn', 'bad', 'neutral'

    ruttner: Dict[str, float] = field(default_factory=dict)
    wing_numbers_valid: List[int] = field(default_factory=list)
    wings_in_eval_breed: List[int] = field(default_factory=list)
    wings_out_of_eval_breed: List[int] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, object]:
        """Словарь для сохранения в ImageData.analysis_results."""
        return {
            "total": self.total,
            "total_all": self.total_wings_all,
            "disabled_count": self.disabled_wings_count,
            "identified": self.identified,
            "breed_match_pct": self.breed_match_pct,
            "mean_ci": self.ci.mean,
            "std_ci": self.ci.std,
            "cv_ci": self.ci.cv,
            "alpatov_pct": self.alpatov_pct,
            "mean_dsa": self.dsa.mean,
            "std_dsa": self.dsa.std,
            "cv_dsa": self.dsa.cv,
            "mean_hi": self.hi.mean,
            "std_hi": self.hi.std,
            "cv_hi": self.hi.cv,
            "breed": self.dominant_breed_str,
            "breed_ru": self.dominant_breed_ru,
            "eval_breed": self.eval_breed or "—",
            "eval_breed_ru": self.eval_breed_ru,
            "score": self.total_score,
            "verdict_title": self.verdict_title,
            "verdict_recommendation": self.verdict_recommendation,
        }


def _compute_index_stats(values: List[float], abs_mean_for_cv: bool = True) -> IndexStats:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not clean:
        return IndexStats()
    mean = float(np.mean(clean))
    std = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    sem = float(std / math.sqrt(len(clean))) if clean else 0.0
    denom = abs(mean) if abs_mean_for_cv else mean
    # В Excel (Карташев в. 2.5, лист «Индексы» строки 103–104):
    # СКО = ROUND(STDEV(...), 3), Квар = ROUND(СКО / МО, 3) * 100%
    std_rounded = round(std, 3)
    cv = float(round(abs(std_rounded / denom), 3) * 100.0) if denom != 0 else 0.0
    return IndexStats(
        values=clean,
        mean=mean,
        std=std,
        sem=sem,
        cv=cv,
        min_val=float(min(clean)),
        max_val=float(max(clean)),
    )


def _excel_roundup_score(id_pct: float) -> int:
    """Баллы за вероятность соответствия породе по формуле Excel: 5 + ROUNDUP((P - 100%)/10%)."""
    diff = (float(id_pct) - 100.0) / 10.0
    if diff >= 0:
        roundup_value = int(math.ceil(diff))
    else:
        roundup_value = int(math.floor(diff))
    return max(0, 5 + roundup_value)


def _build_verdict(
    score: int,
    eval_breed_ru: str,
    total: int,
    identified: int,
    mating_mode: str = "purebred",
    means_in_expanded_breed: bool = False,
) -> Tuple[str, str, str]:
    is_free = (mating_mode == "free_mated")
    mode_tag = " (режим: свободноспаренная матка)" if is_free else ""
    if total == 0:
        return ("Нет активных крыльев для расчёта", "Включите крылья в таблице или распознайте скан.", "neutral")
    if identified == 0 and not (is_free and means_in_expanded_breed):
        return (
            f"Помесь / вне чистопородного стандарта{mode_tag}",
            "Ни одно крыло не попало в эталонные границы чистых пород (возможен сложный гибрид или Бакфаст). Использовать как пользовательную семью на мёд.",
            "bad",
        )
    if score >= 17:
        return (
            f"Элита породы: {eval_breed_ru}{mode_tag}",
            "Эталонная чистопородная семья (17 баллов). Рекомендуется как родоначальница линии и для племенного вывода маток.",
            "elite",
        )
    if score >= 15:
        return (
            f"Чистопородная семья: {eval_breed_ru}{mode_tag}",
            "Отличное качество семьи (15–16 баллов). Полностью подходит для репродукции и вывода племенных маток.",
            "good",
        )
    if is_free and score >= 11 and means_in_expanded_breed:
        return (
            f"Чистопородная свободноспаренная семья: {eval_breed_ru}{mode_tag}",
            "Хорошее соответствие породе для свободноспаренной матки (≥11 баллов, средние индексы в допустимом диапазоне ±15%). Пригодна как пользовательная чистопородная семья и для работы на пасеке.",
            "good",
        )
    if score >= 10:
        return (
            f"Хорошая семья ({eval_breed_ru}) — пригодна для селекции{mode_tag}",
            "Хорошая породность (10–14 баллов), имеется небольшая неоднородность или следы примеси. Подходит для селекционной работы и контроля трутневого фона.",
            "warn",
        )
    if score >= 5:
        return (
            f"Пользовательная семья ({eval_breed_ru} с примесью){mode_tag}",
            "Заметная гибридизация (5–9 баллов). Семья пригодна для товарного медосбора («для себя»), но не рекомендуется для вывода маток.",
            "warn",
        )
    return (
        f"Сильная метизация / гибридная семья{mode_tag}",
        "Низкий балл чистопородности (< 5 баллов). Высокий разброс признаков; рекомендуется плановая замена матки на чистопородную.",
        "bad",
    )


class ColonyAnalysisService:
    """Сервис расчёта статистики и породной оценки пчелосемьи."""

    @staticmethod
    def analyze_wings(
        wings: List[Wing],
        target_breed: Optional[str] = None,
        mating_mode: str = "purebred",
    ) -> ColonyAnalysisResult:
        res = ColonyAnalysisResult()
        if not wings:
            return res

        is_free = (mating_mode == "free_mated")
        res.total_wings_all = len(wings)
        active_entries: List[Tuple[int, Wing]] = [
            (idx + 1, w) for idx, w in enumerate(wings) if getattr(w, "is_enabled", True)
        ]
        res.disabled_wings_count = res.total_wings_all - len(active_entries)
        res.total = len(active_entries)

        if res.total == 0:
            res.verdict_title, res.verdict_recommendation, res.verdict_level = _build_verdict(
                0, "—", 0, 0, mating_mode=mating_mode
            )
            return res

        ci_values: List[float] = []
        dsa_values: List[float] = []
        hi_values: List[float] = []
        alpatov_values: List[float] = []
        valid_numbers: List[int] = []

        for wing_num, w in active_entries:
            if w.analysis and w.analysis.is_valid:
                valid_numbers.append(wing_num)
                if w.analysis.CI > 0:
                    ci_values.append(float(w.analysis.CI))
                    alpatov_values.append(ci_to_alpatov(w.analysis.CI) * 100.0)
                dsa_values.append(float(w.analysis.DsA))
                if w.analysis.HI > 0:
                    hi_values.append(float(w.analysis.HI))

        res.valid_count = len(valid_numbers)
        res.wing_numbers_valid = valid_numbers

        # В эталонной программе Карташева (в. 2.5) идентифицированными считаются крылья,
        # попавшие хотя бы в одну из 4 классических пород Руттнера (CLASSIC_BREEDS).
        # Если пользователь явно выбрал региональный экотип (Carpatica/Ukrainian/FarEast)
        # или ни одно крыло не попало в CLASSIC_BREEDS, учитываем расширенный справочник.
        classic_identified = sum(
            1 for _, w in active_entries
            if w.analysis and w.analysis.breeds and any(b in CLASSIC_BREEDS for b in w.analysis.breeds)
        )
        all_identified = sum(1 for _, w in active_entries if w.analysis and w.analysis.is_identified)
        if target_breed and target_breed not in ("auto",) and target_breed not in CLASSIC_BREEDS:
            res.identified = all_identified
        else:
            res.identified = classic_identified if classic_identified > 0 else all_identified
        res.not_identified = res.total - res.identified
        res.id_wings_pct = 100.0 * res.identified / res.total if res.total > 0 else 0.0
        res.not_id_pct = 100.0 * res.not_identified / res.total if res.total > 0 else 0.0

        res.ci = _compute_index_stats(ci_values)
        res.dsa = _compute_index_stats(dsa_values)
        res.hi = _compute_index_stats(hi_values)
        res.alpatov = _compute_index_stats(alpatov_values)
        res.alpatov_pct = res.alpatov.mean
        res.alpatov_classic_pct = ci_to_alpatov_classic(res.ci.mean)
        res.ruttner = calculate_ruttner_classes(dsa_values)

        # Подсчёт числа крыльев по всем породам справочника
        breed_counts: Dict[str, int] = {b: 0 for b in BREEDS}
        for _, w in active_entries:
            if w.analysis and w.analysis.breeds:
                for b in w.analysis.breeds:
                    if b in breed_counts:
                        breed_counts[b] += 1
        res.breed_counts = breed_counts

        # Вероятность соответствия породе — по ВСЕМ валидным активным крыльям пробы (без selection bias!)
        breed_probabilities: Dict[str, float] = {}
        breed_distances: Dict[str, float] = {}
        for breed_name in BREEDS:
            if ci_values and dsa_values and hi_values:
                prob = calculate_breed_probability(ci_values, dsa_values, hi_values, breed_name)
                dist_val = calculate_breed_distance(res.ci.mean, res.dsa.mean, res.hi.mean, breed_name)
            else:
                prob = 0.0
                dist_val = float("inf")
            breed_probabilities[breed_name] = prob
            breed_distances[breed_name] = dist_val

        res.breed_probabilities = breed_probabilities
        res.breed_distances = breed_distances

        if breed_distances:
            res.closest_breed = min(breed_distances, key=breed_distances.get)

        # Выбор преобладающей породы:
        # Сначала смотрим классические 4 породы (для 100% обратной совместимости с тестами и Excel),
        # но ТОЛЬКО если есть хотя бы 1 идентифицированное крыло!
        classic_max = max(CLASSIC_BREEDS, key=lambda b: (breed_counts.get(b, 0), breed_probabilities.get(b, 0.0)))
        all_max = max(BREEDS.keys(), key=lambda b: (breed_counts.get(b, 0), breed_probabilities.get(b, 0.0)))

        if res.identified > 0 and breed_counts.get(classic_max, 0) > 0:
            res.dominant_breed = classic_max
            res.dominant_breed_str = classic_max
            res.dominant_breed_ru = format_breed_ru(classic_max)
        elif res.identified > 0 and breed_counts.get(all_max, 0) > 0:
            res.dominant_breed = all_max
            res.dominant_breed_str = all_max
            res.dominant_breed_ru = format_breed_ru(all_max)
        else:
            res.dominant_breed = None
            res.dominant_breed_str = "—"
            res.dominant_breed_ru = format_breed_ru(None)

        # Определяем целевую породу для оценки (eval_breed)
        if target_breed and target_breed != "auto" and target_breed in BREEDS:
            res.eval_breed = target_breed
        else:
            res.eval_breed = res.dominant_breed

        res.eval_breed_ru = format_breed_ru(res.eval_breed)

        # Какие крылья укладываются в стандарт целевой породы (eval_breed)
        means_in_expanded_breed = False
        if res.eval_breed and res.eval_breed in BREEDS:
            br = BREEDS[res.eval_breed]
            exp_factor = 0.15 if is_free else 0.0
            ci_lo, ci_hi = br["CI"]
            ci_exp = exp_factor * (ci_hi - ci_lo)
            dsa_lo, dsa_hi = br["DsA"]
            dsa_exp = exp_factor * (dsa_hi - dsa_lo)
            hi_lo, hi_hi = br["HI"]
            hi_exp = exp_factor * (hi_hi - hi_lo)

            for wing_num, w in active_entries:
                if not w.analysis or not w.analysis.is_valid:
                    res.wings_out_of_eval_breed.append(wing_num)
                    continue
                ci_ok = (ci_lo - ci_exp) <= w.analysis.CI <= (ci_hi + ci_exp)
                dsa_ok = (dsa_lo - dsa_exp) <= w.analysis.DsA <= (dsa_hi + dsa_exp)
                hi_ok = (hi_lo - hi_exp) <= w.analysis.HI <= (hi_hi + hi_exp)
                if ci_ok and dsa_ok and hi_ok:
                    res.wings_in_eval_breed.append(wing_num)
                else:
                    res.wings_out_of_eval_breed.append(wing_num)

            if ci_values and dsa_values and hi_values:
                means_in_expanded_breed = (
                    (ci_lo - ci_exp) <= res.ci.mean <= (ci_hi + ci_exp)
                    and (dsa_lo - dsa_exp) <= res.dsa.mean <= (dsa_hi + dsa_exp)
                    and (hi_lo - hi_exp) <= res.hi.mean <= (hi_hi + hi_exp)
                )
        else:
            for wing_num, w in active_entries:
                if w.analysis and w.analysis.is_identified:
                    res.wings_in_eval_breed.append(wing_num)
                else:
                    res.wings_out_of_eval_breed.append(wing_num)

        # 1. Штраф за неидентифицированные крылья:
        # В Excel Карташева (лист «Анализ» строка 4): «За каждые 5% (после округления) начисляется "-1"»
        res.penalty_not_id = -int(math.floor(res.not_id_pct / 5.0 + 0.5)) if res.total > 0 else 0

        # 2. Вероятностная оценка и баллы (0..5)
        if res.eval_breed and res.eval_breed in breed_probabilities:
            res.breed_match_pct = breed_probabilities[res.eval_breed] * 100.0
            res.breed_score = _excel_roundup_score(res.breed_match_pct)
        else:
            res.breed_match_pct = 0.0
            res.breed_score = 0

        cv_scale = 1.15 if is_free else 1.0

        # 3. Целостность семьи по CI (0..2)
        if not ci_values:
            res.ci_integrity = "нет данных"
            res.ci_score = 0
        elif res.ci.cv < 12.5 * cv_scale:
            res.ci_integrity = "идеальная"
            res.ci_score = 2
        elif res.ci.cv <= 20.0 * cv_scale:
            res.ci_integrity = "нормальная"
            res.ci_score = 1
        else:
            res.ci_integrity = "не обеспечена"
            res.ci_score = 0

        # 4. Целостность семьи по DsA (информативно, без баллов)
        if not dsa_values or abs(res.dsa.mean) < 0.5:
            res.dsa_integrity = "не оценивается (среднее около 0°)"
        elif res.dsa.cv < 50.0 * cv_scale:
            res.dsa_integrity = "нормальная"
        else:
            res.dsa_integrity = "не обеспечена"

        # 5. Целостность семьи по HI (0..2)
        if not hi_values:
            res.hi_integrity = "нет данных"
            res.hi_score = 0
        elif res.hi.cv < 6.5 * cv_scale:
            res.hi_integrity = "идеальная"
            res.hi_score = 2
        elif res.hi.cv <= 7.5 * cv_scale:
            res.hi_integrity = "нормальная"
            res.hi_score = 1
        else:
            res.hi_integrity = "не обеспечена"
            res.hi_score = 0

        # 6. Гибридизация по CI, DsA, HI (по 0..3 балла, но ТОЛЬКО если порода определена!)
        if res.eval_breed and res.eval_breed in BREEDS:
            res.ci_hyb_score = calculate_hybridization_score(ci_values, res.eval_breed, "CI", mating_mode=mating_mode)
            res.dsa_hyb_score = calculate_hybridization_score(dsa_values, res.eval_breed, "DsA", mating_mode=mating_mode)
            res.hi_hyb_score = calculate_hybridization_score(hi_values, res.eval_breed, "HI", mating_mode=mating_mode)
        else:
            res.ci_hyb_score = 0
            res.dsa_hyb_score = 0
            res.hi_hyb_score = 0

        res.ci_hybrid = HYBRIDIZATION_LABELS.get(res.ci_hyb_score, "ГИБРИД")
        res.dsa_hybrid = HYBRIDIZATION_LABELS.get(res.dsa_hyb_score, "ГИБРИД")
        res.hi_hybrid = HYBRIDIZATION_LABELS.get(res.hi_hyb_score, "ГИБРИД")

        # 7. Итого баллов (максимум по шкале 17 баллов)
        res.total_score = min(
            17,
            res.penalty_not_id
            + res.breed_score
            + res.ci_score
            + res.hi_score
            + res.ci_hyb_score
            + res.dsa_hyb_score
            + res.hi_hyb_score,
        )

        res.verdict_title, res.verdict_recommendation, res.verdict_level = _build_verdict(
            res.total_score,
            res.eval_breed_ru,
            res.total,
            res.identified if not (target_breed and target_breed in BREEDS) else len(res.wings_in_eval_breed),
            mating_mode=mating_mode,
            means_in_expanded_breed=means_in_expanded_breed,
        )
        return res

    @staticmethod
    def analyze_image(
        image_data: ImageData,
        target_breed: Optional[str] = None,
        reanalyze_wings: bool = True,
        mating_mode: str = "purebred",
    ) -> ColonyAnalysisResult:
        if not image_data or not image_data.wings:
            return ColonyAnalysisResult()
        if reanalyze_wings and hasattr(image_data, "analyze_all_wings"):
            image_data.analyze_all_wings()
        result = ColonyAnalysisService.analyze_wings(
            image_data.wings, target_breed=target_breed, mating_mode=mating_mode
        )
        if hasattr(image_data, "analysis_results") and isinstance(image_data.analysis_results, dict):
            image_data.analysis_results.update(result.to_summary_dict())
        return result


def analyze_colony(
    wings_or_image,
    target_breed: Optional[str] = None,
    reanalyze_wings: bool = True,
    mating_mode: str = "purebred",
) -> ColonyAnalysisResult:
    """Удобная функция-фасад для расчёта статистики семьи по ImageData или списку Wing."""
    if isinstance(wings_or_image, list):
        return ColonyAnalysisService.analyze_wings(
            wings_or_image, target_breed=target_breed, mating_mode=mating_mode
        )
    return ColonyAnalysisService.analyze_image(
        wings_or_image,
        target_breed=target_breed,
        reanalyze_wings=reanalyze_wings,
        mating_mode=mating_mode,
    )


CI_BINS: List[float] = [
    0.71, 0.76, 0.81, 0.87, 0.93, 1.0, 1.07, 1.14, 1.22, 1.31,
    1.4, 1.5, 1.61, 1.73, 1.86, 2.0, 2.16, 2.33, 2.53, 2.75,
    3.0, 3.29, 3.62, 4.0, 4.45, 5.0, 5.67, 6.5, 7.57, 9.0, 10.5,
]
DSA_BINS: List[float] = [
    -16.29, -15.31, -14.33, -13.36, -12.39, -11.42, -10.46, -9.5, -8.54, -7.59,
    -6.63, -5.68, -4.73, -3.78, -2.84, -1.89, -0.95, 0.0, 0.95, 1.89,
    2.84, 3.78, 4.73, 5.68, 6.63, 7.59, 8.54, 9.5, 10.46, 11.42, 12.39,
]
HI_BINS: List[float] = [
    0.6, 0.616, 0.63, 0.648, 0.666, 0.685, 0.704, 0.724, 0.744, 0.765,
    0.786, 0.807, 0.829, 0.852, 0.875, 0.899, 0.923, 0.948, 0.974, 1.0,
    1.027, 1.053, 1.083, 1.113, 1.143, 1.174, 1.206, 1.239, 1.272, 1.308,
    1.344, 1.381, 1.42,
]


def find_best_bees(
    wings: List[Wing],
    peak_width: int = 2,
) -> List[int]:
    """Определить «лучших пчёл» семьи 1:1 по алгоритму Карташёва (Лучшая пчела.xlsm, лист «База» + Макрос2).

    Тройная фильтрация по пикам графиков CI → DsA → HI:
    1) По всей пробе семьи через FREQUENCY(vals, bins) находится пиковая корзина m (в первых 31 корзинах)
       для каждого из трёх индексов (CI, DsA, HI).
    2) Границы отбора для ширины пика pw (1, 2 или 3):
       low_idx = max(0, m - 1 - (1 if pw == 3 else 0)) -> v_min_bound = bins[low_idx]
       high_idx = min(len(bins) - 1, m + (1 if pw > 1 else 0)) -> v_max_bound = bins[high_idx]
    3) Крыло проходит фильтр по индексу, если v_min_bound <= round(val, 3) <= v_max_bound.
    4) Если при текущем peak_width после 3 фильтров получилось 0 крыльев и peak_width < 3,
       автоматически пробуется peak_width + 1 (вплоть до 3).

    Args:
        wings: Список крыльев семьи (Wing).
        peak_width: Ширина пика (по умолчанию 2; 1 = узкий пик, 2 = стандарт, 3 = широкий).
    Returns:
        Список 0-based индексов «лучших» крыльев.
    """
    if not wings:
        return []

    # Собираем валидные крылья с индексами
    entries = []
    for idx, w in enumerate(wings):
        if not getattr(w, 'is_enabled', True):
            continue
        if not (w.analysis and w.analysis.is_valid and w.analysis.CI > 0 and w.analysis.HI > 0):
            continue
        entries.append((idx, float(w.analysis.CI), float(w.analysis.DsA), float(w.analysis.HI)))

    if not entries:
        return []

    def _excel_frequency_peak(vals: List[float], bins: List[float]) -> int:
        """Аналог FREQUENCY(vals, bins) в Excel и поиск первого максимума в первых 31 корзинах."""
        counts = [0] * len(bins)
        for val in vals:
            for i, b in enumerate(bins):
                if i == 0:
                    if val <= b + 1e-9:
                        counts[0] += 1
                        break
                else:
                    if bins[i - 1] + 1e-9 < val <= b + 1e-9:
                        counts[i] += 1
                        break
        first_31 = counts[:31]
        max_cnt = max(first_31) if first_31 else 0
        return first_31.index(max_cnt) if max_cnt > 0 else 0

    def _peak_bounds(m: int, bins: List[float], pw: int) -> Tuple[float, float]:
        low_idx = max(0, m - 1 - (1 if pw == 3 else 0))
        high_idx = min(len(bins) - 1, m + (1 if pw > 1 else 0))
        return bins[low_idx], bins[high_idx]

    ci_all = [it[1] for it in entries]
    dsa_all = [it[2] for it in entries]
    hi_all = [it[3] for it in entries]

    m_ci = _excel_frequency_peak(ci_all, CI_BINS)
    m_dsa = _excel_frequency_peak(dsa_all, DSA_BINS)
    m_hi = _excel_frequency_peak(hi_all, HI_BINS)

    pw_start = max(1, min(3, int(peak_width)))
    for pw in range(pw_start, 4):
        ci_min, ci_max = _peak_bounds(m_ci, CI_BINS, pw)
        dsa_min, dsa_max = _peak_bounds(m_dsa, DSA_BINS, pw)
        hi_min, hi_max = _peak_bounds(m_hi, HI_BINS, pw)

        step1 = [it for it in entries if ci_min - 1e-9 <= round(it[1], 3) <= ci_max + 1e-9]
        step2 = [it for it in step1 if dsa_min - 1e-9 <= round(it[2], 3) <= dsa_max + 1e-9]
        step3 = [it for it in step2 if hi_min - 1e-9 <= round(it[3], 3) <= hi_max + 1e-9]
        if step3:
            return sorted([it[0] for it in step3])

    return []
