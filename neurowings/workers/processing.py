#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Воркер обработки изображений (v2.2.0)

Оптимизации под любое железо (от слабых ноутбуков до мощных станций):
- Интеграция с HardwareProfiler и ComputeProfile (4 режима мощности)
- Параллельная предзагрузка сканов в ОЗУ через ThreadPoolExecutor во время работы нейросети
- Динамический размер батча model_pose (от 4 до 64 кропов за проход)
- Test-Time Augmentation (TTA / Multi-Crop Pose Ensemble) в режиме «Ультра-точность» и «Авто» на мощных ПК
- Локальная субпиксельная доводка точек по центру тёмной жилки (_subpixel_vein_snap)
- Распознавание одиночного крыла внутри пользовательской рамки (recognize_wing_in_bbox)
"""

from concurrent.futures import ThreadPoolExecutor
import gc
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union
import numpy as np
import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from ..core.image_io import read_rgb
from ..core.constants import (
    YOLO_TO_WINGSDIG, YOLO_DET_IMAGE_SIZE, YOLO_DET_CONFIDENCE,
    YOLO_POSE_IMAGE_SIZE, YOLO_POSE_CONFIDENCE, BBOX_MARGIN,
    STAGE2_CROP_SIZE, SUBPIXEL_CROP_SIZE,
    STAGE2_PORTABLE_CROP_HALF, STAGE2_PORTABLE_CROP_SIZE,
    STAGE2_PORTABLE_ITERATIONS, STAGE2_PORTABLE_MAX_OFFSET
)
from ..core.data_models import Wing, WingPoint, BBox
from ..core.models import TORCH_AVAILABLE, TORCH_IMPORT_ERROR
from ..core.hardware_profiler import HardwareProfiler, ComputeProfile

logger = logging.getLogger("NeuroWings")

# Ручная коррекция по Y для первых двух точек (смещение вверх в пикселях)
KP_Y_CORRECTION = {0: -3.0, 1: -3.0}
POSE_BATCH_SIZE = 16

if TORCH_AVAILABLE:
    import torch

BEST_PIPELINE = ['portable', 'portable', 'mac', 'portable', 'mac', 'mac', 'mac', 'mac']


class ProcessingWorker(QThread):
    """Воркер для обработки изображений в фоновом потоке с адаптацией под железо"""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        image_paths,
        model_det,
        model_pose,
        model_stage2,
        device,
        model_subpixel=None,
        model_stage2_portable=None,
        enable_refinement=True,
        compute_profile: Optional[ComputeProfile] = None,
    ):
        super().__init__()
        self.image_paths = [Path(p) for p in image_paths]
        self.model_det = model_det
        self.model_pose = model_pose
        self.enable_refinement = bool(enable_refinement)
        self.model_stage2 = model_stage2 if self.enable_refinement else None
        self.model_subpixel = model_subpixel if self.enable_refinement else None
        self.model_stage2_portable = model_stage2_portable if self.enable_refinement else None
        self.device = device
        self.compute_profile = compute_profile or HardwareProfiler.get_active_profile()
        self._stop = False

    @staticmethod
    def _run_pose_batch(model_pose, crops_list, imgsz: int = YOLO_POSE_IMAGE_SIZE, half: bool = False):
        """Запустить model_pose батчем с безопасным fallback на одиночный вызов."""
        if not crops_list:
            return []
        try:
            kwargs = {
                "imgsz": imgsz,
                "conf": YOLO_POSE_CONFIDENCE,
                "verbose": False,
            }
            if half:
                kwargs["half"] = True
            res = model_pose(crops_list, **kwargs)
            if isinstance(res, (list, tuple)) and len(res) == len(crops_list):
                return [[r] for r in res]
        except Exception:
            pass

        out = []
        for crop in crops_list:
            out.append(
                model_pose(
                    crop,
                    imgsz=imgsz,
                    conf=YOLO_POSE_CONFIDENCE,
                    verbose=False,
                )
            )
        return out

    @staticmethod
    def _subpixel_vein_snap(
        img_bgr: np.ndarray,
        x: float,
        y: float,
        radius: int = 2,
        max_shift: float = 1.5,
    ) -> Tuple[float, float]:
        """
        Мягкое субпиксельное уточнение координаты точки к центру тёмного перекрёстка жилок.
        Срабатывает только при достаточном локальном контрасте жилки (>= 18 ед. яркости)
        и сдвигает точку не более чем на max_shift пикселей от предсказания YOLO.
        """
        h, w = img_bgr.shape[:2]
        ix, iy = int(round(x)), int(round(y))
        r = radius + 1
        if ix - r < 0 or iy - r < 0 or ix + r >= w or iy + r >= h:
            return float(x), float(y)

        patch = img_bgr[iy - r : iy + r + 1, ix - r : ix + r + 1]
        if patch.size == 0:
            return float(x), float(y)

        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
        contrast = float(np.max(gray) - np.min(gray))
        if contrast < 18.0:
            # На синтетических или однородных участках не меняем координату
            return float(x), float(y)

        # Инвертируем яркость (жилка тёмная -> вес выше) и накладываем гауссово окно вокруг (x, y)
        darkness = float(np.max(gray)) - gray
        yy, xx = np.mgrid[-r : r + 1, -r : r + 1].astype(np.float32)
        dx0 = float(x - ix)
        dy0 = float(y - iy)
        gauss = np.exp(-((xx - dx0) ** 2 + (yy - dy0) ** 2) / (2.0 * (1.35 ** 2)))
        weights = (darkness ** 1.5) * gauss
        w_sum = float(np.sum(weights))
        if w_sum <= 1e-6:
            return float(x), float(y)

        shift_x = float(np.sum(weights * xx) / w_sum) - dx0
        shift_y = float(np.sum(weights * yy) / w_sum) - dy0
        # Демпфируем сдвиг (0.45) и жёстко ограничиваем радиусом max_shift
        shift_x = float(np.clip(shift_x * 0.45, -max_shift, max_shift))
        shift_y = float(np.clip(shift_y * 0.45, -max_shift, max_shift))
        return float(x + shift_x), float(y + shift_y)

    @staticmethod
    def _extract_FirstValidPose(pose_results, crop_w: int, crop_h: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Извлечь (kpt_xy [8, 2], conf [8]) из ответа model_pose для одного кропа."""
        for pose in pose_results:
            if getattr(pose, "keypoints", None) is None:
                continue
            kpts = pose.keypoints.xy.cpu().numpy()
            if len(kpts) == 0:
                continue
            confs = pose.keypoints.conf
            confs_np = confs.cpu().numpy() if confs is not None else None
            for pose_idx, kpt in enumerate(kpts):
                if len(kpt) != 8 or not np.isfinite(kpt).all():
                    continue
                if any(px <= 0 or py <= 0 or px >= crop_w or py >= crop_h for px, py in kpt):
                    continue
                if confs_np is not None:
                    c_vec = confs_np[pose_idx]
                    if not np.isfinite(c_vec).all() or (c_vec < 0.5).any():
                        continue
                else:
                    c_vec = np.ones(8, dtype=np.float32)
                return kpt.astype(np.float64), c_vec.astype(np.float64)
        return None

    @classmethod
    def recognize_wing_in_bbox(
        cls,
        image_path_or_rgb: Union[str, Path, np.ndarray],
        bbox: BBox,
        model_pose,
        device=None,
    ) -> Optional[Wing]:
        """
        Распознать 8 точек крыла внутри указанной пользователем рамки BBox.
        Использует активный профиль мощности (включая TTA, если включён).
        """
        if model_pose is None:
            return None
        try:
            if isinstance(image_path_or_rgb, np.ndarray):
                img_rgb = image_path_or_rgb
            else:
                img_rgb = read_rgb(image_path_or_rgb)
            if img_rgb is None or img_rgb.size == 0:
                return None

            h, w = img_rgb.shape[:2]
            x1 = int(round(min(bbox.x1, bbox.x2)))
            y1 = int(round(min(bbox.y1, bbox.y2)))
            x2 = int(round(max(bbox.x1, bbox.x2)))
            y2 = int(round(max(bbox.y1, bbox.y2)))

            profile = HardwareProfiler.get_active_profile()
            scales = profile.tta_scales if (profile and profile.use_tta) else (1.0,)

            crops_bgr = []
            crop_offsets = []
            for scale in scales:
                margin = int(round(BBOX_MARGIN * scale))
                x1m, y1m = max(0, x1 - margin), max(0, y1 - margin)
                x2m, y2m = min(w, x2 + margin), min(h, y2 + margin)
                if x2m - x1m < 10 or y2m - y1m < 10:
                    continue
                c_bgr = cv2.cvtColor(img_rgb[y1m:y2m, x1m:x2m], cv2.COLOR_RGB2BGR)
                crops_bgr.append(c_bgr)
                crop_offsets.append((x1m, y1m, c_bgr.shape[1], c_bgr.shape[0]))

            if not crops_bgr:
                return None

            ctx = torch.inference_mode() if TORCH_AVAILABLE else None
            if ctx is not None:
                ctx.__enter__()
            try:
                pose_batches = cls._run_pose_batch(model_pose, crops_bgr)
            finally:
                if ctx is not None:
                    ctx.__exit__(None, None, None)

            scale_preds = []
            for (x1m, y1m, cw, ch), pose_res in zip(crop_offsets, pose_batches):
                extracted = cls._extract_FirstValidPose(pose_res, cw, ch)
                if extracted is not None:
                    kpt_crop, conf_vec = extracted
                    global_xy = np.column_stack([kpt_crop[:, 0] + x1m, kpt_crop[:, 1] + y1m])
                    scale_preds.append((global_xy, conf_vec))

            if not scale_preds:
                return None

            base_xy, base_conf = scale_preds[0]
            if len(scale_preds) > 1:
                ensemble_xy = np.zeros_like(base_xy)
                for kp_i in range(8):
                    pts_i = [base_xy[kp_i]]
                    wts_i = [float(base_conf[kp_i]) * 1.25]  # Базовый кроп имеет приоритетный вес
                    for aug_xy, aug_conf in scale_preds[1:]:
                        dist = float(np.hypot(aug_xy[kp_i, 0] - base_xy[kp_i, 0], aug_xy[kp_i, 1] - base_xy[kp_i, 1]))
                        if dist <= 10.0:
                            pts_i.append(aug_xy[kp_i])
                            wts_i.append(float(aug_conf[kp_i]))
                    wts_arr = np.asarray(wts_i, dtype=np.float64)[:, None]
                    pts_arr = np.asarray(pts_i, dtype=np.float64)
                    ensemble_xy[kp_i] = np.sum(pts_arr * wts_arr, axis=0) / np.sum(wts_arr)
            else:
                ensemble_xy = base_xy

            yolo_points = [(float(ensemble_xy[i, 0]), float(ensemble_xy[i, 1])) for i in range(8)]
            yolo_wing_points = [yolo_points[YOLO_TO_WINGSDIG[i]] for i in range(8)]
            wing = Wing(
                points=[WingPoint(x=pt[0], y=pt[1]) for pt in yolo_wing_points],
                bbox=BBox(x1, y1, x2, y2),
                points_yolo=[WingPoint(x=pt[0], y=pt[1]) for pt in yolo_wing_points],
                point_sources=['yolo'] * 8,
            )
            wing.analyze(image_height=h, image_width=w)
            return wing
        except Exception as exc:
            logger.warning("Не удалось распознать крыло в рамке: %s", exc)
        return None

    def run(self):
        """Основной метод обработки с адаптацией под вычислительный профиль ПК"""
        if not TORCH_AVAILABLE:
            detail = TORCH_IMPORT_ERROR or "unknown import error"
            self.error.emit(f"Нейросетевой движок недоступен: {detail}")
            return

        try:
            profile = self.compute_profile or HardwareProfiler.get_active_profile()
            batch_size = max(1, int(getattr(profile, "pose_batch_size", POSE_BATCH_SIZE)))
            use_tta = bool(getattr(profile, "use_tta", False))
            tta_scales = tuple(getattr(profile, "tta_scales", (1.0,))) if use_tta else (1.0,)
            use_fp16 = bool(getattr(profile, "use_fp16", False)) and (str(self.device).startswith("cuda"))
            det_conf = float(getattr(profile, "det_conf", YOLO_DET_CONFIDENCE))
            profile_det_imgsz = int(getattr(profile, "det_imgsz", YOLO_DET_IMAGE_SIZE))
            pose_imgsz = int(getattr(profile, "pose_imgsz", YOLO_POSE_IMAGE_SIZE))

            results = {}
            file_errors = []
            total = len(self.image_paths)

            # Параллельный предзагрузчик следующего скана с диска во время работы GPU/CPU
            prefetch_pool = None
            prefetch_futures = {}
            if total > 1 and getattr(profile, "io_workers", 1) > 1 and not getattr(profile, "aggressive_gc", False):
                workers = min(4, int(profile.io_workers), total)
                prefetch_pool = ThreadPoolExecutor(max_workers=workers)
                for p in self.image_paths[: workers + 1]:
                    prefetch_futures[p] = prefetch_pool.submit(read_rgb, p)

            try:
                with torch.inference_mode():
                    for i, path in enumerate(self.image_paths):
                        if self._stop:
                            break

                        # Запускаем предзагрузку следующих файлов в очереди
                        if prefetch_pool is not None:
                            lookahead_idx = i + 2
                            if lookahead_idx < total:
                                next_p = self.image_paths[lookahead_idx]
                                if next_p not in prefetch_futures:
                                    prefetch_futures[next_p] = prefetch_pool.submit(read_rgb, next_p)

                        try:
                            mode_badge = " [TTA]" if len(tta_scales) > 1 else ""
                            self.progress.emit(i + 1, total, f"Обработка{mode_badge}: {path.name}")

                            if path in prefetch_futures:
                                img_rgb = prefetch_futures.pop(path).result()
                            else:
                                img_rgb = read_rgb(path)

                            if img_rgb is None or img_rgb.size == 0:
                                continue
                            h, w = img_rgb.shape[:2]
                            img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

                            # На сверхбольших сканах (>3200 px) используем повышенное разрешение детектора из профиля
                            effective_det_imgsz = (
                                profile_det_imgsz if max(w, h) >= 3200 else YOLO_DET_IMAGE_SIZE
                            )

                            wings = []
                            try:
                                det_kwargs = {
                                    "imgsz": effective_det_imgsz,
                                    "conf": det_conf,
                                    "verbose": False,
                                }
                                if use_fp16:
                                    det_kwargs["half"] = True
                                det_results = self.model_det(img, **det_kwargs)
                            except Exception:
                                det_results = self.model_det(
                                    img,
                                    imgsz=YOLO_DET_IMAGE_SIZE,
                                    conf=YOLO_DET_CONFIDENCE,
                                    verbose=False,
                                )

                            # Собираем боксы крыльев
                            detected_boxes = []
                            for det in det_results:
                                if det.boxes is None:
                                    continue
                                for box in det.boxes:
                                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                                    x1m, y1m = max(0, x1 - BBOX_MARGIN), max(0, y1 - BBOX_MARGIN)
                                    x2m, y2m = min(w, x2 + BBOX_MARGIN), min(h, y2 + BBOX_MARGIN)
                                    base_crop = img[y1m:y2m, x1m:x2m]
                                    if base_crop.size == 0:
                                        continue
                                    detected_boxes.append((x1, y1, x2, y2, x1m, y1m, x2m, y2m, base_crop))

                            # Формируем общий список кропов (с учётом TTA-масштабов, если включён ансамбль)
                            # Каждый элемент flat_tasks: (box_idx, scale_idx, x1m_s, y1m_s, crop_s)
                            flat_tasks = []
                            for box_idx, (x1, y1, x2, y2, x1m, y1m, x2m, y2m, base_crop) in enumerate(detected_boxes):
                                flat_tasks.append((box_idx, 0, x1m, y1m, base_crop))
                                if len(tta_scales) > 1:
                                    for s_idx, scale in enumerate(tta_scales[1:], start=1):
                                        margin_s = max(4, int(round(BBOX_MARGIN * scale)))
                                        sx1 = max(0, x1 - margin_s)
                                        sy1 = max(0, y1 - margin_s)
                                        sx2 = min(w, x2 + margin_s)
                                        sy2 = min(h, y2 + margin_s)
                                        scrop = img[sy1:sy2, sx1:sx2]
                                        if scrop.size > 0 and scrop.shape[0] >= 16 and scrop.shape[1] >= 16:
                                            flat_tasks.append((box_idx, s_idx, sx1, sy1, scrop))

                            # Прогоняем все кропы через model_pose крупными батчами
                            box_predictions = {b_idx: [] for b_idx in range(len(detected_boxes))}
                            for batch_start in range(0, len(flat_tasks), batch_size):
                                if self._stop:
                                    break
                                batch_slice = flat_tasks[batch_start : batch_start + batch_size]
                                batch_crops = [t[4] for t in batch_slice]
                                pose_batches = self._run_pose_batch(
                                    self.model_pose, batch_crops, imgsz=pose_imgsz, half=use_fp16
                                )
                                for (b_idx, s_idx, sx1, sy1, scrop), pose_res in zip(batch_slice, pose_batches):
                                    box_predictions[b_idx].append((s_idx, sx1, sy1, scrop, pose_res))

                            # Собираем итоговые точки по каждому крылу
                            for b_idx, (x1, y1, x2, y2, x1m, y1m, x2m, y2m, crop) in enumerate(detected_boxes):
                                preds_for_box = box_predictions.get(b_idx, [])
                                if not preds_for_box:
                                    continue

                                crop_h, crop_w = crop.shape[:2]
                                crop_rgb = img_rgb[y1m:y2m, x1m:x2m] if self.model_stage2 is not None else None

                                # Базовый кроп (scale_idx == 0)
                                base_pose_results = preds_for_box[0][4]
                                aug_entries = preds_for_box[1:]

                                # Собираем ансамбль TTA, если есть дополнительные масштабы
                                aug_valid_global = []
                                for _s_idx, sx1, sy1, scrop, s_pose_res in aug_entries:
                                    sh, sw = scrop.shape[:2]
                                    ext = self._extract_FirstValidPose(s_pose_res, sw, sh)
                                    if ext is not None:
                                        s_kpt, s_conf = ext
                                        g_xy = np.column_stack([s_kpt[:, 0] + sx1, s_kpt[:, 1] + sy1])
                                        aug_valid_global.append((g_xy, s_conf))

                                for pose in base_pose_results:
                                    if pose.keypoints is None:
                                        continue

                                    kpts = pose.keypoints.xy.cpu().numpy()
                                    if len(kpts) == 0:
                                        continue

                                    confidences = pose.keypoints.conf
                                    confidences = confidences.cpu().numpy() if confidences is not None else None
                                    for pose_idx, kpt in enumerate(kpts):
                                        if len(kpt) != 8:
                                            continue

                                        if not np.isfinite(kpt).all() or any(
                                            px <= 0 or py <= 0 or px >= crop_w or py >= crop_h for px, py in kpt
                                        ):
                                            logger.warning("Rejected missing/out-of-crop landmarks for %s", path)
                                            continue
                                        if confidences is not None and (
                                            not np.isfinite(confidences[pose_idx]).all()
                                            or (confidences[pose_idx] < 0.5).any()
                                        ):
                                            logger.warning("Rejected low-confidence landmarks for %s", path)
                                            continue

                                        base_conf_vec = (
                                            confidences[pose_idx]
                                            if confidences is not None
                                            else np.ones(8, dtype=np.float32)
                                        )

                                        # Если есть валидные TTA-предсказания, усредняем с весами уверенности
                                        if aug_valid_global:
                                            yolo_points_crop = []
                                            for kp_i in range(8):
                                                bx_g = float(kpt[kp_i][0] + x1m)
                                                by_g = float(kpt[kp_i][1] + y1m)
                                                pts_x = [bx_g]
                                                pts_y = [by_g]
                                                wts = [float(base_conf_vec[kp_i]) * 1.35]
                                                for aug_xy, aug_c in aug_valid_global:
                                                    ax_g = float(aug_xy[kp_i, 0])
                                                    ay_g = float(aug_xy[kp_i, 1])
                                                    if np.hypot(ax_g - bx_g, ay_g - by_g) <= 9.0:
                                                        pts_x.append(ax_g)
                                                        pts_y.append(ay_g)
                                                        wts.append(float(aug_c[kp_i]))
                                                w_sum = sum(wts)
                                                ens_gx = sum(px_v * w_v for px_v, w_v in zip(pts_x, wts)) / w_sum
                                                ens_gy = sum(py_v * w_v for py_v, w_v in zip(pts_y, wts)) / w_sum
                                                yolo_points_crop.append((ens_gx - x1m, ens_gy - y1m))
                                        else:
                                            yolo_points_crop = [(float(px), float(py)) for px, py in kpt]

                                        # Масштабно-инвариантное уточнение Stage2 + SubPixel + Portable
                                        # Каскад обучался на одиночных крыльях с базовой длиной dist(P0, P1) ~ 640 px.
                                        # Нормализуем масштаб кропа крыла к 640 px перед вырезанием патчей 256x256 и 64x64.
                                        has_refiners = (
                                            self.model_stage2 is not None
                                            or self.model_stage2_portable is not None
                                        )
                                        if has_refiners and crop.size > 0:
                                            stage1_refined, stage2_refined, portable_refined = (
                                                self._refine_wing_scale_normalized(
                                                    crop_bgr=crop,
                                                    yolo_points_crop=yolo_points_crop,
                                                    x1m=x1m,
                                                    y1m=y1m,
                                                )
                                            )
                                        else:
                                            stage1_refined = [(px + x1m, py + y1m) for px, py in yolo_points_crop]
                                            stage2_refined = stage1_refined
                                            portable_refined = stage1_refined

                                        yolo_points = [(px + x1m, py + y1m) for px, py in yolo_points_crop]

                                        mac_wing_points = [stage2_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                        mac_stage1_wing_points = [stage1_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                        portable_wing_points = [portable_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                        yolo_wing_points = [yolo_points[YOLO_TO_WINGSDIG[i]] for i in range(8)]

                                        final_points = []
                                        for idx in range(8):
                                            if BEST_PIPELINE[idx] == 'portable' and self.model_stage2_portable is not None:
                                                cand = portable_wing_points[idx]
                                            elif self.model_stage2 is not None:
                                                cand = mac_wing_points[idx]
                                            elif self.model_stage2_portable is not None:
                                                cand = portable_wing_points[idx]
                                            else:
                                                cand = yolo_wing_points[idx]
                                            final_points.append(cand)

                                        active_pts = final_points if has_refiners else yolo_wing_points
                                        active_src = 'stage2' if has_refiners else 'yolo'
                                        stage1_points = [WingPoint(x=pt[0], y=pt[1]) for pt in mac_stage1_wing_points] if self.model_stage2 else []

                                        wing = Wing(
                                            points=[WingPoint(x=pt[0], y=pt[1]) for pt in active_pts],
                                            bbox=BBox(x1, y1, x2, y2),
                                            points_yolo=[WingPoint(x=pt[0], y=pt[1]) for pt in yolo_wing_points],
                                            points_stage1=stage1_points,
                                            points_stage2=[WingPoint(x=pt[0], y=pt[1]) for pt in final_points] if has_refiners else [],
                                            point_sources=[active_src] * 8
                                        )
                                        wing.analyze(image_height=h, image_width=w)
                                        if wing.analysis.is_valid and all(
                                            np.isfinite(p.x) and np.isfinite(p.y) and 0 <= p.x < w and 0 <= p.y < h
                                            for p in wing.points
                                        ):
                                            wings.append(wing)
                                        else:
                                            logger.warning("Rejected invalid landmarks for %s", path)

                            results[str(path)] = wings

                            if getattr(profile, "aggressive_gc", False):
                                del img
                                del img_rgb
                                gc.collect()

                        except Exception as exc:
                            file_errors.append(f"{path.name}: {exc}")
                            logger.exception("Image processing failed: %s", path)
            finally:
                if prefetch_pool is not None:
                    prefetch_pool.shutdown(wait=False)

            self.finished.emit(results)
            if file_errors:
                self.error.emit("Часть файлов не обработана:\n" + "\n".join(file_errors))

            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU память очищена")

        except Exception as e:
            import traceback
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            self.error.emit(f"{str(e)}\n{traceback.format_exc()}")

    def _extract_patch(self, img, cx, cy, size, w, h):
        """
        Extract patch centered at (cx, cy).

        Returns:
            patch: The extracted patch (resized to size x size)
            (center_x, center_y): The actual center of the patch in image coordinates
        """
        half = size // 2
        left, top = int(round(cx)) - half, int(round(cy)) - half
        right, bottom = left + size, top + size
        patch = img[max(0, top):min(h, bottom), max(0, left):min(w, right)]
        if not patch.size:
            raise ValueError("Точка уточнения вне изображения")
        patch = cv2.copyMakeBorder(
            patch, max(0, -top), max(0, bottom - h),
            max(0, -left), max(0, right - w), cv2.BORDER_CONSTANT
        )
        return patch, (left + half, top + half)

    def _prepare_tensor(self, image):
        """
        Convert an RGB image patch to normalized NCHW tensor without torchvision.
        """
        arr = np.ascontiguousarray(image).astype(np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
        arr = (arr - mean) / std
        return torch.from_numpy(arr).unsqueeze(0).to(self.device)

    def _refine_point_stage2_only(self, img_rgb, x, y, w, h, skip_stage2=False):
        cx, cy = x, y

        if self.model_stage2 is not None and not skip_stage2:
            patch, (patch_cx, patch_cy) = self._extract_patch(img_rgb, cx, cy, STAGE2_CROP_SIZE, w, h)

            with torch.inference_mode():
                inp = self._prepare_tensor(patch)
                offset = self.model_stage2(inp)[0].cpu().numpy()

            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        return float(cx), float(cy)

    def _refine_point_full(self, img_rgb, x, y, w, h, skip_stage2=False):
        cx, cy = x, y

        if self.model_stage2 is not None and not skip_stage2:
            patch, (patch_cx, patch_cy) = self._extract_patch(img_rgb, cx, cy, STAGE2_CROP_SIZE, w, h)

            with torch.inference_mode():
                inp = self._prepare_tensor(patch)
                offset = self.model_stage2(inp)[0].cpu().numpy()

            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        if self.model_subpixel is not None:
            patch, (patch_cx, patch_cy) = self._extract_patch(img_rgb, cx, cy, SUBPIXEL_CROP_SIZE, w, h)

            with torch.inference_mode():
                inp = self._prepare_tensor(patch)
                offset = self.model_subpixel(inp)[0].cpu().numpy()

            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        return float(cx), float(cy)

    @staticmethod
    def _extract_zero_padded_patch_exact(img_bgr: np.ndarray, cx: float, cy: float, size: int):
        """Точное воспроизведение обучающего кропа для stage2_best.pth и subpixel_best.pth (BGR)."""
        height, width = img_bgr.shape[:2]
        half = size // 2
        x1 = int(max(0, cx - half))
        y1 = int(max(0, cy - half))
        x2 = int(min(width, cx + half))
        y2 = int(min(height, cy + half))
        patch = img_bgr[y1:y2, x1:x2]
        if patch.shape[0] < size or patch.shape[1] < size:
            padded = np.zeros((size, size, 3), dtype=np.uint8)
            ph, pw = patch.shape[:2]
            padded[:ph, :pw] = patch
            patch = padded
        if patch.shape[:2] != (size, size):
            patch = cv2.resize(patch, (size, size))
        return patch, (float(x1 + half), float(y1 + half))

    def _refine_wing_scale_normalized(
        self,
        crop_bgr: np.ndarray,
        yolo_points_crop: List[Tuple[float, float]],
        x1m: int,
        y1m: int,
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]], List[Tuple[float, float]]]:
        """
        Масштабно-инвариантное уточнение 8 точек крыла через Stage2 + SubPixel + Portable.
        Нормализует длину крыла dist(P0, P1) к каноническому масштабу обучения (640 px),
        выполняет уточнение в эталонном масштабе и возвращает глобальные координаты на скане.
        """
        ch, cw = crop_bgr.shape[:2]
        p0x, p0y = yolo_points_crop[0]
        p1x, p1y = yolo_points_crop[1]
        span = float(np.hypot(p1x - p0x, p1y - p0y))
        scale = float(np.clip(640.0 / max(span, 120.0), 0.35, 3.2))

        if abs(scale - 1.0) > 0.04:
            sw = max(32, int(round(cw * scale)))
            sh = max(32, int(round(ch * scale)))
            interp = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
            c_bgr_s = cv2.resize(crop_bgr, (sw, sh), interpolation=interp)
        else:
            scale = 1.0
            sw, sh = cw, ch
            c_bgr_s = crop_bgr

        pts_s = np.array([(px * scale, py * scale) for px, py in yolo_points_crop], dtype=np.float64)
        stage1_s = pts_s.copy()
        stage2_s = pts_s.copy()
        portable_s = pts_s.copy()

        # 1. Каскад Stage2 (256x256 BGR) + SubPixel (64x64 BGR)
        if self.model_stage2 is not None:
            s2_indices = list(range(1, 8))  # Точка KP0 пропускается в Stage2 по контракту обучения
            patches = []
            centers = []
            for idx in s2_indices:
                patch, center = self._extract_zero_padded_patch_exact(
                    c_bgr_s, stage1_s[idx, 0], stage1_s[idx, 1], STAGE2_CROP_SIZE
                )
                patches.append(self._prepare_tensor(patch)[0])
                centers.append(center)
            with torch.inference_mode():
                offsets = self.model_stage2(torch.stack(patches).to(self.device)).detach().cpu().numpy()
            for idx, center, offset in zip(s2_indices, centers, offsets):
                stage1_s[idx, 0] = center[0] + float(offset[0])
                stage1_s[idx, 1] = center[1] + float(offset[1])

            stage2_s = stage1_s.copy()
            if self.model_subpixel is not None:
                sp_patches = []
                sp_centers = []
                for idx in range(8):
                    patch, center = self._extract_zero_padded_patch_exact(
                        c_bgr_s, stage2_s[idx, 0], stage2_s[idx, 1], SUBPIXEL_CROP_SIZE
                    )
                    sp_patches.append(self._prepare_tensor(patch)[0])
                    sp_centers.append(center)
                with torch.inference_mode():
                    sp_offsets = self.model_subpixel(torch.stack(sp_patches).to(self.device)).detach().cpu().numpy()
                for idx, center, offset in zip(range(8), sp_centers, sp_offsets):
                    stage2_s[idx, 0] = center[0] + float(offset[0])
                    stage2_s[idx, 1] = center[1] + float(offset[1])

            for idx, corr_y in KP_Y_CORRECTION.items():
                stage1_s[idx, 1] += corr_y
                stage2_s[idx, 1] += corr_y

        # 2. Каскад Portable (256x256 RGB, 2 итерации)
        if self.model_stage2_portable is not None:
            c_rgb_s = cv2.cvtColor(c_bgr_s, cv2.COLOR_BGR2RGB)
            half = STAGE2_PORTABLE_CROP_HALF
            size = STAGE2_PORTABLE_CROP_SIZE
            for _ in range(STAGE2_PORTABLE_ITERATIONS):
                p_patches = []
                for idx in range(8):
                    cx, cy = portable_s[idx, 0], portable_s[idx, 1]
                    x1 = int(cx) - half
                    y1 = int(cy) - half
                    x2 = int(cx) + half
                    y2 = int(cy) + half
                    pad_l, pad_t = max(0, -x1), max(0, -y1)
                    pad_r, pad_b = max(0, x2 - sw), max(0, y2 - sh)
                    crop_p = c_rgb_s[max(0, y1):min(sh, y2), max(0, x1):min(sw, x2)].copy()
                    if any((pad_l, pad_t, pad_r, pad_b)):
                        crop_p = cv2.copyMakeBorder(
                            crop_p, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REFLECT_101
                        )
                    if crop_p.shape[:2] != (size, size):
                        crop_p = cv2.resize(crop_p, (size, size))
                    p_patches.append(self._prepare_tensor(crop_p)[0])
                with torch.inference_mode():
                    p_out = self.model_stage2_portable(torch.stack(p_patches).to(self.device)).detach().cpu().numpy()
                for idx, out_vec in enumerate(p_out):
                    dx = float(np.clip(out_vec[0] * half, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET))
                    dy = float(np.clip(out_vec[1] * half, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET))
                    portable_s[idx, 0] = np.clip(portable_s[idx, 0] + dx, 0, sw - 1)
                    portable_s[idx, 1] = np.clip(portable_s[idx, 1] + dy, 0, sh - 1)

        # Анатомический предохранитель (не более 22 px в каноническом масштабе 640 px от грубой точки YOLO)
        max_canonical_shift = 22.0
        out_stage1 = []
        out_stage2 = []
        out_portable = []
        for idx in range(8):
            bx, by = pts_s[idx]

            s1x, s1y = stage1_s[idx]
            if np.hypot(s1x - bx, s1y - by) > max_canonical_shift:
                s1x, s1y = bx, by
            out_stage1.append((float(s1x / scale + x1m), float(s1y / scale + y1m)))

            s2x, s2y = stage2_s[idx]
            if np.hypot(s2x - bx, s2y - by) > max_canonical_shift:
                s2x, s2y = bx, by
            out_stage2.append((float(s2x / scale + x1m), float(s2y / scale + y1m)))

            prx, pry = portable_s[idx]
            if np.hypot(prx - bx, pry - by) > max_canonical_shift:
                prx, pry = bx, by
            out_portable.append((float(prx / scale + x1m), float(pry / scale + y1m)))

        return out_stage1, out_stage2, out_portable

    def stop(self):
        """Остановить обработку"""
        self._stop = True

    def _refine_point_portable(self, img_rgb, x, y, w, h):
        if self.model_stage2_portable is None:
            return float(x), float(y)

        cx, cy = float(x), float(y)
        for _ in range(STAGE2_PORTABLE_ITERATIONS):
            x1 = int(cx) - STAGE2_PORTABLE_CROP_HALF
            y1 = int(cy) - STAGE2_PORTABLE_CROP_HALF
            x2 = int(cx) + STAGE2_PORTABLE_CROP_HALF
            y2 = int(cy) + STAGE2_PORTABLE_CROP_HALF

            pad_l, pad_t = max(0, -x1), max(0, -y1)
            pad_r, pad_b = max(0, x2 - w), max(0, y2 - h)

            x1c, y1c = max(0, x1), max(0, y1)
            x2c, y2c = min(w, x2), min(h, y2)

            crop = img_rgb[y1c:y2c, x1c:x2c].copy()
            if any([pad_l, pad_t, pad_r, pad_b]):
                crop = cv2.copyMakeBorder(crop, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REFLECT_101)

            if crop.shape[:2] != (STAGE2_PORTABLE_CROP_SIZE, STAGE2_PORTABLE_CROP_SIZE):
                crop = cv2.resize(crop, (STAGE2_PORTABLE_CROP_SIZE, STAGE2_PORTABLE_CROP_SIZE))

            with torch.inference_mode():
                inp = self._prepare_tensor(crop)
                out = self.model_stage2_portable(inp).cpu().numpy()[0]

            offset_x = np.clip(out[0] * STAGE2_PORTABLE_CROP_HALF, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET)
            offset_y = np.clip(out[1] * STAGE2_PORTABLE_CROP_HALF, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET)

            cx = np.clip(cx + offset_x, 0, w - 1)
            cy = np.clip(cy + offset_y, 0, h - 1)

        return float(cx), float(cy)
