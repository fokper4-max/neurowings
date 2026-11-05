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


def _build_verdict(score: int, eval_breed_ru: str, total: int, identified: int) -> Tuple[str, str, str]:
    if total == 0:
        return ("Нет активных крыльев для расчёта", "Включите крылья в таблице или распознайте скан.", "neutral")
    if identified == 0:
        return (
            "Помесь / вне чистопородного стандарта",
            "Ни одно крыло не попало в эталонные границы чистых пород (возможен сложный гибрид или Бакфаст). Использовать как пользовательную семью на мёд.",
            "bad",
        )
    if score >= 17:
        return (
            f"Элита породы: {eval_breed_ru}",
            "Эталонная чистопородная семья (17 баллов). Рекомендуется как родоначальница линии и для племенного вывода маток.",
            "elite",
        )
    if score >= 15:
        return (
            f"Чистопородная семья: {eval_breed_ru}",
            "Отличное качество семьи (15–16 баллов). Полностью подходит для репродукции и вывода племенных маток.",
            "good",
        )
    if score >= 10:
        return (
            f"Хорошая семья ({eval_breed_ru}) — пригодна для селекции",
            "Хорошая породность (10–14 баллов), имеется небольшая неоднородность или следы примеси. Подходит для селекционной работы и контроля трутневого фона.",
            "warn",
        )
    if score >= 5:
        return (
            f"Пользовательная семья ({eval_breed_ru} с примесью)",
            "Заметная гибридизация (5–9 баллов). Семья пригодна для товарного медосбора («для себя»), но не рекомендуется для вывода маток.",
            "warn",
        )
    return (
        "Сильная метизация / гибридная семья",
        "Низкий балл чистопородности (< 5 баллов). Высокий разброс признаков; рекомендуется плановая замена матки на чистопородную.",
        "bad",
    )


class ColonyAnalysisService:
    """Сервис расчёта статистики и породной оценки пчелосемьи."""

    @staticmethod
    def analyze_wings(
        wings: List[Wing],
        target_breed: Optional[str] = None,
    ) -> ColonyAnalysisResult:
        res = ColonyAnalysisResult()
        if not wings:
            return res

        res.total_wings_all = len(wings)
        active_entries: List[Tuple[int, Wing]] = [
            (idx + 1, w) for idx, w in enumerate(wings) if getattr(w, "is_enabled", True)
        ]
        res.disabled_wings_count = res.total_wings_all - len(active_entries)
        res.total = len(active_entries)

        if res.total == 0:
            res.verdict_title, res.verdict_recommendation, res.verdict_level = _build_verdict(0, "—", 0, 0)
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
        if res.eval_breed and res.eval_breed in BREEDS:
            br = BREEDS[res.eval_breed]
            for wing_num, w in active_entries:
                if not w.analysis or not w.analysis.is_valid:
                    res.wings_out_of_eval_breed.append(wing_num)
                    continue
                ci_ok = br["CI"][0] <= w.analysis.CI <= br["CI"][1]
                dsa_ok = br["DsA"][0] <= w.analysis.DsA <= br["DsA"][1]
                hi_ok = br["HI"][0] <= w.analysis.HI <= br["HI"][1]
                if ci_ok and dsa_ok and hi_ok:
                    res.wings_in_eval_breed.append(wing_num)
                else:
                    res.wings_out_of_eval_breed.append(wing_num)
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

        # 3. Целостность семьи по CI (0..2)
        if not ci_values:
            res.ci_integrity = "нет данных"
            res.ci_score = 0
        elif res.ci.cv < 12.5:
            res.ci_integrity = "идеальная"
            res.ci_score = 2
        elif res.ci.cv <= 20.0:
            res.ci_integrity = "нормальная"
            res.ci_score = 1
        else:
            res.ci_integrity = "не обеспечена"
            res.ci_score = 0

        # 4. Целостность семьи по DsA (информативно, без баллов)
        if not dsa_values or abs(res.dsa.mean) < 0.5:
            res.dsa_integrity = "не оценивается (среднее около 0°)"
        elif res.dsa.cv < 50.0:
            res.dsa_integrity = "нормальная"
        else:
            res.dsa_integrity = "не обеспечена"

        # 5. Целостность семьи по HI (0..2)
        if not hi_values:
            res.hi_integrity = "нет данных"
            res.hi_score = 0
        elif res.hi.cv < 6.5:
            res.hi_integrity = "идеальная"
            res.hi_score = 2
        elif res.hi.cv <= 7.5:
            res.hi_integrity = "нормальная"
            res.hi_score = 1
        else:
            res.hi_integrity = "не обеспечена"
            res.hi_score = 0

        # 6. Гибридизация по CI, DsA, HI (по 0..3 балла, но ТОЛЬКО если порода определена!)
        if res.eval_breed and res.eval_breed in BREEDS:
            res.ci_hyb_score = calculate_hybridization_score(ci_values, res.eval_breed, "CI")
            res.dsa_hyb_score = calculate_hybridization_score(dsa_values, res.eval_breed, "DsA")
            res.hi_hyb_score = calculate_hybridization_score(hi_values, res.eval_breed, "HI")
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
        )
        return res

    @staticmethod
    def analyze_image(
        image_data: ImageData,
        target_breed: Optional[str] = None,
        reanalyze_wings: bool = True,
    ) -> ColonyAnalysisResult:
        if not image_data or not image_data.wings:
            return ColonyAnalysisResult()
        if reanalyze_wings and hasattr(image_data, "analyze_all_wings"):
            image_data.analyze_all_wings()
        result = ColonyAnalysisService.analyze_wings(image_data.wings, target_breed=target_breed)
        if hasattr(image_data, "analysis_results") and isinstance(image_data.analysis_results, dict):
            image_data.analysis_results.update(result.to_summary_dict())
        return result


