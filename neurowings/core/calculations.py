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
        vals = [float(v) for v in values if v is not None and float(v) != 0.0]
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
        return 0.0

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
    valid_values = [float(v) for v in values if v is not None and float(v) != 0.0]
    if not valid_values:
        return 0

    total_wings = len(valid_values)

    # Создаём гистограмму (30 классов, как в Excel на листе "Графики")
    # Excel использует равные интервалы от min до max значений
    min_val = min(valid_values)
    max_val = max(valid_values)

    # Если все значения одинаковые - нет гибридизации
    if abs(max_val - min_val) < 1e-10:
        return 3

    num_bins = 30
    bin_width = (max_val - min_val) / num_bins

    # Создаём классы (бины)
    bins = []
    for i in range(num_bins):
        bin_start = min_val + i * bin_width
        bin_end = min_val + (i + 1) * bin_width
        bins.append((bin_start, bin_end))

    # Распределяем крылья по классам
    bin_counts = [0] * num_bins
    for value in valid_values:
        # Находим, в какой класс попадает значение
        for i, (bin_start, bin_end) in enumerate(bins):
            if i == num_bins - 1:  # Последний класс включает правую границу
                if bin_start <= value <= bin_end:
                    bin_counts[i] += 1
                    break
            else:
                if bin_start <= value < bin_end:
                    bin_counts[i] += 1
                    break

    # Определяем, какая граница породы критична (верхняя или нижняя)
    # Смотрим, с какой стороны больше крыльев выходит за границу
    mean_val = np.mean(valid_values)

    # Для анализа берём ту границу, которая ближе к среднему значению
    # (это та граница, которую крылья могут нарушить)
    if abs(mean_val - breed_min) < abs(mean_val - breed_max):
        # Средняя ближе к нижней границе - анализируем выход вниз
        critical_boundary = breed_min
        beyond_boundary = [v for v in valid_values if v < critical_boundary]
    else:
        # Средняя ближе к верхней границе - анализируем выход вверх
        critical_boundary = breed_max
        beyond_boundary = [v for v in valid_values if v > critical_boundary]

    # Если нет крыльев за границей - отлично
    if not beyond_boundary:
        return 3

    # Находим класс, в котором находится критическая граница
    boundary_bin = -1
    for i, (bin_start, bin_end) in enumerate(bins):
        if bin_start <= critical_boundary <= bin_end:
            boundary_bin = i
            break

    if boundary_bin == -1:
        # Граница вне диапазона - все крылья либо внутри, либо снаружи
        if beyond_boundary:
            pct_beyond = 100.0 * len(beyond_boundary) / total_wings
            if pct_beyond > 2:
                return 0  # Гибрид
            elif pct_beyond > 1:
                return 1  # Допустимая
            else:
                return 2  # Несущественная
        return 3

    # Определяем направление анализа (выше или ниже границы)
    if critical_boundary == breed_min:
        # Анализируем крылья ниже минимума (индексы < boundary_bin)
        rank2_bins = []  # 2-й ранг: дальше 3 классов от границы
        rank1_bins = []  # 1-й ранг: в пределах 3 классов от границы

        for i in range(boundary_bin):
            distance_from_boundary = boundary_bin - i
            if distance_from_boundary > 3:
                rank2_bins.append(i)
            else:
                rank1_bins.append(i)
    else:
        # Анализируем крылья выше максимума (индексы > boundary_bin)
        rank2_bins = []
        rank1_bins = []

        for i in range(boundary_bin + 1, num_bins):
            distance_from_boundary = i - boundary_bin
            if distance_from_boundary > 3:
                rank2_bins.append(i)
            else:
                rank1_bins.append(i)

    # Считаем крылья в рангах
    rank2_count = sum(bin_counts[i] for i in rank2_bins)
    rank1_count = sum(bin_counts[i] for i in rank1_bins)

    # Проценты
    pct_rank2 = 100.0 * rank2_count / total_wings if total_wings > 0 else 0.0
    pct_rank1 = 100.0 * rank1_count / total_wings if total_wings > 0 else 0.0

    # Определяем степень гибридизации по таблице Excel
    if pct_rank2 > 2 or pct_rank1 > 15:
        return 0  # ГИБРИД
    elif pct_rank2 > 1 or pct_rank1 > 7.5:
        return 1  # Допустимая
    elif pct_rank2 > 0 or pct_rank1 > 0:
        return 2  # Несущественная
    else:
        return 3  # Отсутствует
