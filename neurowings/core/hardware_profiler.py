#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Профайлер аппаратных ресурсов и менеджер вычислительных профилей (v2.2.0).

Автоматически определяет ресурсы компьютера (ядра/потоки CPU, объём ОЗУ в ГБ,
наличие GPU NVIDIA CUDA / Apple Silicon MPS и объём видеопамяти VRAM, разрешение экрана)
и настраивает PyTorch, OpenCV, размер батчей, кэш изображений и Test-Time Augmentation (TTA)
для максимальной скорости и точности распознавания на любом оборудовании —
от слабых полевых ноутбуков (4 ГБ ОЗУ) до мощных рабочих станций с мониторами 5160x2160.
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger("NeuroWings.Hardware")

POWER_MODES: Dict[str, str] = {
    "auto": "🚀 Авто (Максимум системы)",
    "ultra_quality": "🎯 Ультра-точность (Макс. качество + TTA)",
    "turbo_speed": "⚡ Турбо-скорость (Макс. батч)",
    "eco": "🍃 Экономный (Слабый ноутбук)",
}


@dataclass
class HardwareSpecs:
    """Фактические характеристики аппаратного обеспечения компьютера."""
    os_name: str
    cpu_name: str
    logical_cores: int
    physical_cores: int
    ram_total_gb: float
    ram_available_gb: float
    accelerator: str          # 'cuda', 'mps', 'cpu'
    gpu_name: str
    vram_total_gb: float
    cuda_compute_capability: Tuple[int, int] = (0, 0)
    supports_fp16: bool = False
    tier: str = "medium"      # 'extreme', 'high', 'medium', 'low'

    def short_summary_ru(self) -> str:
        gpu_part = (
            f"GPU: {self.gpu_name} ({self.vram_total_gb:.1f} ГБ VRAM)"
            if self.accelerator == "cuda"
            else (f"GPU: {self.gpu_name}" if self.accelerator == "mps" else "GPU: нет (CPU)")
        )
        return (
            f"{self.logical_cores} поток(ов) CPU ({self.physical_cores} ядер) | "
            f"{self.ram_total_gb:.1f} ГБ ОЗУ | {gpu_part}"
        )


@dataclass
class ComputeProfile:
    """Параметры исполнения нейросетей и ввода-вывода для выбранного режима мощности."""
    mode: str                                 # 'auto', 'ultra_quality', 'turbo_speed', 'eco'
    mode_label_ru: str
    device: str                               # 'cuda', 'mps', 'cpu'
    cpu_threads: int                          # Потоки PyTorch
    cv2_threads: int                          # Потоки OpenCV
    io_workers: int                           # Потоки параллельного чтения/предзагрузки сканов
    pixmap_cache_size: int                    # Размер LRU-кэша полноразмерных сканов в ОЗУ
    det_imgsz: int                            # Разрешение YOLO-детектора крыльев (1280 / 1536 / 1600)
    det_conf: float                           # Порог уверенности детектора крыльев
    pose_imgsz: int                           # Разрешение кропа крыла для YOLO-pose (768)
    pose_batch_size: int                      # Размер батча для кропов крыльев (4 .. 64)
    use_fp16: bool                            # Использовать ли FP16 (half precision) на CUDA
    use_tta: bool                             # Test-Time Augmentation (мульти-масштабный ансамбль кропов)
    tta_scales: Tuple[float, ...]             # Масштабы кропов при TTA, например (1.0, 0.92, 1.08)
    use_subpixel_vein_snap: bool              # Локальное субпиксельное уточнение центра жилки
    preload_folder_in_ram: bool               # Фоновая параллельная предзагрузка сканов папки
    aggressive_gc: bool                       # Принудительная очистка памяти после каждого скана
    specs: HardwareSpecs = None

    def status_bar_text(self) -> str:
        acc = self.device.upper()
        tta_badge = " + TTA" if self.use_tta else ""
        fp16_badge = " FP16" if self.use_fp16 else ""
        ram_gb = self.specs.ram_total_gb if self.specs else 0.0
        return (
            f"⚡ {self.mode_label_ru} | "
            f"CPU: {self.cpu_threads} пот. | ОЗУ: {ram_gb:.0f} ГБ | "
            f"{acc}{fp16_badge} (батч {self.pose_batch_size}{tta_badge})"
        )

    def detailed_tooltip_ru(self) -> str:
        s = self.specs
        lines = [
            f"Активный профиль: {self.mode_label_ru}",
            "─" * 42,
        ]
        if s:
            lines.extend([
                f"Процессор: {s.cpu_name} ({s.physical_cores} ядер / {s.logical_cores} потоков)",
                f"Оперативная память: {s.ram_total_gb:.1f} ГБ всего (~{s.ram_available_gb:.1f} ГБ доступно)",
                f"Ускоритель ИИ: {s.gpu_name} [{s.accelerator.upper()}]",
            ])
            if s.accelerator == "cuda":
                lines.append(f"Видеопамять VRAM: {s.vram_total_gb:.1f} ГБ (CC {s.cuda_compute_capability[0]}.{s.cuda_compute_capability[1]})")
            lines.append(f"Класс системы: {s.tier.upper()}")
            lines.append("─" * 42)
        lines.extend([
            f"Потоки PyTorch / OpenCV: {self.cpu_threads} / {self.cv2_threads}",
            f"Потоки предзагрузки диска: {self.io_workers}",
            f"Кэш сканов в ОЗУ: до {self.pixmap_cache_size} фото",
            f"Разрешение детектора крыльев: {self.det_imgsz} px (conf={self.det_conf:.2f})",
            f"Размер батча точек крыла: {self.pose_batch_size} кропов за проход",
            f"Мульти-кроп ансамбль (TTA): {'ВКЛЮЧЕН ' + str(self.tta_scales) if self.use_tta else 'Выкл.'}",
            f"Субпиксельная доводка жилки: {'ВКЛЮЧЕНА' if self.use_subpixel_vein_snap else 'Выкл.'}",
        ])
        return "\n".join(lines)


