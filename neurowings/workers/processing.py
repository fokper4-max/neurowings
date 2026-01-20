#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Воркер обработки изображений
Обновлено для models_trained_2025_01_19

Новая логика:
- Stage2 и SubPixel выдают прямое смещение в пикселях
- Смещение добавляется к центру патча (не к предсказанной точке)
- KP1 пропускает Stage2, но для KP1/KP2 добавлена ручная коррекция Y
"""

import logging
import numpy as np
import cv2

from PyQt5.QtCore import QThread, pyqtSignal

from ..core.constants import (
    YOLO_TO_WINGSDIG, YOLO_DET_IMAGE_SIZE, YOLO_DET_CONFIDENCE,
    YOLO_POSE_IMAGE_SIZE, YOLO_POSE_CONFIDENCE, BBOX_MARGIN,
    STAGE2_CROP_SIZE, SUBPIXEL_CROP_SIZE,
    STAGE2_PORTABLE_CROP_HALF, STAGE2_PORTABLE_CROP_SIZE,
    STAGE2_PORTABLE_ITERATIONS, STAGE2_PORTABLE_MAX_OFFSET
)
from ..core.data_models import Wing, WingPoint, BBox
from ..core.models import TORCH_AVAILABLE

logger = logging.getLogger("NeuroWings")

# Ручная коррекция по Y для первых двух точек (смещение вверх в пикселях)
KP_Y_CORRECTION = {0: -3.0, 1: -3.0}

if TORCH_AVAILABLE:
    import torch
    from torchvision import transforms


BEST_PIPELINE = ['portable', 'portable', 'mac', 'portable', 'mac', 'mac', 'mac', 'mac']


class ProcessingWorker(QThread):
    """Воркер для обработки изображений в фоновом потоке"""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, image_paths, model_det, model_pose, model_stage2, device,
                 model_subpixel=None, model_stage2_portable=None):
        super().__init__()
        self.image_paths = image_paths
        self.model_det = model_det
        self.model_pose = model_pose
        self.model_stage2 = model_stage2
        self.model_subpixel = model_subpixel
        self.model_stage2_portable = model_stage2_portable
        self.device = device
        self._stop = False

    def run(self):
        """Основной метод обработки"""
        if not TORCH_AVAILABLE:
            self.error.emit("PyTorch не установлен")
            return

        try:
            results = {}
            total = len(self.image_paths)

            tf = transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])
            self.tf = tf

            for i, path in enumerate(self.image_paths):
                if self._stop:
                    break

                self.progress.emit(i + 1, total, f"Обработка: {path.name}")

                img = cv2.imread(str(path))
                if img is None:
                    continue
                h, w = img.shape[:2]
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                wings = []
                det_results = self.model_det(img, imgsz=YOLO_DET_IMAGE_SIZE, conf=YOLO_DET_CONFIDENCE, verbose=False)

                for det in det_results:
                    if det.boxes is None:
                        continue

                    for box in det.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                        x1m, y1m = max(0, x1 - BBOX_MARGIN), max(0, y1 - BBOX_MARGIN)
                        x2m, y2m = min(w, x2 + BBOX_MARGIN), min(h, y2 + BBOX_MARGIN)

                        crop = img[y1m:y2m, x1m:x2m]
                        crop_h, crop_w = crop.shape[:2]

                        pose_results = self.model_pose(crop, imgsz=YOLO_POSE_IMAGE_SIZE, conf=YOLO_POSE_CONFIDENCE, verbose=False)

                        for pose in pose_results:
                            if pose.keypoints is None:
                                continue

                            kpts = pose.keypoints.xy.cpu().numpy()
                            if len(kpts) == 0:
                                continue

                            for kpt in kpts:
                                if len(kpt) != 8:
                                    continue

                                # YOLO points (relative to crop)
                                yolo_points_crop = [(px, py) for px, py in kpt]

                                # Stage1/Stage2 (MAC pipeline)
                                if self.model_stage2 is not None:
                                    stage1_refined = []
                                    stage2_refined = []

                                    for kp_idx, (px, py) in enumerate(yolo_points_crop):
                                        skip_s2 = (kp_idx == 0)

                                        s1x, s1y = self._refine_point_stage2_only(
                                            crop, px, py, tf, crop_w, crop_h, skip_stage2=skip_s2
                                        )
                                        if kp_idx in KP_Y_CORRECTION:
                                            s1y += KP_Y_CORRECTION[kp_idx]
                                        stage1_refined.append((s1x + x1m, s1y + y1m))

                                        s2x, s2y = self._refine_point_full(
                                            crop, px, py, tf, crop_w, crop_h, skip_stage2=skip_s2
                                        )
                                        if kp_idx in KP_Y_CORRECTION:
                                            s2y += KP_Y_CORRECTION[kp_idx]
                                        stage2_refined.append((s2x + x1m, s2y + y1m))
                                else:
                                    stage1_refined = [(px + x1m, py + y1m) for px, py in yolo_points_crop]
                                    stage2_refined = stage1_refined

                                # Portable pipeline (Stage2 iterative, нормализованный выход)
                                portable_refined = []
                                if self.model_stage2_portable is not None:
                                    for px, py in yolo_points_crop:
                                        rx, ry = self._refine_point_portable(img_rgb, px + x1m, py + y1m, w, h)
                                        portable_refined.append((rx, ry))
                                else:
                                    portable_refined = [(px + x1m, py + y1m) for px, py in yolo_points_crop]

                                # Convert YOLO points to global coordinates
                                yolo_points = [(px + x1m, py + y1m) for px, py in yolo_points_crop]

                                # Перестановка точек YOLO -> WingsDig
                                mac_wing_points = [stage2_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                mac_stage1_wing_points = [stage1_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                portable_wing_points = [portable_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                yolo_wing_points = [yolo_points[YOLO_TO_WINGSDIG[i]] for i in range(8)]

                                # Комбинация: выбираем лучшую модель по KPI
                                final_points = []
                                for idx in range(8):
                                    if BEST_PIPELINE[idx] == 'portable':
                                        final_points.append(portable_wing_points[idx])
                                    else:
                                        final_points.append(mac_wing_points[idx])

                                stage1_points = [WingPoint(x=pt[0], y=pt[1]) for pt in mac_stage1_wing_points] if self.model_stage2 else []

                                wing = Wing(
                                    points=[WingPoint(x=pt[0], y=pt[1]) for pt in final_points],
                                    bbox=BBox(x1, y1, x2, y2),
                                    points_yolo=[WingPoint(x=pt[0], y=pt[1]) for pt in yolo_wing_points],
                                    points_stage1=stage1_points,
                                    points_stage2=[WingPoint(x=pt[0], y=pt[1]) for pt in final_points],
                                    point_sources=['stage2'] * 8
                                )
                                wings.append(wing)

                results[str(path)] = wings

            self.finished.emit(results)

            # Очистка GPU памяти
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

        # Calculate patch bounds
        x1 = int(max(0, cx - half))
        y1 = int(max(0, cy - half))
        x2 = int(min(w, cx + half))
        y2 = int(min(h, cy + half))

        # Extract patch
        patch = img[y1:y2, x1:x2]

        # Pad if needed
        if patch.shape[0] < size or patch.shape[1] < size:
            padded = np.zeros((size, size, 3), dtype=np.uint8)
            ph, pw = patch.shape[:2]
            padded[:ph, :pw] = patch
            patch = padded

        # Resize to target size
        patch = cv2.resize(patch, (size, size))

        # Return patch center in image coordinates
        return patch, (x1 + half, y1 + half)

    def _refine_point_stage2_only(self, img, x, y, tf, w, h, skip_stage2=False):
        """
        Refine point using only Stage2 model (for Stage1 display).
        Uses new 2025 logic: direct pixel offset from patch center.
        """
        cx, cy = x, y

        if self.model_stage2 is not None and not skip_stage2:
            patch, (patch_cx, patch_cy) = self._extract_patch(img, cx, cy, STAGE2_CROP_SIZE, w, h)

            with torch.no_grad():
                inp = tf(patch).unsqueeze(0).to(self.device)
                offset = self.model_stage2(inp)[0].cpu().numpy()

            # NEW LOGIC: add offset to patch center (not to cx, cy!)
            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        return float(cx), float(cy)

    def _refine_point_full(self, img, x, y, tf, w, h, skip_stage2=False):
        """
        Refine point using full pipeline: Stage2 + SubPixel.
        Uses new 2025 logic: direct pixel offset from patch center.
        """
        cx, cy = x, y

        # Stage2 refinement (256x256 patch)
        if self.model_stage2 is not None and not skip_stage2:
            patch, (patch_cx, patch_cy) = self._extract_patch(img, cx, cy, STAGE2_CROP_SIZE, w, h)

            with torch.no_grad():
                inp = tf(patch).unsqueeze(0).to(self.device)
                offset = self.model_stage2(inp)[0].cpu().numpy()

            # NEW LOGIC: add offset to patch center
            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        # SubPixel refinement (64x64 patch)
        if self.model_subpixel is not None:
            patch, (patch_cx, patch_cy) = self._extract_patch(img, cx, cy, SUBPIXEL_CROP_SIZE, w, h)

            with torch.no_grad():
                inp = tf(patch).unsqueeze(0).to(self.device)
                offset = self.model_subpixel(inp)[0].cpu().numpy()

            # Add offset to patch center
            cx = patch_cx + offset[0]
            cy = patch_cy + offset[1]

        return float(cx), float(cy)

    def stop(self):
        """Остановить обработку"""
        self._stop = True

    def _refine_point_portable(self, img_rgb, x, y, w, h):
        """
        Iterative refinement using portable Stage2 (normalized offset, clamped).
        """
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

            with torch.no_grad():
                inp = self.tf(crop).unsqueeze(0).to(self.device)
                out = self.model_stage2_portable(inp).cpu().numpy()[0]

            offset_x = np.clip(out[0] * STAGE2_PORTABLE_CROP_HALF, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET)
            offset_y = np.clip(out[1] * STAGE2_PORTABLE_CROP_HALF, -STAGE2_PORTABLE_MAX_OFFSET, STAGE2_PORTABLE_MAX_OFFSET)

            cx = np.clip(cx + offset_x, 0, w - 1)
            cy = np.clip(cy + offset_y, 0, h - 1)

        return float(cx), float(cy)
