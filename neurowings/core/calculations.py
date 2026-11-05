#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Расчёт морфометрических индексов (правильно как в NeuroWings_v1_8_1 + Excel)

Проверено на 58 WD.tps (первые 8 точек):
  CI=1.896427073094
  HI=0.751669046973
  DsA=-0.728874236276   <- ПРАВИЛЬНО (как в 58.xlsm)

ВАЖНО:
- calculate_dsa_excel() возвращает (DsA, proj), где proj = (x,y) — проекция P3 на линию P1-P2.
- Это именно тот формат, который UI использует для отрисовки "дискоидального" (линия P3->proj).
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional
import numpy as np
import math
import logging

from .constants import BREEDS, INDEX_POINTS

logger = logging.getLogger("NeuroWings")

Point = Tuple[float, float]


def dist(p1: Point, p2: Point) -> float:
    """Вычислить евклидово расстояние между двумя точками"""
    if p1 is None or p2 is None:
        logger.warning("Попытка вычислить расстояние для None точки")
        return 0.0
    try:
        return float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
    except (TypeError, IndexError) as e:
        logger.error(f"Ошибка при вычислении расстояния: {e}")
        return 0.0


def project_point_to_line(p: Point, a: Point, b: Point) -> Point:
    """Проекция точки p на прямую через a->b"""
    if p is None or a is None or b is None:
        logger.warning("Попытка проекции с None точкой")
        return (0.0, 0.0)

    try:
        ax, ay = a
        bx, by = b
        px, py = p

        vx = bx - ax
        vy = by - ay
        vv = vx * vx + vy * vy
        if vv < 1e-12:
            logger.debug("Вырожденная линия при проекции (точки a и b совпадают)")
            return (0.0, 0.0)

        t = ((px - ax) * vx + (py - ay) * vy) / vv
        return (ax + t * vx, ay + t * vy)
    except (TypeError, ValueError) as e:
        logger.error(f"Ошибка при проекции точки: {e}")
        return (0.0, 0.0)


def calculate_dsa_excel(points: List[Point]) -> Tuple[float, Point]:
    """
    DsA по Excel-формуле:

      proj = proj(P3 на P1-P2)
      K2 = (projY - P3Y) / (projX - P3X)
      K3 = (projY - P8Y) / (projX - P8X)
      DsA = -deg(atan((K2-K3)/(1+K3*K2)))

    Точки (8 шт): P1..P8 в порядке 1..8.
    """
    if not isinstance(points, (list, tuple)) or len(points) != 8:
        return 0.0, (0.0, 0.0)

    p1, p2, p3, p4, p5, p6, p7, p8 = points

    proj = project_point_to_line(p3, p1, p2)

    dx_p3 = proj[0] - p3[0]
    dy_p3 = proj[1] - p3[1]
    dx_p8 = proj[0] - p8[0]
    dy_p8 = proj[1] - p8[1]

    if abs(dx_p3) < 1e-10:
        K2 = 1e10 if dy_p3 > 0 else -1e10
    else:
        K2 = dy_p3 / dx_p3

    if abs(dx_p8) < 1e-10:
        K3 = 1e10 if dy_p8 > 0 else -1e10
    else:
        K3 = dy_p8 / dx_p8

    denominator = 1 + K3 * K2
    if abs(denominator) < 1e-10:
        DsA = 90.0 if (K2 - K3) > 0 else -90.0
    else:
        DsA = -float(np.degrees(np.arctan((K2 - K3) / denominator)))

    return float(DsA), proj


def calculate_indices(points: List[Point]) -> Dict[str, float]:
    """
    CI = dist(P5,P6) / dist(P6,P7)
    HI = dist(P5,P7) / dist(P3,P4)
    DsA = calculate_dsa_excel
    """
    if not isinstance(points, (list, tuple)) or len(points) != 8:
        return {"CI": 0.0, "DsA": 0.0, "HI": 0.0}

    p1, p2, p3, p4, p5, p6, p7, p8 = points

    d56 = dist(p5, p6)
    d67 = dist(p6, p7)
    ci = d56 / d67 if d67 > 1e-12 else 0.0

    d57 = dist(p5, p7)
    d34 = dist(p3, p4)
    hi = d57 / d34 if d34 > 1e-12 else 0.0

    dsa, _ = calculate_dsa_excel(points)

    return {"CI": float(ci), "DsA": float(dsa), "HI": float(hi)}