def _detect_ram_gb() -> Tuple[float, float]:
    """Определить общий и доступный объём ОЗУ в ГБ без внешних зависимостей."""
    # 1. Пробуем psutil, если установлен
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        return round(vm.total / (1024 ** 3), 2), round(vm.available / (1024 ** 3), 2)
    except Exception:
        pass

    # 2. Windows через ctypes GlobalMemoryStatusEx
    if sys.platform.startswith("win"):
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024 ** 3)
                avail_gb = stat.ullAvailPhys / (1024 ** 3)
                return round(total_gb, 2), round(avail_gb, 2)
        except Exception:
            pass

    # 3. Linux (/proc/meminfo)
    if Path_meminfo := ("/proc/meminfo" if os.path.exists("/proc/meminfo") else None):
        try:
            total_kb = 0
            avail_kb = 0
            with open(Path_meminfo, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
            if total_kb > 0:
                total_gb = total_kb / (1024 ** 2)
                avail_gb = (avail_kb / (1024 ** 2)) if avail_kb > 0 else (total_gb * 0.65)
                return round(total_gb, 2), round(avail_gb, 2)
        except Exception:
            pass

    # 4. macOS / POSIX sysconf
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            if page_size > 0 and phys_pages > 0:
                total_gb = (page_size * phys_pages) / (1024 ** 3)
                return round(total_gb, 2), round(total_gb * 0.7, 2)
    except Exception:
        pass

    return 8.0, 5.0


def _detect_cpu_cores() -> Tuple[int, int, str]:
    """Определить (logical_cores, physical_cores, cpu_name)."""
    logical = max(1, os.cpu_count() or 4)
    physical = max(1, logical // 2) if logical >= 4 else logical
    cpu_name = platform.processor() or platform.machine() or "CPU"

    try:
        import psutil  # type: ignore
        phys = psutil.cpu_count(logical=False)
        if phys and phys > 0:
            physical = phys
    except Exception:
        if sys.platform == "darwin":
            try:
                out = subprocess.check_output(
                    ["sysctl", "-n", "hw.physicalcpu"], timeout=1.0
                ).decode("utf-8", errors="ignore").strip()
                if out.isdigit():
                    physical = int(out)
                brand = subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], timeout=1.0
                ).decode("utf-8", errors="ignore").strip()
                if brand:
                    cpu_name = brand
            except Exception:
                pass

    return logical, physical, cpu_name