def analyze_colony(
    wings_or_image,
    target_breed: Optional[str] = None,
    reanalyze_wings: bool = True,
) -> ColonyAnalysisResult:
    """Удобная функция-фасад для расчёта статистики семьи по ImageData или списку Wing."""
    if isinstance(wings_or_image, list):
        return ColonyAnalysisService.analyze_wings(wings_or_image, target_breed=target_breed)
    return ColonyAnalysisService.analyze_image(
        wings_or_image, target_breed=target_breed, reanalyze_wings=reanalyze_wings
    )


def find_best_bees(
    wings: List[Wing],
    peak_width: int = 1,
) -> List[int]:
    """Определить «лучших пчёл» семьи по алгоритму Карташёва (Лучшая пчела.xlsm).

    Тройная фильтрация по пикам графиков CI → DsA → HI:
    1) Все крылья сортируются по CI, выделяется группа класса с максимальным числом крыльев (±peak_width классов).
    2) Из выделенных крыльев — аналогичная фильтрация по DsA.
    3) Из оставшихся — фильтрация по HI.
    Возвращает список индексов крыльев (0-based), прошедших все три фильтра.

    Args:
        wings: Список крыльев семьи (Wing).
        peak_width: Ширина пика (1 = один класс, 2 = два соседних, 3 = три).
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

    def _filter_by_peak(items, value_idx, peak_w):
        """Фильтровать по пику: найти класс с максимальным числом значений."""
        if not items:
            return items
        vals = [it[value_idx] for it in items]
        v_min, v_max = min(vals), max(vals)
        if v_max - v_min < 1e-9:
            return items  # все одинаковые
        # 31 класс (как у Карташёва)
        n_classes = 31
        bin_width = (v_max - v_min) / n_classes
        if bin_width < 1e-12:
            return items

        # Распределяем по классам
        class_counts = [0] * n_classes
        class_members = [[] for _ in range(n_classes)]
        for it in items:
            v = it[value_idx]
            c = min(int((v - v_min) / bin_width), n_classes - 1)
            class_counts[c] += 1
            class_members[c].append(it)

        # Находим класс-пик
        peak_class = max(range(n_classes), key=lambda c: class_counts[c])

        # Собираем крылья из пика ± peak_width
        half = peak_w - 1  # peak_width=1 → только пик, 2 → пик+1, 3 → пик±1
        result = []
        for c in range(max(0, peak_class - half), min(n_classes, peak_class + half + 1)):
            result.extend(class_members[c])
        return result if result else items

    # Тройная фильтрация
    step1 = _filter_by_peak(entries, 1, peak_width)   # по CI
    step2 = _filter_by_peak(step1, 2, peak_width)     # по DsA
    step3 = _filter_by_peak(step2, 3, peak_width)     # по HI

    return sorted([it[0] for it in step3])