def identify_breed(CI: float, DsA: float, HI: float):
    """
    Возвращает 2 значения, как ожидает data_models.py:
      (breeds_found, index_valid)
    """
    breeds_found: List[str] = []
    index_valid = {"CI": False, "DsA": False, "HI": False}

    for name, ranges in BREEDS.items():
        ci_ok = ranges["CI"][0] <= CI <= ranges["CI"][1]
        dsa_ok = ranges["DsA"][0] <= DsA <= ranges["DsA"][1]
        hi_ok = ranges["HI"][0] <= HI <= ranges["HI"][1]

        if ci_ok:
            index_valid["CI"] = True
        if dsa_ok:
            index_valid["DsA"] = True
        if hi_ok:
            index_valid["HI"] = True

        if ci_ok and dsa_ok and hi_ok:
            breeds_found.append(name)

    return breeds_found, index_valid


def get_problem_points(index_valid: Dict[str, bool]) -> List[int]:
    problem_points = set()
    for index_name, is_valid in index_valid.items():
        if not is_valid and index_name in INDEX_POINTS:
            problem_points.update(INDEX_POINTS[index_name])
    return list(problem_points)


def ci_to_alpatov(ci: float) -> float:
    if ci <= 0:
        return 0.0
    return float((0.0381 * ci + 0.9982) / ci)


def ci_to_alpatov_classic(ci: float) -> float:
    """Классический кубитальный индекс в процентах по В. В. Алпатову (b/a * 100% = 100 / CI)."""
    if ci is None or not math.isfinite(float(ci)) or float(ci) <= 0:
        return 0.0
    return float(100.0 / float(ci))


def calculate_ruttner_classes(dsa_values: List[float]) -> Dict[str, float]:
    """
    Классификация дискоидального смещения (DsA) по Ф. Руттнеру:
      '-' (отрицательное): DsA < -0.5°
      '0' (нейтральное):  -0.5° <= DsA <= +0.5°
      '+' (положительное): DsA > +0.5°
    """
    valid = [float(v) for v in (dsa_values or []) if v is not None and math.isfinite(float(v))]
    total = len(valid)
    if total == 0:
        return {
            "minus": 0, "zero": 0, "plus": 0, "total": 0,
            "pct_minus": 0.0, "pct_zero": 0.0, "pct_plus": 0.0,
        }
    minus_cnt = sum(1 for v in valid if v < -0.5)
    zero_cnt = sum(1 for v in valid if -0.5 <= v <= 0.5)
    plus_cnt = sum(1 for v in valid if v > 0.5)
    return {
        "minus": minus_cnt,
        "zero": zero_cnt,
        "plus": plus_cnt,
        "total": total,
        "pct_minus": 100.0 * minus_cnt / total,
        "pct_zero": 100.0 * zero_cnt / total,
        "pct_plus": 100.0 * plus_cnt / total,
    }


def check_wing_orientation(points: List[Point]) -> Dict[str, object]:
    """
    Проверка топологии и ориентации 8 точек крыла (в экранных или WingsDig координатах).
    Проверяет:
    - не перепутаны ли местами точки 3 и 4 (в норме проекция P4 ближе к P1, чем P3: t_p4 < t_p3);
    - порядок точек кубитальной ячейки P5 -> P6 -> P7 вдоль оси P1 -> P2.
    """
    if not isinstance(points, (list, tuple)) or len(points) != 8:
        return {"is_standard": False, "is_swapped_p3_p4": False, "is_inverted_cubital": False, "warning": "Неполный набор точек"}

    p1, p2, p3, p4, p5, p6, p7, p8 = points
    vx = p2[0] - p1[0]
    vy = p2[1] - p1[1]
    vv = vx * vx + vy * vy
    if vv < 1e-6:
        return {"is_standard": False, "is_swapped_p3_p4": False, "is_inverted_cubital": False, "warning": "Вырожденная базовая ось P1-P2"}

    def _proj_t(pt: Point) -> float:
        return ((pt[0] - p1[0]) * vx + (pt[1] - p1[1]) * vy) / vv

    t3 = _proj_t(p3)
    t4 = _proj_t(p4)
    t5 = _proj_t(p5)
    t6 = _proj_t(p6)
    t7 = _proj_t(p7)

    swapped_p3_p4 = t3 < t4
    inverted_cubital = t5 > t7
    warnings = []
    if swapped_p3_p4:
        warnings.append("Возможно, перепутаны точки 3 и 4")
    if inverted_cubital:
        warnings.append("Инвертирован порядок точек кубитальной ячейки (5–6–7)")

    return {
        "is_standard": not (swapped_p3_p4 or inverted_cubital),
        "is_swapped_p3_p4": swapped_p3_p4,
        "is_inverted_cubital": inverted_cubital,
        "warning": "; ".join(warnings),
    }