class HardwareProfiler:
    """Синглтон-профайлер железа и управления режимами мощности."""

    _cached_specs: Optional[HardwareSpecs] = None
    _active_mode: str = "auto"
    _active_profile: Optional[ComputeProfile] = None

    @classmethod
    def detect_specs(cls, force_refresh: bool = False) -> HardwareSpecs:
        if cls._cached_specs is not None and not force_refresh:
            return cls._cached_specs

        logical_cores, physical_cores, cpu_name = _detect_cpu_cores()
        ram_total_gb, ram_avail_gb = _detect_ram_gb()

        accelerator = "cpu"
        gpu_name = "CPU"
        vram_total_gb = 0.0
        cc = (0, 0)
        supports_fp16 = False

        try:
            import torch
            if torch.cuda.is_available():
                accelerator = "cuda"
                gpu_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                vram_total_gb = round(props.total_memory / (1024 ** 3), 2)
                cc = (int(props.major), int(props.minor))
                supports_fp16 = bool(cc[0] >= 7 and vram_total_gb >= 3.5)
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                accelerator = "mps"
                gpu_name = f"Apple Silicon GPU ({cpu_name})"
                # Единая память Apple Silicon: доступно до ~75% системного ОЗУ
                vram_total_gb = round(ram_total_gb * 0.75, 1)
                supports_fp16 = False
        except Exception:
            pass

        # Классификация мощности системы
        if (
            (accelerator == "cuda" and vram_total_gb >= 8.0 and ram_total_gb >= 16.0)
            or (accelerator == "mps" and ram_total_gb >= 24.0 and logical_cores >= 8)
            or (logical_cores >= 16 and ram_total_gb >= 32.0)
        ):
            tier = "extreme"
        elif (
            accelerator in ("cuda", "mps")
            or (logical_cores >= 8 and ram_total_gb >= 14.0)
        ):
            tier = "high"
        elif logical_cores >= 4 and ram_total_gb >= 7.0:
            tier = "medium"
        else:
            tier = "low"

        cls._cached_specs = HardwareSpecs(
            os_name=f"{platform.system()} {platform.release()}",
            cpu_name=cpu_name,
            logical_cores=logical_cores,
            physical_cores=physical_cores,
            ram_total_gb=ram_total_gb,
            ram_available_gb=ram_avail_gb,
            accelerator=accelerator,
            gpu_name=gpu_name,
            vram_total_gb=vram_total_gb,
            cuda_compute_capability=cc,
            supports_fp16=supports_fp16,
            tier=tier,
        )
        return cls._cached_specs

    @classmethod
    def build_profile(cls, mode: str = "auto") -> ComputeProfile:
        if mode not in POWER_MODES:
            mode = "auto"
        specs = cls.detect_specs()

        logical = specs.logical_cores
        ram = specs.ram_total_gb
        vram = specs.vram_total_gb
        acc = specs.accelerator

        # Базовые настройки потоков (100% ядер процессора вместо старого лимита в 2 потока!)
        full_cpu_threads = max(1, logical)
        full_cv2_threads = max(1, logical)
        io_workers = min(16, max(2, logical)) if ram >= 12.0 else max(1, min(4, logical // 2))

        # Кэш полноразмерных сканов в ОЗУ в зависимости от доступной памяти
        if ram >= 28.0:
            cache_size = 30
        elif ram >= 15.0:
            cache_size = 18
        elif ram >= 8.0:
            cache_size = 8
        else:
            cache_size = 2

        if mode == "eco":
            return ComputeProfile(
                mode="eco",
                mode_label_ru=POWER_MODES["eco"],
                device=acc,
                cpu_threads=max(1, logical // 2),
                cv2_threads=max(1, logical // 2),
                io_workers=1,
                pixmap_cache_size=2,
                det_imgsz=1280,
                det_conf=0.25,
                pose_imgsz=768,
                pose_batch_size=4,
                use_fp16=specs.supports_fp16,
                use_tta=False,
                tta_scales=(1.0,),
                use_subpixel_vein_snap=False,
                preload_folder_in_ram=False,
                aggressive_gc=True,
                specs=specs,
            )

        if mode == "turbo_speed":
            if acc == "cuda" and vram >= 8.0:
                batch_sz = 64
            elif acc in ("cuda", "mps") and (vram >= 4.0 or ram >= 16.0):
                batch_sz = 48
            elif ram >= 16.0:
                batch_sz = 32
            else:
                batch_sz = 16
            return ComputeProfile(
                mode="turbo_speed",
                mode_label_ru=POWER_MODES["turbo_speed"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=max(4, io_workers),
                pixmap_cache_size=max(10, cache_size),
                det_imgsz=1280,
                det_conf=0.25,
                pose_imgsz=768,
                pose_batch_size=batch_sz,
                use_fp16=specs.supports_fp16,
                use_tta=False,
                tta_scales=(1.0,),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=ram >= 12.0,
                aggressive_gc=ram < 8.0,
                specs=specs,
            )

        if mode == "ultra_quality":
            if acc == "cuda" and vram >= 8.0:
                batch_sz = 48
            elif acc in ("cuda", "mps") and (vram >= 4.0 or ram >= 16.0):
                batch_sz = 32
            elif ram >= 12.0:
                batch_sz = 24
            else:
                batch_sz = 12
            return ComputeProfile(
                mode="ultra_quality",
                mode_label_ru=POWER_MODES["ultra_quality"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=io_workers,
                pixmap_cache_size=cache_size,
                det_imgsz=1280,
                det_conf=0.22,
                pose_imgsz=768,
                pose_batch_size=batch_sz,
                use_fp16=False,  # Полная точность FP32 для максимального качества точек
                use_tta=True,
                tta_scales=(1.0, 0.92, 1.08),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=ram >= 12.0,
                aggressive_gc=ram < 8.0,
                specs=specs,
            )

        # Режим "auto" (🚀 Авто - выжимаем максимум из доступной конфигурации)
        if specs.tier == "extreme":
            return ComputeProfile(
                mode="auto",
                mode_label_ru=POWER_MODES["auto"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=io_workers,
                pixmap_cache_size=cache_size,
                det_imgsz=1280,
                det_conf=0.22,
                pose_imgsz=768,
                pose_batch_size=48,
                use_fp16=False,
                use_tta=True,
                tta_scales=(1.0, 0.92, 1.08),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=True,
                aggressive_gc=False,
                specs=specs,
            )
        elif specs.tier == "high":
            return ComputeProfile(
                mode="auto",
                mode_label_ru=POWER_MODES["auto"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=io_workers,
                pixmap_cache_size=cache_size,
                det_imgsz=1280,
                det_conf=0.23,
                pose_imgsz=768,
                pose_batch_size=32,
                use_fp16=False,
                use_tta=True,
                tta_scales=(1.0, 0.93),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=ram >= 14.0,
                aggressive_gc=False,
                specs=specs,
            )
        elif specs.tier == "medium":
            return ComputeProfile(
                mode="auto",
                mode_label_ru=POWER_MODES["auto"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=io_workers,
                pixmap_cache_size=cache_size,
                det_imgsz=1280,
                det_conf=0.25,
                pose_imgsz=768,
                pose_batch_size=16,
                use_fp16=specs.supports_fp16,
                use_tta=False,
                tta_scales=(1.0,),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=False,
                aggressive_gc=False,
                specs=specs,
            )
        else:
            return ComputeProfile(
                mode="auto",
                mode_label_ru=POWER_MODES["auto"],
                device=acc,
                cpu_threads=full_cpu_threads,
                cv2_threads=full_cv2_threads,
                io_workers=1,
                pixmap_cache_size=2,
                det_imgsz=1280,
                det_conf=0.25,
                pose_imgsz=768,
                pose_batch_size=6,
                use_fp16=specs.supports_fp16,
                use_tta=False,
                tta_scales=(1.0,),
                use_subpixel_vein_snap=True,
                preload_folder_in_ram=False,
                aggressive_gc=True,
                specs=specs,
            )

    @classmethod
    def apply_profile(cls, mode: Optional[str] = None) -> ComputeProfile:
        """Построить и применить вычислительный профиль к PyTorch, OpenCV и кэшу изображений."""
        if mode is not None:
            cls._active_mode = mode
        profile = cls.build_profile(cls._active_mode)
        cls._active_profile = profile

        # 1. Настройка потоков окружения и PyTorch
        is_wine_or_restricted = (
            os.environ.get("KMP_AFFINITY") == "disabled"
            or "WINEPREFIX" in os.environ
            or os.environ.get("NEUROWINGS_FORCE_SINGLE_THREAD") == "1"
        )
        effective_threads = 1 if is_wine_or_restricted else profile.cpu_threads
        effective_cv2_threads = 0 if is_wine_or_restricted else profile.cv2_threads
        os.environ["OMP_NUM_THREADS"] = str(effective_threads)
        os.environ["MKL_NUM_THREADS"] = str(effective_threads)
        try:
            import torch
            if not is_wine_or_restricted:
                torch.set_num_threads(effective_threads)
            if torch.cuda.is_available():
                torch.backends.cudnn.benchmark = True
                if hasattr(torch.backends.cuda, "matmul"):
                    torch.backends.cuda.matmul.allow_tf32 = True
                if hasattr(torch.backends.cudnn, "allow_tf32"):
                    torch.backends.cudnn.allow_tf32 = True
        except Exception as e:
            logger.debug(f"Не удалось применить настройки потоков PyTorch: {e}")

        # 2. Настройка потоков OpenCV
        try:
            import cv2
            cv2.setNumThreads(effective_cv2_threads)
        except Exception:
            pass

        # 3. Настройка размера LRU-кэша полноразмерных изображений
        try:
            from .image_io import set_pixmap_cache_max_items
            set_pixmap_cache_max_items(profile.pixmap_cache_size)
        except Exception:
            pass

        logger.info(
            "Активирован вычислительный профиль [%s]: %s",
            profile.mode,
            profile.status_bar_text(),
        )
        return profile

    @classmethod
    def get_active_profile(cls) -> ComputeProfile:
        if cls._active_profile is None:
            return cls.apply_profile("auto")
        return cls._active_profile
