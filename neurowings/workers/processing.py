#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Воркер обработки изображений
"""

import logging
import numpy as np
import cv2

from PyQt5.QtCore import QThread, pyqtSignal

from ..core.constants import (
    YOLO_TO_WINGSDIG, YOLO_DET_IMAGE_SIZE, YOLO_DET_CONFIDENCE,
    YOLO_POSE_IMAGE_SIZE, YOLO_POSE_CONFIDENCE, BBOX_MARGIN,
    STAGE2_CROP_SIZE, STAGE2_CROP_HALF, STAGE2_MAX_OFFSET, STAGE2_ITERATIONS
)
from ..core.data_models import Wing, WingPoint, BBox
from ..core.models import TORCH_AVAILABLE

logger = logging.getLogger("NeuroWings")

if TORCH_AVAILABLE:
    import torch
    from torchvision import transforms


class ProcessingWorker(QThread):
    """Воркер для обработки изображений в фоновом потоке"""
    
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, image_paths, model_det, model_pose, model_stage2, device):
        super().__init__()
        self.image_paths = image_paths
        self.model_det = model_det
        self.model_pose = model_pose
        self.model_stage2 = model_stage2
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
            
            for i, path in enumerate(self.image_paths):
                if self._stop:
                    break
                
                self.progress.emit(i + 1, total, f"Обработка: {path.name}")
                
                img = cv2.imread(str(path))
                if img is None:
                    continue
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w = img.shape[:2]

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
                                
                                yolo_points = [(px + x1m, py + y1m) for px, py in kpt]

                                # Применяем Stage2 если доступен
                                if self.model_stage2 is not None:
                                    # Stage1 = одна итерация Stage2
                                    stage1_refined = self._refine_points(img_rgb, yolo_points, tf, w, h, iterations=1)
                                    # Stage2 = полные итерации
                                    stage2_refined = self._refine_points(img_rgb, yolo_points, tf, w, h, iterations=STAGE2_ITERATIONS)
                                    final_points = stage2_refined
                                else:
                                    stage1_refined = yolo_points
                                    final_points = yolo_points

                                # Перестановка точек YOLO -> WingsDig
                                wing_points = [final_points[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                yolo_wing_points = [yolo_points[YOLO_TO_WINGSDIG[i]] for i in range(8)]
                                stage1_wing_points = [stage1_refined[YOLO_TO_WINGSDIG[i]] for i in range(8)]

                                stage1_points = [WingPoint(x=pt[0], y=pt[1]) for pt in stage1_wing_points] if self.model_stage2 else []
                                
                                wing = Wing(
                                    points=[WingPoint(x=pt[0], y=pt[1]) for pt in wing_points],
                                    bbox=BBox(x1, y1, x2, y2),
                                    points_yolo=[WingPoint(x=pt[0], y=pt[1]) for pt in yolo_wing_points],
                                    points_stage1=stage1_points,
                                    points_stage2=[WingPoint(x=pt[0], y=pt[1]) for pt in wing_points],
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

    def _refine_points(self, img_rgb, points, tf, w, h, iterations=STAGE2_ITERATIONS):
        """Уточнить координаты всех точек с помощью Stage2"""
        refined = []
        for pt in points:
            rx, ry = self._refine_point(img_rgb, pt[0], pt[1], tf, w, h, iterations)
            refined.append((rx, ry))
        return refined

    def _refine_point(self, img_rgb, x, y, tf, w, h, iterations=STAGE2_ITERATIONS):
        """Уточнить координаты одной точки с помощью Stage2"""
        cx, cy = x, y

        for _ in range(iterations):
            x1, y1 = int(cx) - STAGE2_CROP_HALF, int(cy) - STAGE2_CROP_HALF
            x2, y2 = int(cx) + STAGE2_CROP_HALF, int(cy) + STAGE2_CROP_HALF

            pad_l, pad_t = max(0, -x1), max(0, -y1)
            pad_r, pad_b = max(0, x2 - w), max(0, y2 - h)

            x1c, y1c = max(0, x1), max(0, y1)
            x2c, y2c = min(w, x2), min(h, y2)

            crop = img_rgb[y1c:y2c, x1c:x2c].copy()

            if any([pad_l, pad_t, pad_r, pad_b]):
                crop = cv2.copyMakeBorder(crop, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REFLECT_101)

            if crop.shape[:2] != (STAGE2_CROP_SIZE, STAGE2_CROP_SIZE):
                crop = cv2.resize(crop, (STAGE2_CROP_SIZE, STAGE2_CROP_SIZE))

            with torch.no_grad():
                inp = tf(crop).unsqueeze(0).to(self.device)
                out = self.model_stage2(inp).cpu().numpy()[0]

            offset_x = np.clip(out[0] * STAGE2_CROP_HALF, -STAGE2_MAX_OFFSET, STAGE2_MAX_OFFSET)
            offset_y = np.clip(out[1] * STAGE2_CROP_HALF, -STAGE2_MAX_OFFSET, STAGE2_MAX_OFFSET)

            cx = np.clip(cx + offset_x, 0, w - 1)
            cy = np.clip(cy + offset_y, 0, h - 1)

        return cx, cy
    
    def stop(self):
        """Остановить обработку"""
        self._stop = True