def calculate_breed_distance(ci: float, dsa: float, hi: float, breed_name: str) -> float:
    """
    Нормированное 3D-расстояние от (ci, dsa, hi) до центра эталонного диапазона породы.
    Значение <= 1.0 означает попадание внутрь эталонного эллипсоида породы.
    """
    from .constants import BREED_RANGES
    if breed_name not in BREED_RANGES:
        return float("inf")
    ranges = BREED_RANGES[breed_name]
    d2 = 0.0
    for val, key in ((ci, "CI"), (dsa, "DsA"), (hi, "HI")):
        lo, hi_bound = ranges[key]
        center = 0.5 * (lo + hi_bound)
        half = max(1e-6, 0.5 * (hi_bound - lo))
        d2 += ((float(val) - center) / half) ** 2
    return float(math.sqrt(d2 / 3.0))


# Совместимость с core/__init__.py (если импортирует эти имена)
def calculate_ci(points: List[Point]) -> float:
    return calculate_indices(points).get("CI", 0.0)


def calculate_hi(points: List[Point]) -> float:
    return calculate_indices(points).get("HI", 0.0)


def calculate_dsa(points: List[Point]) -> float:
    return calculate_indices(points).get("DsA", 0.0)


def get_breed_scores(
    CI: Optional[float] = None,
    DsA: Optional[float] = None,
    HI: Optional[float] = None,
    points: Optional[List[Point]] = None,
) -> Dict[str, float]:
    if points is not None:
        idx = calculate_indices(points)
        CI = idx.get("CI", 0.0)
        DsA = idx.get("DsA", 0.0)
        HI = idx.get("HI", 0.0)

    if CI is None or DsA is None or HI is None:
        return {}

    def score_in_range(val: float, lo: float, hi: float) -> float:
        if hi <= lo:
            return 0.0
        if lo <= val <= hi:
            return 1.0
        width = hi - lo
        dist_out = (lo - val) if val < lo else (val - hi)
        s = 1.0 - (dist_out / width)
        return float(max(0.0, min(1.0, s)))

    scores: Dict[str, float] = {}
    for breed, ranges in BREEDS.items():
        s_ci = score_in_range(float(CI), *ranges["CI"])
        s_dsa = score_in_range(float(DsA), *ranges["DsA"])
        s_hi = score_in_range(float(HI), *ranges["HI"])
        scores[breed] = float((s_ci + s_dsa + s_hi) / 3.0)

    return scores



def calculate_breed_probability(
    ci_values: List[float],
    dsa_values: List[float],
    hi_values: List[float],
    breed_name: str
) -> float:
    """
    Рассчитать вероятность соответствия породе 1:1 как в Excel (58 WD.xlsm, лист "Результаты", K23:K26).

    Excel делает так:
    - Считает среднее и STDEV (выборочное, ddof=1) по значениям (как на листе "Индексы")
    - STDEV округляется до 3 знаков (ROUND(...,3))
    - Доверительный интервал (95%): [mean - stdev*1.96, mean + stdev*1.96]
    - Вероятность = (объём пересечения интервала семьи с диапазонами породы по CI, DsA, HI)
                    / (объём интервала семьи)
    """
    from .constants import BREED_RANGES

    if breed_name not in BREED_RANGES:
        return 0.0

    def _mean_stdev(values: List[float]) -> Tuple[float, float]:
        vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
        if not vals:
            return 0.0, 0.0
        mean = float(np.mean(vals))
        if len(vals) > 1:
            stdev = float(np.std(vals, ddof=1))
            stdev = float(round(stdev, 3))  # Excel: ROUND(STDEV(...),3)
        else:
            stdev = 0.0
        return mean, stdev

    def _interval(mean: float, stdev: float) -> tuple[float, float]:
        lo = mean - stdev * 1.96
        hi = mean + stdev * 1.96
        # Excel не делает доп. округления тут, оставляем как есть
        return lo, hi

    def _overlap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
        if a_hi < b_lo or a_lo > b_hi:
            return 0.0
        return max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo))

    ci_mean, ci_sd = _mean_stdev(ci_values)
    dsa_mean, dsa_sd = _mean_stdev(dsa_values)
    hi_mean, hi_sd = _mean_stdev(hi_values)

    ci_lo, ci_hi = _interval(ci_mean, ci_sd)
    dsa_lo, dsa_hi = _interval(dsa_mean, dsa_sd)
    hi_lo, hi_hi = _interval(hi_mean, hi_sd)

    fam_vol = (ci_hi - ci_lo) * (dsa_hi - dsa_lo) * (hi_hi - hi_lo)
    if fam_vol <= 0:
        return float(all(BREED_RANGES[breed_name][key][0] <= value <= BREED_RANGES[breed_name][key][1] for key,value in [("CI",ci_mean),("DsA",dsa_mean),("HI",hi_mean)]))

    br = BREED_RANGES[breed_name]
    ov_ci = _overlap(ci_lo, ci_hi, br['CI'][0], br['CI'][1])
    ov_dsa = _overlap(dsa_lo, dsa_hi, br['DsA'][0], br['DsA'][1])
    ov_hi = _overlap(hi_lo, hi_hi, br['HI'][0], br['HI'][1])

    inter_vol = ov_ci * ov_dsa * ov_hi
    return float(inter_vol / fam_vol)


def calculate_hybridization_score(
    values: List[float],
    breed_name: str,
    index_type: str
) -> int:
    """
    Рассчитать баллы за гибридизацию по алгоритму Excel.

    Excel алгоритм:
    1. Определяет границы преобладающей породы (например, для Mellifera CI: 0.76-2.16)
    2. Строит гистограмму распределения значений
    3. Находит, в каком классе гистограммы находится граница породы
    4. Считает крылья в двух рангах:
       - 2-й ранг: крылья ДАЛЬШЕ 3 классов от границы (явные гибриды)
       - 1-й ранг: крылья в пределах 3 классов от границы (подозрительные)
    5. Определяет степень гибридизации по процентам:
       - > 2% во 2-м ИЛИ > 15% в 1-м → ГИБРИД (0 баллов)
       - > 1% во 2-м ИЛИ > 7.5% в 1-м → Допустимая (1 балл)
       - > 0% во 2-м ИЛИ > 0% в 1-м → Несущественная (2 балла)
       - Оба = 0% → Отсутствует (3 балла)

    Args:
        values: Список значений индекса (CI, DsA или HI)
        breed_name: Название преобладающей породы
        index_type: Тип индекса ('CI', 'DsA', 'HI')

    Returns:
        Баллы: 0-3
    """
    from .constants import BREED_RANGES

    if not values or breed_name not in BREED_RANGES:
        return 0

    # Получаем границы породы для данного индекса
    breed_range = BREED_RANGES[breed_name][index_type]
    breed_min, breed_max = breed_range

    # Фильтруем валидные значения
    valid_values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not valid_values:
        return 0

    total_wings = len(valid_values)

    # Создаём гистограмму (30 классов, как в Excel на листе "Графики")
    # Excel использует равные интервалы от min до max значений
    min_val = min(valid_values)
    max_val = max(valid_values)

    # Если все значения одинаковые - нет гибридизации
    if abs(max_val - min_val) < 1e-10:
        return 3 if breed_min <= min_val <= breed_max else 0

    num_bins = 30
    bin_width = (max_val - min_val) / num_bins

    rank1 = rank2 = 0
    for value in valid_values:
        distance = max(breed_min - value, value - breed_max, 0)
        if distance > 3 * bin_width:
            rank2 += 1
        elif distance > 0:
            rank1 += 1
    pct_rank2 = 100 * rank2 / total_wings
    pct_rank1 = 100 * rank1 / total_wings
    if pct_rank2 > 2 or pct_rank1 > 15:
        return 0
    if pct_rank2 > 1 or pct_rank1 > 7.5:
        return 1
    if pct_rank2 > 0 or pct_rank1 > 0:
        return 2
    return 3
