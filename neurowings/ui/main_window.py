#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Главное окно приложения (v2.2.0)
"""

import html
import math
import copy
import os
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from urllib.parse import urlparse

from ..core import (
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_MAX_URL, APP_TELEGRAM_LABEL, APP_TELEGRAM_URL, APP_UPDATE_FEED_URL,
    NUM_POINTS,
    COLOR_NORMAL, COLOR_YOLO, COLOR_STAGE1, COLOR_STAGE2, COLOR_GT,
    DEFAULT_POINT_RADIUS, YOLO_TO_WINGSDIG,
    ALLOWED_IMAGE_EXTENSIONS, format_breed_ru,
    WingPoint, BBox, Wing, ImageData, EditMode,
    get_device, load_stage2_model, load_stage2_portable_model, load_subpixel_model,
    TORCH_AVAILABLE, TORCH_IMPORT_ERROR, TORCHVISION_MODELS_AVAILABLE,
    TORCHVISION_MODELS_IMPORT_ERROR
)
from ..core.update_manager import (
    create_windows_update_script,
    is_direct_download_url,
    launch_windows_update_script,
)
from ..core.image_io import read_pixmap, image_size, preload_rgb_parallel
from ..core.project_io import save_project, load_project
from ..core.tps_io import load_tps_into_image, save_tps_from_image
from ..core.pdf_passport import generate_pdf_passport
from ..core.hardware_profiler import HardwareProfiler, POWER_MODES

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem, QListWidget, QListWidgetItem,
    QPushButton, QToolButton, QLabel, QCheckBox, QGroupBox, QComboBox,
    QSplitter, QToolBar, QFileDialog, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QScrollArea, QShortcut, QRadioButton, QButtonGroup, QAction, QTabWidget, QGridLayout,
    QApplication, QMenu, QSizePolicy, QDialog, QDialogButtonBox, QProgressDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QUrl, QThread
from PyQt5.QtGui import QPixmap, QColor, QKeySequence, QPen, QFont, QDesktopServices

from .graphics_items import PointItem, WingLabelItem, BBoxItem, MeasurementLineItem
from .graphics_view import ZoomableGraphicsView
from .analysis_widget import AnalysisWidget
from .graphs_widget import GraphsWidget
from .interpretation_widget import InterpretationWidget, GlobalInterpretationWidget
from .batch_widget import BatchResultsWidget
from .dialogs import PointSettingsDialog
from .wing_guide_widget import WingGuideWidget, BeekeeperGuideDialog

from ..workers import ProcessingWorker, UpdateCheckWorker, UpdateDownloadWorker


class MainWindow(QMainWindow):
    """Главное окно приложения NeuroWings"""

    def __init__(self):
        super().__init__()
        self._gpt_client = None
        self._gpt_model = None
        self._gpt_enabled = False
        self._load_gpt_config()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1500, 950)
        self.setAcceptDrops(True)

        # Данные
        self.images: Dict[str, ImageData] = {}
        self._undo_stack = []
        self.current_image: Optional[ImageData] = None
        self.current_folder: Optional[Path] = None
        self.target_breed: str = "auto"

        # Модели и вычислительный профиль железа
        self.compute_profile = HardwareProfiler.apply_profile("auto")
        self.device = get_device()
        self.model_det = None
        self.model_pose = None
        self.model_stage2 = None
        self.model_stage2_portable = None
        self.model_subpixel = None
        self.single_wing_mode = False
        self.left_collapsed = False
        self.right_collapsed = False
        self._saved_splitter_sizes = None
        self._saved_left_size = 180
        self._saved_right_size = 280
        self._ui_font_px = 13

        # Состояние UI
        self.point_items: List[PointItem] = []
        self.wing_labels = []
        self.bbox_items = []
        self.measurement_lines = []
        self.edit_mode = EditMode.VIEW
        self.selected_wing_idx = -1
        self.adding_points: List[Tuple[float, float]] = []
        self.temp_add_items = []
        self._updating_wings_table = False

        # Настройки точек
        self.point_color = COLOR_NORMAL
        self._custom_point_color_set = False
        self.point_radius = DEFAULT_POINT_RADIUS

        # Флаги отображения (все выключены по умолчанию)
        self.show_gt = False
        self.show_yolo = False
        self.show_stage1 = False
        self.show_stage2 = False
        self.show_bboxes = False
        self.show_measurement_lines = False
        self.expert_mode = False
        self._update_info = None
        self._update_check_worker = None
        self._update_download_worker = None
        self._update_progress_dialog = None
        self._skip_unsaved_prompt = False

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_shortcuts()
        self._apply_screen_adaptation()
        self._apply_light_theme()
        self._show_empty_canvas_hint()
        self._load_models()
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QTimer.singleShot(1500, self._auto_check_for_updates)

    def _setup_ui(self):
        """Настройка пользовательского интерфейса"""
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.update_banner = QWidget()
        self.update_banner.setVisible(False)
        self.update_banner.setStyleSheet(
            "background-color: #fff3cd; border-bottom: 1px solid #e0c36c;"
        )
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_update_banner = QLabel("")
        self.lbl_update_banner.setWordWrap(True)
        banner_layout.addWidget(self.lbl_update_banner, 1)

        self.btn_update_banner = QPushButton("Обновить")
        self.btn_update_banner.clicked.connect(self._start_pending_update)
        banner_layout.addWidget(self.btn_update_banner)

        self.btn_hide_update_banner = QPushButton("Позже")
        self.btn_hide_update_banner.clicked.connect(self._hide_update_banner)
        banner_layout.addWidget(self.btn_hide_update_banner)

        root_layout.addWidget(self.update_banner)

        self.main_splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.main_splitter, 1)

        # ЛЕВАЯ ПАНЕЛЬ - список файлов
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        files_header = QHBoxLayout()
        files_label = QLabel("📁 Файлы")
        files_label.setStyleSheet("font-weight: bold;")
        files_header.addWidget(files_label)
        files_header.addStretch()

        self.btn_select_all = QToolButton()
        self.btn_select_all.setText("✓")
        self.btn_select_all.setToolTip("Выбрать все файлы для пакетной обработки")
        self.btn_select_all.clicked.connect(self._select_all_files)
        files_header.addWidget(self.btn_select_all)

        self.btn_select_none = QToolButton()
        self.btn_select_none.setText("✗")
        self.btn_select_none.setToolTip("Снять выбор со всех файлов")
        self.btn_select_none.clicked.connect(self._deselect_all_files)
        files_header.addWidget(self.btn_select_none)

        left_layout.addLayout(files_header)

        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._on_file_clicked)
        left_layout.addWidget(self.file_list)

        self.lbl_files_stats = QLabel("0 файлов")
        left_layout.addWidget(self.lbl_files_stats)

        self.left_panel.setMaximumWidth(210)
        self.main_splitter.addWidget(self.left_panel)

        # ЦЕНТРАЛЬНАЯ ПАНЕЛЬ
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QTabWidget()

        # Вкладка изображения
        image_tab = QWidget()
        image_layout = QVBoxLayout(image_tab)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView(self.scene, self)
        self.view.point_clicked.connect(self._on_point_clicked)
        self.view.scene_clicked.connect(self._on_scene_clicked)
        self.view.point_moved.connect(self._on_point_moved)
        self.view.bbox_created.connect(self._on_bbox_created)
        self.view.bbox_changed.connect(self._on_bbox_changed)
        self.view.point_delete_requested.connect(self._on_point_delete)
        self.view.bbox_delete_requested.connect(self._on_bbox_delete)
        self.view.wing_reset_requested.connect(self._on_wing_reset_requested)
        self.view.bbox_recognize_requested.connect(self._on_bbox_recognize_requested)
        self.view.setFocusPolicy(Qt.StrongFocus)
        image_layout.addWidget(self.view)

        # Информационная панель
        info_bar = QWidget()
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(10, 3, 10, 3)

        self.lbl_filename = QLabel("Файл: —")
        self.lbl_size = QLabel("Размер: —")
        self.lbl_wings_count = QLabel("Крыльев: 0")
        self.lbl_mode = QLabel("Режим: Просмотр (точки можно двигать мышкой)")

        info_layout.addWidget(self.lbl_filename)
        info_layout.addWidget(QLabel("|"))
        info_layout.addWidget(self.lbl_size)
        info_layout.addWidget(QLabel("|"))
        info_layout.addWidget(self.lbl_wings_count)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_mode)

        image_layout.addWidget(info_bar)
        self.tab_widget.addTab(image_tab, "🖼 Изображение")

        # Вкладка анализа
        self.analysis_widget = AnalysisWidget(self)
        self.analysis_widget.goto_wing_signal.connect(self._goto_wing)
        self.analysis_widget.save_tps_callback = self._save_tps
        self.tab_widget.addTab(self.analysis_widget, "📊 Анализ результатов")

        # Вкладка графиков
        self.graphs_widget = GraphsWidget()
        self.tab_widget.addTab(self.graphs_widget, "📈 Графики")

        # Вкладка сводной таблицы
        self.batch_widget = BatchResultsWidget()
        self.batch_widget.set_refresh_callback(self._refresh_batch_table)
        self.tab_widget.addTab(self.batch_widget, "📋 Сводная таблица")

        # Вкладка интерпретации
        self.interpretation_widget = InterpretationWidget()
        self.interpretation_widget.target_breed_changed.connect(self._on_target_breed_changed)
        self.tab_widget.addTab(self.interpretation_widget, "🐝 Интерпретация")

        # Вкладка общей интерпретации (агрегат по всем фото)
        self.global_interpretation_widget = GlobalInterpretationWidget(title="🌐 Общая интерпретация")
        self.tab_widget.addTab(self.global_interpretation_widget, "🌐 Общая интерпретация")

        self.analysis_widget.set_graphs_widget(self.graphs_widget)
        self._apply_gpt_to_widgets()

        center_layout.addWidget(self.tab_widget)
        self.main_splitter.addWidget(center_widget)

        # ПРАВАЯ ПАНЕЛЬ
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)

        wings_label = QLabel("🦋 Крылья (☑ — учитывать в расчёте)")
        wings_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(wings_label)

        self.wings_table = QTableWidget()
        self.wings_table.setColumnCount(4)
        self.wings_table.setHorizontalHeaderLabels(["№", "Порода", "Кубит. (CI)", "✓"])
        self.wings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.wings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.wings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.wings_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.wings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wings_table.itemClicked.connect(self._on_wing_selected)
        self.wings_table.itemChanged.connect(self._on_wings_table_item_changed)
        right_layout.addWidget(self.wings_table)

        wing_btns_layout = QHBoxLayout()
        self.btn_delete_wing = QPushButton("🗑 Удалить крыло")
        self.btn_delete_wing.clicked.connect(self._delete_selected_wing)
        wing_btns_layout.addWidget(self.btn_delete_wing)

        self.btn_reset_wing = QPushButton("🔄 Сбросить точки")
        self.btn_reset_wing.setToolTip("Вернуть точки выбранного крыла к исходным (нейросеть / TPS)")
        self.btn_reset_wing.clicked.connect(self._reset_selected_wing)
        wing_btns_layout.addWidget(self.btn_reset_wing)
        right_layout.addLayout(wing_btns_layout)

        # Схема точек крыла (1-8) для пасечника
        self.wing_guide_group = QGroupBox("📌 Схема точек крыла (1–8)")
        wg_layout = QVBoxLayout(self.wing_guide_group)
        wg_layout.setContentsMargins(4, 6, 4, 4)
        self.wing_guide = WingGuideWidget(self)
        wg_layout.addWidget(self.wing_guide)
        right_layout.addWidget(self.wing_guide_group)

        # Группа вспомогательных элементов
        auxiliary_group = QGroupBox("🔧 Отображение на скане")
        aux_layout = QVBoxLayout(auxiliary_group)

        self.chk_bbox = QCheckBox("🟠 Показывать рамки крыльев")
        self.chk_bbox.setChecked(False)
        self.chk_bbox.toggled.connect(lambda checked: self._on_display_toggle(checked))
        aux_layout.addWidget(self.chk_bbox)

        self.chk_measurement = QCheckBox("📏 Показывать линии промеров")
        self.chk_measurement.setChecked(False)
        self.chk_measurement.toggled.connect(lambda checked: self._on_display_toggle(checked))
        aux_layout.addWidget(self.chk_measurement)

        self.chk_gt = QCheckBox("🟢 Показать исходные точки TPS")
        self.chk_gt.setChecked(False)
        self.chk_gt.toggled.connect(lambda checked: self._on_display_toggle(checked))
        aux_layout.addWidget(self.chk_gt)

        right_layout.addWidget(auxiliary_group)

        # Группа экспертного отображения моделей (скрыта по умолчанию)
        self.display_group = QGroupBox("👁 Сравнение моделей (эксперт)")
        display_layout = QVBoxLayout(self.display_group)

        self.chk_yolo_raw = QCheckBox("🔴 Модель 1 (YOLO)")
        self.chk_yolo_raw.setChecked(False)
        self.chk_yolo_raw.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_yolo_raw)

        self.chk_stage1 = QCheckBox("🔵 Модель 2 (Stage1)")
        self.chk_stage1.setChecked(False)
        self.chk_stage1.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_stage1)

        self.chk_stage2 = QCheckBox("🟣 Модель 2 с уточнением")
        self.chk_stage2.setChecked(False)
        self.chk_stage2.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_stage2)

        self.display_group.setVisible(False)
        right_layout.addWidget(self.display_group)

        # Группа выбора модели точек (скрыта по умолчанию, доступна в экспертном режиме)
        self.point_selection_group = QGroupBox("Модель точек")
        sel_layout = QGridLayout(self.point_selection_group)
        sel_layout.setSpacing(2)

        sel_layout.addWidget(QLabel("#"), 0, 0)

        btn_all_yolo = QPushButton("🔴")
        btn_all_yolo.setToolTip("Переключить все точки на YOLO")
        btn_all_yolo.setMaximumWidth(30)
        btn_all_yolo.clicked.connect(lambda: self._set_all_points_model('yolo'))
        sel_layout.addWidget(btn_all_yolo, 0, 1)

        btn_all_stage1 = QPushButton("🔵")
        btn_all_stage1.setToolTip("Переключить все точки на Stage1")
        btn_all_stage1.setMaximumWidth(30)
        btn_all_stage1.clicked.connect(lambda: self._set_all_points_model('stage1'))
        sel_layout.addWidget(btn_all_stage1, 0, 2)

        btn_all_stage2 = QPushButton("🟣")
        btn_all_stage2.setToolTip("Переключить все точки на Stage2")
        btn_all_stage2.setMaximumWidth(30)
        btn_all_stage2.clicked.connect(lambda: self._set_all_points_model('stage2'))
        sel_layout.addWidget(btn_all_stage2, 0, 3)

        self.point_model_groups: List[QButtonGroup] = []
        for idx in range(NUM_POINTS):
            lbl = QLabel(str(idx + 1))
            sel_layout.addWidget(lbl, idx + 1, 0)

            group = QButtonGroup(self)

            rb_yolo = QRadioButton()
            rb_yolo.setProperty('model_type', 'yolo')
            rb_yolo.setProperty('point_idx', idx)
            group.addButton(rb_yolo)
            sel_layout.addWidget(rb_yolo, idx + 1, 1)

            rb_stage1 = QRadioButton()
            rb_stage1.setProperty('model_type', 'stage1')
            rb_stage1.setProperty('point_idx', idx)
            group.addButton(rb_stage1)
            sel_layout.addWidget(rb_stage1, idx + 1, 2)

            rb_stage2 = QRadioButton()
            rb_stage2.setProperty('model_type', 'stage2')
            rb_stage2.setProperty('point_idx', idx)
            group.addButton(rb_stage2)
            sel_layout.addWidget(rb_stage2, idx + 1, 3)

            rb_yolo.setChecked(True)
            group.buttonClicked.connect(self._on_point_model_changed)
            self.point_model_groups.append(group)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(4)
        btn_apply_current = QPushButton("К фото")
        btn_apply_current.setToolTip("Применить выбор моделей точек ко всем крыльям текущего фото")
        btn_apply_current.setMaximumWidth(70)
        btn_apply_current.setMinimumHeight(22)
        btn_apply_current.clicked.connect(lambda: self._apply_point_selection(scope="current"))
        actions_layout.addWidget(btn_apply_current)

        btn_apply_all = QPushButton("Ко всем")
        btn_apply_all.setToolTip("Применить выбор моделей точек ко всем открытым фото")
        btn_apply_all.setMaximumWidth(70)
        btn_apply_all.setMinimumHeight(22)
        btn_apply_all.clicked.connect(lambda: self._apply_point_selection(scope="all"))
        actions_layout.addWidget(btn_apply_all)

        sel_layout.addLayout(actions_layout, NUM_POINTS + 2, 1, 1, 3)
        self.point_selection_group.setVisible(False)
        right_layout.addWidget(self.point_selection_group)

        right_layout.addStretch()

        right_content = self.right_panel
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_content)
        right_scroll.setMinimumWidth(295)
        right_scroll.setMaximumWidth(375)
        self.right_panel = right_scroll
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setSizes([180, 920, 300])
        self._saved_splitter_sizes = self.main_splitter.sizes()
        if len(self._saved_splitter_sizes) >= 1:
            self._saved_left_size = self._saved_splitter_sizes[0]
        if len(self._saved_splitter_sizes) >= 3:
            self._saved_right_size = self._saved_splitter_sizes[2]

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.right_panel.setVisible(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.lbl_hardware_status = QLabel()
        self.lbl_hardware_status.setStyleSheet(
            "color: #1864ab; font-weight: bold; padding: 0 8px;"
        )
        self._update_hardware_status_label()
        self.statusBar().addPermanentWidget(self.lbl_hardware_status)

    def _setup_menu(self):
        """Настройка меню"""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Файл")
        file_menu.addAction("📂 Открыть скан/фото...", self._open_files, "Ctrl+O")
        file_menu.addAction("📁 Открыть папку со сканами...", self._open_folder, "Ctrl+Shift+O")
        file_menu.addSeparator()
        file_menu.addAction("💾 Сохранить TPS", self._save_current, "Ctrl+S")
        file_menu.addAction("💾 Сохранить все TPS", self._save_all)
        file_menu.addSeparator()
        file_menu.addAction("📄 Сохранить PDF-Паспорт семьи...", self._export_pdf, "Ctrl+P")
        file_menu.addAction("📊 Экспорт в Excel...", self._export_excel)
        file_menu.addSeparator()
        file_menu.addAction("Выход", self.close)

        edit_menu = menubar.addMenu("Правка")
        edit_menu.addAction("Отменить изменение", self._undo_edit, "Ctrl+Z")
        edit_menu.addAction("Сбросить точки выбранного крыла", self._reset_selected_wing)
        edit_menu.addAction("Удалить крыло", self._delete_selected_wing, "Delete")
        edit_menu.addSeparator()
        edit_menu.addAction("🔄 Повернуть скан на 90° вправо", self._rotate_current_image_cw, "Ctrl+R")
        edit_menu.addAction("🔄 Повернуть скан на 180°", self._rotate_current_image_180)
        edit_menu.addAction("↔ Отразить скан по горизонтали", self._flip_current_image_h)

        view_menu = menubar.addMenu("Вид")
        view_menu.addAction("Увеличить", lambda: self._zoom(1.25))
        view_menu.addAction("Уменьшить", lambda: self._zoom(0.8))
        view_menu.addAction("По размеру", self._fit_view)
        view_menu.addAction("1:1", self._zoom_100)
        view_menu.addSeparator()
        view_menu.addAction("Настройки точек...", self._show_point_settings)
        view_menu.addSeparator()
        self.act_expert_mode = QAction("🔬 Режим сравнения моделей (экспертный)", self)
        self.act_expert_mode.setCheckable(True)
        self.act_expert_mode.setChecked(False)
        self.act_expert_mode.toggled.connect(self._toggle_expert_mode)
        view_menu.addAction(self.act_expert_mode)
        view_menu.addAction("🤖 Настройки ИИ (OpenAI GPT)...", self._show_gpt_settings)

        help_menu = menubar.addMenu("Справка")
        help_menu.addAction("❓ Памятка пчеловода (Как пользоваться)", self._show_beekeeper_guide, "F1")
        help_menu.addSeparator()
        help_menu.addAction("Проверить обновление", lambda: self._check_for_updates(manual=True))
        help_menu.addSeparator()
        help_menu.addAction("О программе", self._show_about)

    def _setup_toolbar(self):
        """Настройка панели инструментов"""
        toolbar = QToolBar("Инструменты")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction("📂 Открыть скан/фото", self._open_files)
        toolbar.addAction("📁 Открыть папку", self._open_folder)
        toolbar.addSeparator()

        toolbar.addAction("◀", self._prev_file)
        toolbar.addAction("▶", self._next_file)
        toolbar.addSeparator()

        self.act_mode_view = QAction("👆 Просмотр", self)
        self.act_mode_view.setCheckable(True)
        self.act_mode_view.setChecked(True)
        self.act_mode_view.triggered.connect(lambda: self._set_edit_mode(EditMode.VIEW))
        toolbar.addAction(self.act_mode_view)

        self.act_mode_edit = QAction("✎ Редакт.", self)
        self.act_mode_edit.setCheckable(True)
        self.act_mode_edit.triggered.connect(lambda: self._set_edit_mode(EditMode.EDIT))
        toolbar.addAction(self.act_mode_edit)

        self.act_mode_add = QAction("➕ Точки", self)
        self.act_mode_add.setCheckable(True)
        self.act_mode_add.triggered.connect(lambda: self._set_edit_mode(EditMode.ADD))
        toolbar.addAction(self.act_mode_add)

        self.act_mode_bbox = QAction("⬜ Рамка", self)
        self.act_mode_bbox.setCheckable(True)
        self.act_mode_bbox.triggered.connect(lambda: self._set_edit_mode(EditMode.BBOX))
        toolbar.addAction(self.act_mode_bbox)

        toolbar.addSeparator()
        toolbar.addAction("🔍+", lambda: self._zoom(1.25))
        toolbar.addAction("🔍-", lambda: self._zoom(0.8))
        act_rot90 = toolbar.addAction("🔄 90°", self._rotate_current_image_cw)
        act_rot90.setToolTip("Повернуть текущий скан на 90° по часовой стрелке (Ctrl+R)")
        act_rot180 = toolbar.addAction("🔄 180°", self._rotate_current_image_180)
        act_rot180.setToolTip("Развернуть текущий скан на 180° (если крылья отсканированы вверх ногами или влево)")
        act_flip = toolbar.addAction("↔ Отразить", self._flip_current_image_h)
        act_flip.setToolTip("Зеркально отразить текущий скан по горизонтали")

        toolbar.addSeparator()
        toolbar.addAction("⚡ Обработать", self._process_smart)
        toolbar.addAction("💾 Сохранить", self._save_current)
        toolbar.addAction("📄 PDF-Паспорт", self._export_pdf)
        toolbar.addAction("❓ Как пользоваться", self._show_beekeeper_guide)

        act_minimap = toolbar.addAction("🗺 Обзор", self._toggle_minimap)
        act_minimap.setToolTip("Показать/скрыть миникарту навигации (M)")
        act_minimap.setShortcut("M")

        toolbar.addSeparator()
        toolbar.addAction("⬅ панель", self._toggle_left_panel)
        toolbar.addAction("панель ➡", self._toggle_right_panel)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.chk_single_wing = QCheckBox("1 фото = 1 крыло (микроскоп)")
        self.chk_single_wing.setToolTip("Объединить все открытые одиночные фото крыльев в одну общую пробу улья")
        self.chk_single_wing.setChecked(False)
        self.chk_single_wing.toggled.connect(self._toggle_single_wing_mode)
        toolbar.addWidget(self.chk_single_wing)

        toolbar.addSeparator()
        lbl_power = QLabel(" Мощность: ")
        lbl_power.setStyleSheet("font-weight: bold; color: #222222;")
        toolbar.addWidget(lbl_power)

        self.combo_power_mode = QComboBox()
        for mode_key, mode_label in POWER_MODES.items():
            self.combo_power_mode.addItem(mode_label, mode_key)
        self.combo_power_mode.setCurrentIndex(0)
        self.combo_power_mode.setToolTip(self.compute_profile.detailed_tooltip_ru())
        self.combo_power_mode.currentIndexChanged.connect(self._on_power_mode_changed)
        toolbar.addWidget(self.combo_power_mode)

    def _on_power_mode_changed(self, idx: int):
        mode_key = self.combo_power_mode.itemData(idx) or "auto"
        self.compute_profile = HardwareProfiler.apply_profile(mode_key)
        self.combo_power_mode.setToolTip(self.compute_profile.detailed_tooltip_ru())
        self._update_hardware_status_label()
        self.statusBar().showMessage(
            f"Активирован режим: {self.compute_profile.status_bar_text()}"
        )

    def _update_hardware_status_label(self):
        if hasattr(self, "lbl_hardware_status") and self.lbl_hardware_status is not None:
            self.lbl_hardware_status.setText(self.compute_profile.status_bar_text())
            self.lbl_hardware_status.setToolTip(self.compute_profile.detailed_tooltip_ru())

    def _apply_screen_adaptation(self):
        """
        Адаптация геометрии окна, ширины боковых панелей и шрифта под разрешение монитора —
        от маленьких ноутбуков (1366x768) до сверхшироких экранов 5K2K (5160x2160 @ 165 Гц).
        """
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            geom = screen.availableGeometry()
            sw, sh = geom.width(), geom.height()
            if sw <= 0 or sh <= 0:
                return

            if sw >= 4400 or sh >= 2000:
                # Сверхширокие и 5K2K экраны (например, 5160x2160)
                self._ui_font_px = 15
                win_w = min(int(sw * 0.86), 3840)
                win_h = min(int(sh * 0.88), 1920)
                left_w, right_min, right_max = 300, 380, 480
            elif sw >= 3000 or sh >= 1500:
                # 4K / UWQHD (3440x1440, 3840x2160)
                self._ui_font_px = 14
                win_w = min(int(sw * 0.88), 3100)
                win_h = min(int(sh * 0.88), 1650)
                left_w, right_min, right_max = 260, 340, 430
            elif sw <= 1440 or sh <= 850:
                # Компактные ноутбуки (1366x768, 1440x900)
                self._ui_font_px = 12
                win_w = max(1024, int(sw * 0.96))
                win_h = max(680, int(sh * 0.94))
                left_w, right_min, right_max = 175, 255, 315
            else:
                # Стандартные FullHD / QHD (1920x1080, 2560x1440)
                self._ui_font_px = 13
                win_w = min(int(sw * 0.90), 2100)
                win_h = min(int(sh * 0.90), 1250)
                left_w, right_min, right_max = 220, 300, 385

            self.resize(win_w, win_h)
            self.left_panel.setMaximumWidth(left_w + 40)
            self.right_panel.setMinimumWidth(right_min)
            self.right_panel.setMaximumWidth(right_max)
            center_w = max(600, win_w - left_w - right_min)
            self.main_splitter.setSizes([left_w, center_w, right_min])
            self._saved_splitter_sizes = self.main_splitter.sizes()
            self._saved_left_size = left_w
            self._saved_right_size = right_min
        except Exception:
            pass

    def _setup_shortcuts(self):
        """Настройка горячих клавиш"""
        QShortcut(QKeySequence("V"), self, lambda: self._set_edit_mode(EditMode.VIEW))
        QShortcut(QKeySequence("E"), self, lambda: self._set_edit_mode(EditMode.EDIT))
        QShortcut(QKeySequence("A"), self, lambda: self._set_edit_mode(EditMode.ADD))
        QShortcut(QKeySequence("B"), self, lambda: self._set_edit_mode(EditMode.BBOX))
        QShortcut(QKeySequence("Space"), self, self._process_smart)
        QShortcut(QKeySequence("PageUp"), self, self._prev_file)
        QShortcut(QKeySequence("PageDown"), self, self._next_file)
        QShortcut(QKeySequence("Escape"), self, self._cancel_action)
        QShortcut(QKeySequence("F"), self, self._fit_view)

    def _toggle_expert_mode(self, checked: bool):
        self.expert_mode = bool(checked)
        self.display_group.setVisible(self.expert_mode)
        self.point_selection_group.setVisible(self.expert_mode)

    def _show_beekeeper_guide(self):
        dlg = BeekeeperGuideDialog(self)
        dlg.exec_()

    def _show_empty_canvas_hint(self):
        """Показать дружелюбную подсказку на пустом холсте."""
        if self.current_image is not None:
            return
        self.scene.clear()
        text_item = QGraphicsTextItem()
        text_item.setHtml(
            "<div style='background-color:#ffffff; border:2px dashed #74c0fc; border-radius:12px; "
            "padding:24px; text-align:center; color:#1864ab; font-family:Arial;'>"
            "<h2 style='margin:0 0 10px 0;'>🐝 Добро пожаловать в «НейроКрылья»!</h2>"
            "<p style='font-size:15px; color:#222222;'>"
            "📂 Нажмите <b>«Открыть скан/фото»</b> (или <b>«Открыть папку»</b>) на верхней панели<br>"
            "или просто <b>перетащите изображение крыльев мышкой</b> прямо в это окно."
            "</p>"
            "<p style='font-size:13px; color:#495057;'>"
            "Поддерживаются форматы: <b>JPG, PNG, TIF, TIFF, BMP, WEBP</b> + файлы разметки <b>TPS</b>.<br>"
            "После загрузки нажмите <b>«⚡ Обработать»</b> (или клавишу <b>Пробел</b>)."
            "</p></div>"
        )
        text_item.setTextWidth(620)
        self.scene.addItem(text_item)
        self.scene.setSceneRect(text_item.boundingRect().adjusted(-40, -40, 40, 40))

    # --- Drag & Drop ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_dir() or p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS or p.suffix.lower() == ".tps":
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            return
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        folders = [p for p in paths if p.is_dir()]
        if folders:
            self.current_folder = folders[0]
            self._load_folder()
            event.acceptProposedAction()
            return

        img_files = []
        for p in paths:
            if p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS and p.exists():
                img_files.append(p)
            elif p.suffix.lower() == ".tps" and p.exists():
                for ext in ALLOWED_IMAGE_EXTENSIONS:
                    cand = p.with_suffix(ext)
                    if cand.exists():
                        img_files.append(cand)
                        break
                    cand_up = p.with_suffix(ext.upper())
                    if cand_up.exists():
                        img_files.append(cand_up)
                        break
        if img_files:
            self._load_file_paths(img_files)
            event.acceptProposedAction()

    def _on_tab_changed(self, index):
        """Обработка смены вкладки"""
        total = sum(self.main_splitter.sizes()) or (self._saved_left_size + 900 + self._saved_right_size)
        if index == 0:
            left_size = 0 if self.left_collapsed else self._saved_left_size
            right_size = 0 if self.right_collapsed else self._saved_right_size
            center_size = max(0, total - left_size - right_size)
            self.left_panel.setVisible(not self.left_collapsed)
            self.right_panel.setVisible(not self.right_collapsed)
            self.main_splitter.setSizes([left_size, center_size, right_size])
        else:
            left_size = 0 if self.left_collapsed else self._saved_left_size
            center_size = max(0, total - left_size)
            self.left_panel.setVisible(not self.left_collapsed)
            self.right_panel.setVisible(False)
            self.main_splitter.setSizes([left_size, center_size, 0])

        current_w = self.tab_widget.widget(index)
        if current_w is self.graphs_widget:
            self.graphs_widget.flush_pending()
        elif current_w is self.global_interpretation_widget:
            self._update_global_interpretation(force=True)

    def _on_target_breed_changed(self, breed_key: str):
        self.target_breed = breed_key or "auto"
        self.analysis_widget.target_breed = self.target_breed
        self._update_analysis_widget()

    def _apply_light_theme(self):
        """Применить светлую тему оформления (с адаптивным размером шрифта под разрешение монитора)"""
        base_px = getattr(self, "_ui_font_px", 13)
        style = """
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                color: #222222;
                font-size: __BASE_PX__px;
            }
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f9f9f9;
                gridline-color: #dddddd;
                border: 1px solid #cccccc;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                color: #222222;
                padding: 5px;
                border: 1px solid #cccccc;
                font-weight: bold;
            }
            QPushButton, QToolButton {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 5px 10px;
                color: #222222;
            }
            QPushButton:hover, QToolButton:hover {
                background-color: #e8f4fd;
                border-color: #4a90e2;
            }
            QPushButton:pressed, QToolButton:pressed {
                background-color: #d0e8f7;
            }
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QLabel {
                color: #222222;
            }
            QCheckBox {
                color: #222222;
            }
            QRadioButton {
                color: #222222;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #222222;
                border: 1px solid #cccccc;
                border-bottom: none;
                padding: 8px 15px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #e8f4fd;
            }
            QMenuBar {
                background-color: #f0f0f0;
                color: #222222;
            }
            QMenuBar::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QMenu {
                background-color: #ffffff;
                color: #222222;
                border: 1px solid #cccccc;
            }
            QMenu::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QToolBar {
                background-color: #f0f0f0;
                border: none;
                spacing: 3px;
            }
            QStatusBar {
                background-color: #f0f0f0;
                color: #222222;
            }
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 3px;
                text-align: center;
                background-color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #4a90e2;
            }
        """.replace("__BASE_PX__", str(base_px))
        self.setStyleSheet(style)

    def _load_models(self):
        """Загрузка моделей"""
        if not TORCH_AVAILABLE:
            self.statusBar().showMessage(
                "⚠️ Модуль нейросетевого распознавания не загружен. Доступна работа с готовыми TPS и ручная разметка."
            )
            return

        try:
            from ultralytics import YOLO

            app_dir = Path(__file__).resolve().parent.parent
            project_root = app_dir.parent

            base_dirs = []
            runtime_dir = getattr(sys, "_MEIPASS", "")
            if runtime_dir:
                base_dirs.append(Path(runtime_dir))
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).resolve().parent
                base_dirs.extend([exe_dir, exe_dir / "_internal"])
            base_dirs.extend([project_root, app_dir])

            search_dirs = []
            seen_dirs = set()
            for base_dir in base_dirs:
                for candidate in (base_dir / "models", base_dir, base_dir / "neurowings"):
                    candidate_key = str(candidate).lower()
                    if candidate_key in seen_dirs:
                        continue
                    seen_dirs.add(candidate_key)
                    search_dirs.append(candidate)

            for name in ["yolo_detect_best.pt", "detect_best.pt"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        from ..core.models import verify_model
                        verify_model(path)
                        self.model_det = YOLO(str(path))
                        break
                if self.model_det:
                    break

            for name in ["yolo_pose_best.pt", "pose_best.pt", "best.pt"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        from ..core.models import verify_model
                        verify_model(path)
                        self.model_pose = YOLO(str(path))
                        break
                if self.model_pose:
                    break

            for search_dir in search_dirs:
                s2_path = search_dir / "stage2_best.pth"
                if s2_path.exists() and self.model_stage2 is None:
                    self.model_stage2 = load_stage2_model(s2_path, self.device)
                sp_path = search_dir / "subpixel_best.pth"
                if sp_path.exists() and self.model_subpixel is None:
                    self.model_subpixel = load_subpixel_model(sp_path, self.device)
                port_path = search_dir / "stage2_portable.pth"
                if port_path.exists() and self.model_stage2_portable is None:
                    self.model_stage2_portable = load_stage2_portable_model(port_path, self.device)

            if self.model_det and self.model_pose:
                self.statusBar().showMessage(
                    "✅ Программа готова к работе. Откройте скан крыльев и нажмите «⚡ Обработать»"
                )
            else:
                self.statusBar().showMessage(
                    "✅ Программа готова к работе (режим TPS / ручной разметки). Откройте скан или папку."
                )

        except ImportError:
            self.statusBar().showMessage(
                "✅ Программа готова к работе. Откройте скан крыльев или файл TPS."
            )
        except Exception as e:
            print(f"Ошибка загрузки моделей: {e}")
            self.statusBar().showMessage(
                "✅ Программа готова к работе. Откройте скан крыльев."
            )

    def _show_point_settings(self):
        """Показать настройки точек"""
        dialog = PointSettingsDialog(self.point_radius, self.point_color, self)
        if dialog.exec_():
            new_radius, new_color = dialog.get_settings()
            if new_color != self.point_color:
                self._custom_point_color_set = True
            self.point_radius = new_radius
            self.point_color = new_color
            self._update_display()

    @staticmethod
    def _find_tps_for_image(img_path: Path) -> Optional[Path]:
        """Найти парный .tps/.TPS файл без учёта регистра расширения."""
        for suffix in ('.tps', '.TPS', '.Tps'):
            cand = img_path.with_suffix(suffix)
            if cand.exists():
                return cand
        return None

    def _open_files(self):
        """Открыть один или несколько файлов сканов/фото"""
        exts = " ".join(f"*{e} *{e.upper()}" for e in ALLOWED_IMAGE_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите скан или фото крыльев",
            str(self.current_folder or Path.home()),
            f"Изображения крыльев ({exts});;Все файлы (*.*)"
        )
        if files:
            paths = [Path(f) for f in files if Path(f).exists()]
            if paths:
                self.current_folder = paths[0].parent
                self._load_file_paths(paths)

    def _open_folder(self):
        """Открыть папку с изображениями"""
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку со сканами крыльев")
        if folder:
            self.current_folder = Path(folder)
            self._load_folder()

    def _load_folder(self):
        """Загрузить файлы из папки (все форматы без учёта регистра)"""
        if not self.current_folder:
            return
        images = [
            p for p in self.current_folder.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
        ]
        self._load_file_paths(sorted(images, key=lambda p: p.name.casefold()))

    def _load_file_paths(self, image_paths: List[Path]):
        """Загрузить список путей к изображениям"""
        if not self._confirm_close():
            return
        self._cancel_adding()
        self.current_image = None
        self.scene.clear()
        self._undo_stack.clear()
        self.images.clear()
        self.file_list.clear()

        seen = set()
        unique_paths = []
        for p in image_paths:
            key = str(p.resolve()) if p.exists() else str(p)
            if key not in seen:
                seen.add(key)
                unique_paths.append(p)

        for idx, img_path in enumerate(unique_paths, start=1):
            img_data = ImageData(path=img_path)
            self.images[str(img_path)] = img_data

            tps_path = self._find_tps_for_image(img_path)
            if tps_path is not None:
                self._load_tps_for_image(img_data, tps_path)

            has_data = "✓" if img_data.wings else "○"
            item = QListWidgetItem(f"{has_data} {idx}) {img_path.name}")
            item.setData(Qt.UserRole, str(img_path))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.file_list.addItem(item)

        self._update_files_stats()
        self.batch_widget.update_batch_results(self.images)

        if self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)
            self._load_current_image()
            # На компьютерах с большим объёмом ОЗУ фоново прогреваем кэш сканов папки
            if (
                len(unique_paths) > 1
                and getattr(self.compute_profile, "preload_folder_in_ram", False)
                and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
            ):
                import threading
                preload_targets = unique_paths[1 : max(2, self.compute_profile.pixmap_cache_size)]
                threading.Thread(
                    target=preload_rgb_parallel,
                    args=(preload_targets, self.compute_profile.io_workers),
                    daemon=True,
                ).start()
        else:
            self._show_empty_canvas_hint()

    def _load_tps_for_image(self, img_data: ImageData, tps_path: Path):
        """Загрузить TPS файл (через tps_io)"""
        try:
            load_tps_into_image(img_data, tps_path)
            restored_project = load_project(img_data, tps_path)
            if not restored_project:
                for wing in img_data.wings:
                    wing.point_sources = ['gt'] * NUM_POINTS
            img_data.is_processed = True
            img_data.analyze_all_wings()
        except Exception as e:
            print(f"Ошибка TPS: {e}")

    def _on_file_clicked(self, item):
        """Обработка клика по файлу"""
        self._load_current_image()

    def _load_current_image(self):
        """Загрузить текущее изображение"""
        item = self.file_list.currentItem()
        if not item:
            return

        path = item.data(Qt.UserRole)
        if path not in self.images:
            return

        self.current_image = self.images[path]

        pixmap = read_pixmap(path)
        self.current_image.width = pixmap.width()
        self.current_image.height = pixmap.height()

        self._cancel_adding()
        self.selected_wing_idx = -1
        self.scene.clear()
        self.point_items.clear()
        self.wing_labels.clear()
        self.bbox_items.clear()
        self.measurement_lines.clear()

        pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(pixmap_item)
        self.scene.setSceneRect(pixmap_item.boundingRect())

        self.current_image.analyze_all_wings()

        self._update_display()
        self.view.fit_in_view()

        self._update_analysis_widget()
        self._update_interpretation_widgets()

    def _transform_current_image_orientation(self, mode: str):
        """
        Повернуть или отразить текущий файл изображения на диске (с пересчётом координат точек и рамок).
        mode: 'cw90' (90° по часовой), 'rot180' (180°), 'fliph' (зеркально по горизонтали).
        """
        if not self.current_image or not self.current_image.path:
            self.statusBar().showMessage("Сначала откройте и выберите изображение в списке слева")
            return
        img_path = Path(self.current_image.path)
        if not img_path.exists():
            return

        try:
            from PIL import Image, ImageOps
            import tempfile

            with Image.open(img_path) as im:
                im = ImageOps.exif_transpose(im)
                old_w, old_h = im.size
                if mode == "cw90":
                    im_out = im.transpose(Image.Transpose.ROTATE_270)
                    label_ru = "повёрнуто на 90° вправо"
                elif mode == "rot180":
                    im_out = im.transpose(Image.Transpose.ROTATE_180)
                    label_ru = "развёрнуто на 180°"
                elif mode == "fliph":
                    im_out = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    label_ru = "отражено по горизонтали"
                else:
                    return

                suffix = img_path.suffix or ".jpg"
                fd, tmp_path = tempfile.mkstemp(prefix=img_path.name + ".", suffix=suffix, dir=img_path.parent)
                os.close(fd)
                try:
                    save_kwargs = {"quality": 95} if suffix.lower() in (".jpg", ".jpeg") else {}
                    im_out.save(tmp_path, **save_kwargs)
                    os.replace(tmp_path, img_path)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            def _map_xy(x: float, y: float):
                if mode == "cw90":
                    return float(old_h - y), float(x)
                if mode == "rot180":
                    return float(old_w - x), float(old_h - y)
                return float(old_w - x), float(y)

            for wing in self.current_image.wings:
                for attr in ("points", "points_yolo", "points_stage1", "points_stage2", "points_gt"):
                    pts_list = getattr(wing, attr, None)
                    if pts_list:
                        for pt in pts_list:
                            pt.x, pt.y = _map_xy(pt.x, pt.y)
                if wing.bbox is not None:
                    bx1, by1 = _map_xy(wing.bbox.x1, wing.bbox.y1)
                    bx2, by2 = _map_xy(wing.bbox.x2, wing.bbox.y2)
                    wing.bbox.x1 = min(bx1, bx2)
                    wing.bbox.y1 = min(by1, by2)
                    wing.bbox.x2 = max(bx1, bx2)
                    wing.bbox.y2 = max(by1, by2)

            self.current_image.is_modified = True
            self._load_current_image()
            self.statusBar().showMessage(
                f"Изображение {img_path.name} {label_ru}. Нажмите «⚡ Обработать» для распознавания крыльев."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Поворот изображения", f"Не удалось повернуть изображение:\n{exc}")

    def _rotate_current_image_cw(self):
        self._transform_current_image_orientation("cw90")

    def _rotate_current_image_180(self):
        self._transform_current_image_orientation("rot180")

    def _flip_current_image_h(self):
        self._transform_current_image_orientation("fliph")

    def _prev_file(self):
        """Предыдущий файл"""
        row = self.file_list.currentRow()
        if row > 0:
            self.file_list.setCurrentRow(row - 1)
            self._load_current_image()

    def _next_file(self):
        """Следующий файл"""
        row = self.file_list.currentRow()
        if row < self.file_list.count() - 1:
            self.file_list.setCurrentRow(row + 1)
            self._load_current_image()

    def _select_all_files(self):
        """Выбрать все файлы"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Checked)

    def _deselect_all_files(self):
        """Снять выбор со всех файлов"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Unchecked)

    def _update_files_stats(self):
        """Обновить статистику файлов"""
        total = self.file_list.count()
        with_data = sum(1 for d in self.images.values() if d.wings)
        self.lbl_files_stats.setText(f"Готово: {with_data} из {total}")

    def _refresh_batch_table(self):
        """Обновить сводную таблицу"""
        for img_data in self.images.values():
            if img_data.wings:
                self.analysis_widget.calculate_analysis_results(img_data, target_breed=self.target_breed)
        self.batch_widget.update_batch_results(self.images)

    def _on_display_toggle(self, checked):
        """Переключение отображения"""
        self.show_gt = self.chk_gt.isChecked()
        self.show_yolo = self.chk_yolo_raw.isChecked()
        self.show_stage1 = self.chk_stage1.isChecked()
        self.show_stage2 = self.chk_stage2.isChecked()
        self.show_bboxes = self.chk_bbox.isChecked()
        self.show_measurement_lines = self.chk_measurement.isChecked()

        if self.current_image:
            self._update_display()

    def _on_point_model_changed(self, button):
        """Изменение модели для точки"""
        if not self.current_image:
            return

        point_idx = button.property('point_idx')
        model_type = button.property('model_type')

        for wing in self.current_image.wings:
            if point_idx < len(wing.point_sources):
                if model_type in ("yolo", "stage1", "stage2") and len(getattr(wing, "points_" + model_type)) != NUM_POINTS:
                    self.statusBar().showMessage("У выбранной модели нет результата; сохранён текущий источник")
                    continue
                wing.point_sources[point_idx] = model_type

        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()

    def _get_point_model_selection(self):
        selection = []
        for group in self.point_model_groups:
            checked = group.checkedButton()
            selection.append(checked.property('model_type') if checked else 'stage2')
        return selection

    def _apply_point_selection(self, scope: str):
        selection = self._get_point_model_selection()
        if scope == "all":
            targets = list(self.images.values())
        else:
            targets = [self.current_image] if self.current_image else []

        for img_data in targets:
            if not img_data or not img_data.wings:
                continue
            for wing in img_data.wings:
                for idx, model_type in enumerate(selection):
                    if idx < len(wing.point_sources):
                        if model_type in ("yolo", "stage1", "stage2") and len(getattr(wing, "points_" + model_type)) != NUM_POINTS:
                            self.statusBar().showMessage("У выбранной модели нет результата; сохранён текущий источник")
                            continue
                        wing.point_sources[idx] = model_type
            img_data.is_modified = True
            img_data.analyze_all_wings()

        if self.current_image:
            self._update_display()
        self._update_analysis_widget()
        self.batch_widget.update_batch_results(self.images)
        self._update_interpretation_widgets()

    def _set_all_points_model(self, model_type: str):
        """Переключить все точки на указанную модель"""
        if not self.current_image or not self.current_image.wings:
            return

        selected_wing_idx = self.wings_table.currentRow()
        if selected_wing_idx < 0 or selected_wing_idx >= len(self.current_image.wings):
            wings_to_update = self.current_image.wings
        else:
            wings_to_update = [self.current_image.wings[selected_wing_idx]]

        for wing in wings_to_update:
            for point_idx in range(NUM_POINTS):
                if point_idx < len(wing.point_sources):
                    if model_type in ("yolo", "stage1", "stage2") and len(getattr(wing, "points_" + model_type)) != NUM_POINTS:
                        self.statusBar().showMessage("У выбранной модели нет результата; сохранён текущий источник")
                        continue
                    wing.point_sources[point_idx] = model_type

        for point_idx, group in enumerate(self.point_model_groups):
            for button in group.buttons():
                if button.property('model_type') == model_type:
                    button.setChecked(True)
                    break

        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()

    def _update_display(self):
        """Обновить отображение на сцене"""
        if not self.current_image:
            return

        for item in self.point_items:
            self.scene.removeItem(item)
        self.point_items.clear()

        for label in self.wing_labels:
            self.scene.removeItem(label)
        self.wing_labels.clear()

        for bbox in self.bbox_items:
            self.scene.removeItem(bbox)
        self.bbox_items.clear()

        for line in self.measurement_lines:
            self.scene.removeItem(line)
        self.measurement_lines.clear()

        # Размер точек строго соответствует настройке (по умолчанию radius=1 px -> диаметр 2 px),
        # чтобы точки не перекрывали перекрестья жилок крыла.
        max_img_dim = max(int(self.current_image.width or 0), int(self.current_image.height or 0), 1000)
        scan_scale = max(1.0, max_img_dim / 1500.0)
        eff_radius = float(self.point_radius)
        eff_point_font = 7
        eff_wing_font = max(18, int(round(18 * (0.75 + 0.25 * scan_scale))))

        for wing_idx, wing in enumerate(self.current_image.wings):
            cx, cy = wing.get_center()
            active_points = wing.get_active_points()
            valid_ys = [py for px, py in active_points if math.isfinite(px) and math.isfinite(py) and not (px == 0 and py == 0)]
            if wing.bbox:
                y_top = min(wing.bbox.y1, min(valid_ys) if valid_ys else wing.bbox.y1)
            elif valid_ys:
                y_top = min(valid_ys)
            else:
                y_top = cy - 40

            is_ok = (wing.analysis.is_identified if wing.analysis else False) and getattr(wing, "is_enabled", True)
            wing_label = WingLabelItem(wing_idx, cx, cy, is_ok, y_top=y_top, font_size=eff_wing_font)
            if not getattr(wing, "is_enabled", True):
                wing_label.setOpacity(0.45)
            self.scene.addItem(wing_label)
            self.wing_labels.append(wing_label)

            # BBOX
            if self.show_bboxes and wing.bbox:
                bbox_item = BBoxItem(wing.bbox.x1, wing.bbox.y1, wing.bbox.x2, wing.bbox.y2, wing_idx)
                self.scene.addItem(bbox_item)
                self.bbox_items.append(bbox_item)

            # Линии измерений
            if self.show_measurement_lines and len(wing.points) == 8:
                self._draw_measurement_lines(active_points, wing.analysis, wing.bbox)

            problem_points = wing.analysis.problem_points if wing.analysis else []

            if active_points:
                for point_idx in range(min(8, len(active_points))):
                    px, py = active_points[point_idx]
                    if not math.isfinite(px) or not math.isfinite(py):
                        continue
                    if px == 0 and py == 0 and all(apx == 0 and apy == 0 for apx, apy in active_points):
                        continue
                    is_problem = point_idx in problem_points

                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'

                    if self._custom_point_color_set or not self.expert_mode:
                        point_color = self.point_color
                    elif source == 'yolo':
                        point_color = COLOR_YOLO
                    elif source == 'stage1':
                        point_color = COLOR_STAGE1
                    elif source == 'stage2':
                        point_color = COLOR_STAGE2
                    elif source == 'gt':
                        point_color = COLOR_GT
                    else:
                        point_color = self.point_color

                    global_idx = wing_idx * 8 + point_idx
                    pt_item = PointItem(
                        px, py, global_idx, wing_idx, point_idx,
                        radius=eff_radius, color=point_color,
                        is_problem=is_problem, source_type=source,
                        text_size=eff_point_font,
                    )
                    if not getattr(wing, "is_enabled", True):
                        pt_item.setOpacity(0.45)
                    pt_item.setZValue(200)

                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            # Оверлеи для сравнения моделей
            if self.show_yolo and hasattr(wing, 'points_yolo') and wing.points_yolo:
                for point_idx, point in enumerate(wing.points_yolo[:8]):
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'yolo':
                        continue
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_YOLO,
                        is_problem=False, source_type='yolo_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            if self.show_stage1 and hasattr(wing, 'points_stage1') and wing.points_stage1:
                for point_idx, point in enumerate(wing.points_stage1[:8]):
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'stage1':
                        continue
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_STAGE1,
                        is_problem=False, source_type='stage1_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            if self.show_stage2 and hasattr(wing, 'points_stage2') and wing.points_stage2:
                for point_idx, point in enumerate(wing.points_stage2[:8]):
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'stage2':
                        continue
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_STAGE2,
                        is_problem=False, source_type='stage2_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            # Ground Truth (TPS) точки из points_gt (или points)
            if self.show_gt:
                gt_list = wing.points_gt if getattr(wing, 'points_gt', None) else wing.points
                if gt_list:
                    for point_idx, point in enumerate(gt_list[:8]):
                        if point_idx < len(active_points):
                            apx, apy = active_points[point_idx]
                            if math.isfinite(apx) and math.isfinite(apy) and abs(point.x - apx) < 0.1 and abs(point.y - apy) < 0.1:
                                continue
                        pt_item = PointItem(
                            point.x, point.y, -100, wing_idx, point_idx,
                            radius=self.point_radius * 0.75, color=COLOR_GT,
                            is_problem=False, source_type='gt_compare'
                        )
                        pt_item.setOpacity(0.65)
                        pt_item.setZValue(95)
                        self.scene.addItem(pt_item)
                        self.point_items.append(pt_item)

        self._update_wings_table()

        self.lbl_filename.setText(f"Файл: {self.current_image.path.name}")
        self.lbl_size.setText(f"{self.current_image.width}×{self.current_image.height}")

        total_wings = len(self.current_image.wings)
        enabled_wings = [w for w in self.current_image.wings if getattr(w, "is_enabled", True)]
        identified = sum(1 for w in enabled_wings if w.analysis and w.analysis.is_identified)
        self.lbl_wings_count.setText(f"Крыльев: {len(enabled_wings)}/{total_wings} (✓{identified})")

    def _draw_measurement_lines(self, points, analysis, bbox=None):
        """Отрисовка линий измерений"""
        if len(points) != 8 or not all(math.isfinite(x) and math.isfinite(y) for x, y in points):
            return

        p1, p2, p3, p4, p5, p6, p7, p8 = points

        line = MeasurementLineItem(p1[0], p1[1], p2[0], p2[1], QColor(0, 100, 255), 2, Qt.SolidLine)
        self.scene.addItem(line)
        self.measurement_lines.append(line)

        for (pa, pb, color, style) in [
            (p3, p4, QColor(200, 0, 200), Qt.SolidLine),
            (p5, p6, QColor(255, 50, 50), Qt.SolidLine),
            (p6, p7, QColor(180, 0, 0), Qt.SolidLine),
            (p5, p7, QColor(255, 100, 150), Qt.DashDotLine),
        ]:
            line = MeasurementLineItem(pa[0], pa[1], pb[0], pb[1], color, 2, style)
            self.scene.addItem(line)
            self.measurement_lines.append(line)

    def _update_wings_table(self):
        """Обновить таблицу крыльев справа (с чекбоксом включения в расчёт и русскими названиями пород)"""
        self._updating_wings_table = True
        try:
            if not self.current_image:
                self.wings_table.setRowCount(0)
                return

            self.wings_table.setRowCount(len(self.current_image.wings))

            for i, wing in enumerate(self.current_image.wings):
                enabled = getattr(wing, "is_enabled", True)
                num_item = QTableWidgetItem(str(i + 1))
                num_item.setFlags(num_item.flags() | Qt.ItemIsUserCheckable)
                num_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
                num_item.setToolTip("Снимите галочку, чтобы временно исключить это крыло из расчёта семьи")
                self.wings_table.setItem(i, 0, num_item)

                if wing.analysis:
                    breeds_ru = format_breed_ru(wing.analysis.breeds, short=True) if wing.analysis.breeds else "—"
                    breed_item = QTableWidgetItem(breeds_ru)
                    breed_item.setToolTip(format_breed_ru(wing.analysis.breeds) if wing.analysis.breeds else "Вне стандарта чистых пород")
                    self.wings_table.setItem(i, 1, breed_item)
                    self.wings_table.setItem(i, 2, QTableWidgetItem(f"{wing.analysis.CI:.2f}"))

                    if not enabled:
                        status = "⏸"
                    elif wing.analysis.is_identified:
                        status = "✅"
                    else:
                        status = "❌"
                    status_item = QTableWidgetItem(status)
                    tip = wing.analysis.invalid_reason or getattr(wing.analysis, "orientation_warning", "")
                    if tip:
                        status_item.setToolTip(tip)
                    self.wings_table.setItem(i, 3, status_item)
                else:
                    self.wings_table.setItem(i, 1, QTableWidgetItem("—"))
                    self.wings_table.setItem(i, 2, QTableWidgetItem("—"))
                    self.wings_table.setItem(i, 3, QTableWidgetItem("❌"))

            self.wings_table.viewport().update()
        finally:
            self._updating_wings_table = False

    def _on_wings_table_item_changed(self, item: QTableWidgetItem):
        """Включение/отключение крыла из расчёта по галочке в колонке 0"""
        if self._updating_wings_table or not self.current_image or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.current_image.wings):
            new_enabled = (item.checkState() == Qt.Checked)
            wing = self.current_image.wings[row]
            if getattr(wing, "is_enabled", True) != new_enabled:
                wing.is_enabled = new_enabled
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
                self.batch_widget.update_batch_results(self.images)

    def _on_wing_selected(self, item):
        """Выбор крыла в таблице справа"""
        row = item.row()
        if row < 0 or not self.current_image:
            return

        self.selected_wing_idx = row

        for pt_item in self.point_items:
            pt_item.set_selected(False)

        if row < len(self.current_image.wings):
            for pt_item in self.point_items:
                if pt_item.wing_idx == row and pt_item.global_idx >= 0:
                    pt_item.set_selected(True)

            cx, cy = self.current_image.wings[row].get_center()
            self.view._fit_mode = False
            self.view.resetTransform()
            self.view.scale(1.6, 1.6)
            self.view._zoom = 1.6
            self.view.centerOn(cx, cy)

    def _goto_wing(self, wing_idx: int):
        """Перейти к крылу"""
        if not self.current_image or wing_idx < 0 or wing_idx >= len(self.current_image.wings):
            return

        self.tab_widget.setCurrentIndex(0)
        self.selected_wing_idx = wing_idx

        for pt_item in self.point_items:
            pt_item.set_selected(False)

        for pt_item in self.point_items:
            if pt_item.wing_idx == wing_idx and pt_item.global_idx >= 0:
                pt_item.set_selected(True)

        cx, cy = self.current_image.wings[wing_idx].get_center()
        self.view._fit_mode = False
        self.view.resetTransform()
        self.view.scale(1.6, 1.6)
        self.view._zoom = 1.6
        self.view.centerOn(cx, cy)

        self.wings_table.selectRow(wing_idx)

    def _set_edit_mode(self, mode: EditMode):
        """Установить режим редактирования"""
        self.edit_mode = mode
        self.view.set_edit_mode(mode)

        self.act_mode_view.setChecked(mode == EditMode.VIEW)
        self.act_mode_edit.setChecked(mode == EditMode.EDIT)
        self.act_mode_add.setChecked(mode == EditMode.ADD)
        self.act_mode_bbox.setChecked(mode == EditMode.BBOX)

        self.lbl_mode.setText(f"Режим: {mode.value}")

        if mode == EditMode.ADD:
            self.wing_guide.set_active_point(0)
        else:
            self._cancel_adding()
            self.wing_guide.set_active_point(None)

    def _on_point_clicked(self, global_idx: int, wing_idx: int, point_idx: int):
        """Клик по точке"""
        for item in self.point_items:
            item.set_selected(False)

        for point in self.point_items:
            if point.global_idx == global_idx and global_idx >= 0:
                point.set_selected(True)

        self.selected_wing_idx = wing_idx
        self.wings_table.selectRow(wing_idx)
        self.wing_guide.set_active_point(point_idx)

    def _remember_edit(self):
        if self.current_image:
            self._undo_stack.append((str(self.current_image.path), copy.deepcopy(self.current_image.wings)))
            self._undo_stack = self._undo_stack[-50:]

    def _undo_edit(self):
        if not self._undo_stack:
            return
        path, wings = self._undo_stack.pop()
        if path in self.images:
            image = self.images[path]
            image.wings = wings
            image.is_modified = True
            image.analyze_all_wings()
            if image is self.current_image:
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
            self.batch_widget.update_batch_results(self.images)

    def _on_point_moved(self, wing_idx: int, point_idx: int, x: float, y: float):
        """Перемещение точки (сохраняет эталонные точки points_gt нетронутыми!)"""
        if not self.current_image:
            return

        if 0 <= wing_idx < len(self.current_image.wings):
            wing = self.current_image.wings[wing_idx]
            if 0 <= point_idx < len(wing.points):
                self._remember_edit()
                # Если крыло было из TPS ('gt'), а points_gt ещё не скопирован — сохраняем копию эталона
                if not getattr(wing, 'points_gt', None) and any(s == 'gt' for s in wing.point_sources):
                    wing.points_gt = [WingPoint(p.x, p.y, p.is_manual) for p in wing.points]

                wing.points[point_idx].x = x
                wing.points[point_idx].y = y
                wing.points[point_idx].is_manual = True
                if point_idx < len(wing.point_sources):
                    wing.point_sources[point_idx] = 'manual'
                self.current_image.is_modified = True

                self.current_image.analyze_all_wings()
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
                self._update_wings_table()
                self.batch_widget.update_batch_results(self.images)
                self.wing_guide.set_active_point(point_idx)

    def _on_bbox_created(self, x1, y1, x2, y2):
        """Создание рамки: если загружена model_pose, автоматически распознаёт 8 точек внутри рамки!"""
        if not self.current_image:
            return

        self._remember_edit()
        bbox = BBox(x1, y1, x2, y2)
        recognized_wing = None
        if self.model_pose is not None and self.current_image.path.exists():
            recognized_wing = ProcessingWorker.recognize_wing_in_bbox(
                self.current_image.path, bbox, self.model_pose, self.device
            )

        if recognized_wing is not None:
            wing = recognized_wing
            self.statusBar().showMessage("✅ Крыло в рамке автоматически распознано (8 точек)!")
        else:
            # Создаём 8 точек внутри рамки по анатомическому шаблону, чтобы их было видно и удобно поправить мышкой
            w_box = max(20.0, x2 - x1)
            h_box = max(20.0, y2 - y1)
            from .wing_guide_widget import WingSchematicCanvas
            pts = [
                WingPoint(x=x1 + nx * w_box, y=y1 + ny * h_box, is_manual=True)
                for nx, ny in WingSchematicCanvas.NORM_POINTS
            ]
            wing = Wing(points=pts, bbox=bbox, point_sources=['manual'] * 8)
            wing.analyze(
                image_height=self.current_image.height if self.current_image.height > 0 else None,
                image_width=self.current_image.width if self.current_image.width > 0 else None,
            )
            self.statusBar().showMessage("Рамка создана: подвиньте точки 1–8 мышкой на пересечения жилок.")

        self.current_image.wings.append(wing)
        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self.chk_bbox.setChecked(True)
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)

    def _on_bbox_changed(self, wing_idx, x1, y1, x2, y2):
        """Изменение размера/положения рамки"""
        if not self.current_image:
            return

        if 0 <= wing_idx < len(self.current_image.wings):
            self._remember_edit()
            wing = self.current_image.wings[wing_idx]
            wing.bbox = BBox(x1, y1, x2, y2)
            # Если у крыла не было валидных точек или загружена model_pose — распознаём по новой рамке
            if self.model_pose is not None and self.current_image.path.exists():
                rec = ProcessingWorker.recognize_wing_in_bbox(
                    self.current_image.path, wing.bbox, self.model_pose, self.device
                )
                if rec is not None:
                    wing.points = rec.points
                    wing.points_yolo = rec.points_yolo
                    wing.point_sources = rec.point_sources

        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)

    def _on_bbox_recognize_requested(self, wing_idx: int):
        """Распознать точки внутри выбранной рамки по команде контекстного меню"""
        if not self.current_image or not (0 <= wing_idx < len(self.current_image.wings)):
            return
        wing = self.current_image.wings[wing_idx]
        if not wing.bbox:
            return
        if self.model_pose is None:
            QMessageBox.information(self, "Распознавание в рамке", "Модель распознавания точек не загружена.")
            return
        rec = ProcessingWorker.recognize_wing_in_bbox(
            self.current_image.path, wing.bbox, self.model_pose, self.device
        )
        if rec is not None:
            self._remember_edit()
            wing.points = rec.points
            wing.points_yolo = rec.points_yolo
            wing.point_sources = rec.point_sources
            self.current_image.is_modified = True
            self.current_image.analyze_all_wings()
            self._update_display()
            self._update_analysis_widget()
            self._update_interpretation_widgets()
            self.batch_widget.update_batch_results(self.images)
            self.statusBar().showMessage(f"✅ Точки крыла №{wing_idx + 1} распознаны внутри рамки.")
        else:
            QMessageBox.warning(
                self,
                "Распознавание в рамке",
                "Не удалось автоматически найти 8 точек в этой рамке. Подвиньте точки мышкой вручную."
            )

    def _reset_selected_wing(self):
        row = self.wings_table.currentRow()
        if row >= 0:
            self._on_wing_reset_requested(row)

    def _on_wing_reset_requested(self, wing_idx: int):
        """Сбросить точки крыла к исходным (TPS или нейросеть YOLO)"""
        if not self.current_image or not (0 <= wing_idx < len(self.current_image.wings)):
            return
        wing = self.current_image.wings[wing_idx]
        self._remember_edit()
        if getattr(wing, 'points_gt', None) and len(wing.points_gt) == 8:
            wing.points = [WingPoint(p.x, p.y, False) for p in wing.points_gt]
            wing.point_sources = ['gt'] * 8
        elif getattr(wing, 'points_yolo', None) and len(wing.points_yolo) == 8:
            wing.points = [WingPoint(p.x, p.y, False) for p in wing.points_yolo]
            wing.point_sources = ['yolo'] * 8
        elif getattr(wing, 'points_stage2', None) and len(wing.points_stage2) == 8:
            wing.points = [WingPoint(p.x, p.y, False) for p in wing.points_stage2]
            wing.point_sources = ['stage2'] * 8
        else:
            self.statusBar().showMessage("У этого крыла нет сохранённых исходных точек для сброса.")
            return

        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)
        self.statusBar().showMessage(f"🔄 Точки крыла №{wing_idx + 1} возвращены к исходным.")

    def _on_point_delete(self, wing_idx, point_idx):
        """Удаление точки или крыла"""
        if not self.current_image:
            return
        if wing_idx < 0 or wing_idx >= len(self.current_image.wings):
            return

        wing = self.current_image.wings[wing_idx]

        if point_idx >= 0:
            reply = QMessageBox.question(
                self,
                "Удаление точки",
                f"Удалить точку №{point_idx + 1} с крыла №{wing_idx + 1}?\n\n"
                f"Подсказка: чтобы поставить её заново, выберите инструмент «➕ Точки» и кликните в нужное место крыла "
                f"(или нажмите «🔄 Сбросить точки»).",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._remember_edit()
                if 0 <= point_idx < len(wing.points):
                    wing.points[point_idx].x = float("nan")
                    wing.points[point_idx].y = float("nan")
                    wing.points[point_idx].is_manual = True
                if point_idx < len(wing.point_sources):
                    wing.point_sources[point_idx] = 'manual'
                self.current_image.is_modified = True
                self.current_image.analyze_all_wings()
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
        else:
            reply = QMessageBox.question(
                self, "Удаление", f"Удалить крыло №{wing_idx + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._remember_edit()
                del self.current_image.wings[wing_idx]
                self.current_image.is_modified = True
                self.current_image.analyze_all_wings()
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
                self.batch_widget.update_batch_results(self.images)

    def _on_bbox_delete(self, wing_idx):
        """Удаление рамки"""
        self._on_point_delete(wing_idx, -1)

    def _delete_selected_wing(self):
        """Удалить выбранное крыло"""
        row = self.wings_table.currentRow()
        if row >= 0:
            self._on_point_delete(row, -1)

    def _on_scene_clicked(self, x: float, y: float):
        """Клик по сцене в режиме ADD: сначала дозаполняет пропущенную точку (NaN), иначе создаёт новое крыло из 8 точек"""
        if self.edit_mode != EditMode.ADD or not self.current_image:
            return

        # Проверяем, есть ли у крыльев удалённая точка (NaN), которую пользователь хочет поставить заново
        if not self.adding_points:
            for w_idx, wing in enumerate(self.current_image.wings):
                active = wing.get_active_points()
                for p_idx, (px, py) in enumerate(active):
                    if not (math.isfinite(px) and math.isfinite(py)):
                        self._remember_edit()
                        while len(wing.points) < NUM_POINTS:
                            wing.points.append(WingPoint(0.0, 0.0, True))
                        wing.points[p_idx].x = x
                        wing.points[p_idx].y = y
                        wing.points[p_idx].is_manual = True
                        if p_idx < len(wing.point_sources):
                            wing.point_sources[p_idx] = 'manual'
                        self.current_image.is_modified = True
                        self.current_image.analyze_all_wings()
                        self._update_display()
                        self._update_analysis_widget()
                        self._update_interpretation_widgets()
                        self.batch_widget.update_batch_results(self.images)
                        self.statusBar().showMessage(
                            f"📍 Точка №{p_idx + 1} на крыле №{w_idx + 1} восстановлена!"
                        )
                        return

        self.adding_points.append((x, y))
        cur_pt_idx = len(self.adding_points) - 1

        global_idx = len(self.current_image.wings) * NUM_POINTS + cur_pt_idx
        pt_item = PointItem(
            x, y, global_idx, len(self.current_image.wings), cur_pt_idx,
            radius=self.point_radius, color=QColor(255, 165, 0)
        )
        self.scene.addItem(pt_item)
        self.temp_add_items.append(pt_item)

        self.statusBar().showMessage(f"Поставлена точка {len(self.adding_points)} из 8")
        if len(self.adding_points) < NUM_POINTS:
            self.wing_guide.set_active_point(len(self.adding_points))

        if len(self.adding_points) == NUM_POINTS:
            self._remember_edit()
            wing = Wing(
                points=[WingPoint(x=pt[0], y=pt[1], is_manual=True) for pt in self.adding_points],
                point_sources=['manual'] * 8,
            )
            wing.analyze(
                image_height=self.current_image.height if self.current_image.height > 0 else None,
                image_width=self.current_image.width if self.current_image.width > 0 else None,
            )
            self.current_image.wings.append(wing)
            self.current_image.is_modified = True
            self._cancel_adding()
            self._update_display()
            self._update_analysis_widget()
            self._update_interpretation_widgets()
            self.batch_widget.update_batch_results(self.images)
            self.wing_guide.set_active_point(0)
            self.statusBar().showMessage("✅ Новое крыло из 8 точек добавлено!")

    def _cancel_adding(self):
        """Отмена добавления"""
        self.adding_points.clear()
        for item in self.temp_add_items:
            self.scene.removeItem(item)
        self.temp_add_items.clear()

    def _cancel_action(self):
        """Отмена действия (в режиме ADD удаляет последнюю поставленную точку по одному шагу)"""
        if self.edit_mode == EditMode.ADD and self.adding_points:
            self.adding_points.pop()
            if self.temp_add_items:
                last_item = self.temp_add_items.pop()
                self.scene.removeItem(last_item)
            self.wing_guide.set_active_point(len(self.adding_points))
            self.statusBar().showMessage(f"Точек: {len(self.adding_points)}/8")
        else:
            self._set_edit_mode(EditMode.VIEW)

    def _process_smart(self):
        """Умная обработка"""
        selected_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_paths.append(Path(item.data(Qt.UserRole)))

        if selected_paths:
            self._process_images(selected_paths)
        elif self.current_image:
            self._process_images([self.current_image.path])
        else:
            self.statusBar().showMessage("Сначала откройте скан или папку с крыльями")

    def _process_images(self, paths):
        """Обработать изображения"""
        if getattr(self, 'worker', None) and self.worker.isRunning():
            self.statusBar().showMessage('Обработка уже выполняется')
            return
        if any(self.images[str(p)].wings for p in paths if str(p) in self.images):
            if QMessageBox.question(
                self,
                'Повторная обработка',
                'Заменить имеющиеся точки новым распознаванием?',
                QMessageBox.Yes | QMessageBox.No
            ) != QMessageBox.Yes:
                return
        if not self.model_det or not self.model_pose:
            QMessageBox.critical(
                self,
                "Модели не найдены",
                "Нейросетевые модели распознавания крыльев не загружены.\n"
                "Убедитесь, что файлы весов находятся в папке models/."
            )
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(paths))

        self.worker = ProcessingWorker(
            paths, self.model_det, self.model_pose,
            self.model_stage2, self.device,
            model_subpixel=self.model_subpixel,
            model_stage2_portable=self.model_stage2_portable,
            compute_profile=self.compute_profile,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current, total, message):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.statusBar().showMessage(message)

    def _on_finished(self, results):
        """Завершение обработки (с быстрым чтением размеров через image_size и подсказкой при 0 крыльев)"""
        self.progress_bar.setVisible(False)
        zero_wing_files = []

        for path_str, wings in results.items():
            if path_str in self.images:
                img_data = self.images[path_str]
                img_data.wings = sorted(wings, key=lambda w: (round(w.get_center()[1] / 400), w.get_center()[0]))
                img_data.is_modified = True
                img_data.analysis_results = {}
                img_data.is_processed = True

                if img_data.height == 0:
                    try:
                        w, h = image_size(img_data.path)
                        img_data.width = w
                        img_data.height = h
                    except Exception:
                        pixmap = read_pixmap(img_data.path)
                        img_data.width = pixmap.width()
                        img_data.height = pixmap.height()

                img_data.analyze_all_wings()
                if not img_data.wings:
                    zero_wing_files.append(img_data.path.name)

        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            path = item.data(Qt.UserRole)
            if path in self.images and self.images[path].wings:
                text = item.text()
                if text.startswith("○"):
                    item.setText("✓" + text[1:])

        self._update_files_stats()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)

        self.statusBar().showMessage(f"✅ Обработка завершена (файлов: {len(results)})")

        if zero_wing_files and len(results) == 1:
            QMessageBox.information(
                self,
                "Крылья не распознаны автоматически",
                f"На изображении «{zero_wing_files[0]}» нейросеть не смогла автоматически выделить крылья.\n\n"
                "Возможные причины:\n"
                "• Слишком размытое, тёмное или бликующее фото (рекомендуется скан на светлом фоне от 1200 DPI);\n"
                "• Крылья соприкасаются друг с другом или обрезаны краем кадра.\n\n"
                "💡 Что делать:\n"
                "Нажмите кнопку «⬜ Рамка» на верхней панели и обведите крыло прямоугольником — "
                "программа расставит внутри него 8 точек!"
            )

    def _on_error(self, msg):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", msg)

    def _toggle_left_panel(self):
        if not hasattr(self, "left_panel"):
            return
        sizes = self.main_splitter.sizes()
        total = sum(sizes) or (self._saved_left_size + 900 + self._saved_right_size)
        right_width = 0 if self.right_collapsed else (sizes[2] if len(sizes) > 2 and sizes[2] > 0 else self._saved_right_size)

        if not self.left_collapsed:
            if len(sizes) > 0 and sizes[0] > 0:
                self._saved_left_size = sizes[0]
            center_width = total - right_width
            self.main_splitter.setSizes([0, center_width, right_width])
            self.left_panel.setVisible(False)
            self.left_collapsed = True
        else:
            center_width = max(0, total - self._saved_left_size - right_width)
            self.main_splitter.setSizes([self._saved_left_size, center_width, right_width])
            self.left_panel.setVisible(True)
            self.left_collapsed = False

    def _toggle_right_panel(self):
        sizes = self.main_splitter.sizes()
        total = sum(sizes) or (self._saved_left_size + 900 + self._saved_right_size)
        left_width = 0 if self.left_collapsed else (sizes[0] if len(sizes) > 0 and sizes[0] > 0 else self._saved_left_size)

        if not self.right_collapsed:
            if len(sizes) > 2 and sizes[2] > 0:
                self._saved_right_size = sizes[2]
            center_width = total - left_width
            self.main_splitter.setSizes([left_width, center_width, 0])
            self.right_panel.setVisible(False)
            self.right_collapsed = True
        else:
            center_width = max(0, total - left_width - self._saved_right_size)
            self.main_splitter.setSizes([left_width, center_width, self._saved_right_size])
            self.right_panel.setVisible(True)
            self.right_collapsed = False

    def _toggle_minimap(self):
        """Показать/скрыть миникарту навигации."""
        self.view.toggle_minimap()

    def _toggle_single_wing_mode(self, checked):
        """Включение/выключение режима одиночного крыла (агрегирование по всем фото)"""
        self.single_wing_mode = checked
        self._update_analysis_widget()
        self._update_interpretation_widgets()

    def _load_gpt_config(self):
        self._gpt_config_path = Path.home() / ".neuroWingHybrid_gpt.json"
        cfg = {"api_key": "", "model": "gpt-4o-mini", "enabled": False}
        if self._gpt_config_path.exists():
            try:
                cfg.update(json.loads(self._gpt_config_path.read_text()))
            except Exception:
                pass
        self._gpt_api_key = cfg.get("api_key", "")
        if not self._gpt_api_key:
            try:
                from ..core.credential_store import read_key
                self._gpt_api_key = read_key()
            except Exception:
                self._gpt_api_key = ""
        self._gpt_model = cfg.get("model", "gpt-4o-mini")
        self._gpt_enabled = bool(cfg.get("enabled", False) and self._gpt_api_key)
        self._init_gpt_client()

    def _save_gpt_config(self):
        from ..core.credential_store import write_key
        write_key(self._gpt_api_key)
        cfg = {"model": self._gpt_model, "enabled": self._gpt_enabled}
        try:
            self._gpt_config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"Не удалось сохранить GPT конфиг: {e}")

    def _init_gpt_client(self):
        try:
            if self._gpt_enabled and self._gpt_api_key:
                from openai import OpenAI
                self._gpt_client = OpenAI(api_key=self._gpt_api_key, timeout=15.0, max_retries=0)
            else:
                self._gpt_client = None
        except Exception as e:
            print(f"GPT инициализация не удалась: {e}")
            self._gpt_client = None

    def _show_gpt_settings(self):
        from PyQt5.QtWidgets import QFormLayout, QLineEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки ИИ-комментариев (OpenAI GPT)")
        layout = QFormLayout(dlg)
        key_edit = QLineEdit(self._gpt_api_key)
        key_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        model_edit = QLineEdit(self._gpt_model or "gpt-4o-mini")
        enabled_chk = QCheckBox("Включить кнопку комментария GPT во вкладке Интерпретация")
        enabled_chk.setChecked(self._gpt_enabled)
        layout.addRow("API ключ OpenAI:", key_edit)
        layout.addRow("Модель:", model_edit)
        layout.addRow("", enabled_chk)

        test_btn = QPushButton("Проверить ключ (таймаут 10 сек)")

        def _test_key():
            key = key_edit.text().strip()
            model_name = model_edit.text().strip() or "gpt-4o-mini"
            if not key:
                QMessageBox.warning(dlg, "GPT", "Введите API ключ.")
                return
            try:
                from openai import OpenAI
            except ImportError:
                QMessageBox.warning(
                    dlg,
                    "GPT",
                    "Модуль интеграции с OpenAI недоступен в данной сборке.",
                )
                return
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                client = OpenAI(api_key=key, timeout=10.0, max_retries=0)
                client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    temperature=0.0,
                )
                QApplication.restoreOverrideCursor()
                QMessageBox.information(dlg, "GPT", "✅ Ключ успешно проверен и работает!")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(dlg, "GPT", f"Ошибка проверки ключа:\n{e}")

        test_btn.clicked.connect(_test_key)
        layout.addRow("", test_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        if dlg.exec_():
            self._gpt_api_key = key_edit.text().strip()
            self._gpt_model = model_edit.text().strip() or "gpt-4o-mini"
            self._gpt_enabled = enabled_chk.isChecked() and bool(self._gpt_api_key)
            try:
                self._save_gpt_config()
            except Exception as exc:
                QMessageBox.warning(self, "GPT", f"Не удалось сохранить ключ в системном хранилище: {exc}")
                self._gpt_enabled = False
                return
            self._init_gpt_client()
            self._apply_gpt_to_widgets()

    def _apply_gpt_to_widgets(self):
        if self._gpt_client and self._gpt_enabled:
            self.interpretation_widget.set_llm(self._gpt_client, self._gpt_model, True)
            self.global_interpretation_widget.set_llm(self._gpt_client, self._gpt_model, True)
        else:
            self.interpretation_widget.set_llm(None, None, False)
            self.global_interpretation_widget.set_llm(None, None, False)

    def _update_analysis_widget(self):
        """Обновить анализ с учётом режима одиночного крыла"""
        if self.single_wing_mode:
            agg_wings, _, _ = self._collect_all_wings()
            self.analysis_widget.update_statistics(agg_wings if agg_wings else [], target_breed=self.target_breed)
        else:
            self.analysis_widget.update_statistics(self.current_image, target_breed=self.target_breed)

    def _collect_all_wings(self):
        """Собрать все крылья со всех изображений"""
        wings = []
        ref_w = ref_h = 0
        for img in self.images.values():
            if img and img.wings:
                needs_calc = img.is_modified or any(getattr(w, "analysis", None) is None for w in img.wings)
                if needs_calc:
                    img.analyze_all_wings()
                wings.extend(img.wings)
                if ref_w == 0 and img.width:
                    ref_w, ref_h = img.width, img.height
        return wings, ref_w, ref_h

    def _update_interpretation_widgets(self):
        """Обновить интерпретацию (пер-фото и общую)"""
        if self.single_wing_mode:
            agg_wings, _, _ = self._collect_all_wings()
            self.interpretation_widget.update_interpretation(agg_wings if agg_wings else [], target_breed=self.target_breed)
        else:
            self.interpretation_widget.update_interpretation(self.current_image, target_breed=self.target_breed)

        if self.tab_widget.currentWidget() is self.global_interpretation_widget:
            self._update_global_interpretation(force=True)
        else:
            if self.single_wing_mode:
                self.global_interpretation_widget.set_message("Режим одиночного крыла: общая интерпретация отключена.")
            else:
                self.global_interpretation_widget.set_message("Откройте вкладку \"🌐 Общая интерпретация\" для расчёта.")

    def _update_global_interpretation(self, force: bool = False):
        if self.single_wing_mode:
            self.global_interpretation_widget.set_message("Режим одиночного крыла: общая интерпретация отключена.")
            return
        if not force and self.tab_widget.currentWidget() is not self.global_interpretation_widget:
            return
        self.global_interpretation_widget.update_global(self.images, self.single_wing_mode)

    def _save_current(self):
        """Сохранить текущий TPS с защитой от неполных крыльев (NaN)"""
        if not self.current_image:
            return
        if self._save_tps(self.current_image):
            self.statusBar().showMessage(f"💾 Сохранено: {self.current_image.path.stem}.tps")

    def _save_all(self):
        """Сохранить все TPS"""
        saved = 0
        for img_data in self.images.values():
            if img_data.wings or img_data.is_modified:
                if self._save_tps(img_data):
                    saved += 1
        self.statusBar().showMessage(f"💾 Сохранено файлов: {saved}")

    def _save_tps(self, img_data) -> bool:
        """Сохранить TPS файл в формате WingsDig с проверкой валидности координат"""
        if not img_data:
            return False

        # Проверяем, есть ли крылья с удалёнными точками (NaN)
        incomplete_indices = []
        for idx, w in enumerate(img_data.wings):
            pts = w.get_active_points()
            if len(pts) != 8 or not all(math.isfinite(x) and math.isfinite(y) for x, y in pts):
                incomplete_indices.append(idx + 1)

        if incomplete_indices:
            nums_str = ", ".join(f"№{n}" for n in incomplete_indices)
            reply = QMessageBox.question(
                self,
                "Неполная разметка крыла",
                f"В файле «{img_data.path.name}» у крыльев {nums_str} удалены отдельные точки.\n\n"
                "Формат TPS требует ровно 8 точек на каждое крыло.\n"
                "Удалить неполные крылья перед сохранением TPS?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                img_data.wings = [
                    w for w in img_data.wings
                    if len(w.get_active_points()) == 8
                    and all(math.isfinite(x) and math.isfinite(y) for x, y in w.get_active_points())
                ]
                self._update_display()
            else:
                return False

        try:
            tps_path = img_data.path.with_suffix('.tps')
            save_tps_from_image(img_data, tps_path)
            save_project(img_data, tps_path)
            img_data.is_modified = False
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка сохранения TPS", f"Не удалось сохранить {img_data.path.name}:\n{exc}")
            return False

    def _export_pdf(self):
        """Экспорт одностраничного PDF-Паспорта семьи с верхней панели или меню"""
        if self.single_wing_mode:
            agg_wings, _, _ = self._collect_all_wings()
            if not agg_wings:
                QMessageBox.warning(self, "PDF-Паспорт", "Сначала загрузите и обработайте крылья.")
                return
            self.analysis_widget._export_to_pdf()
            return

        if not self.current_image or not self.current_image.wings:
            QMessageBox.warning(
                self,
                "PDF-Паспорт",
                "Нет распознанных крыльев для создания PDF-Паспорта.\n"
                "Откройте скан и нажмите «⚡ Обработать»."
            )
            return
        self.analysis_widget._export_to_pdf()

    def _export_excel(self):
        """Экспорт в Excel"""
        if not self.current_image and not self.single_wing_mode:
            return
        self.analysis_widget._export_to_excel()

    def _fit_view(self):
        self.view.fit_in_view()

    def _zoom(self, factor):
        self.view._fit_mode = False
        self.view.scale(factor, factor)
        self.view._zoom = self.view.transform().m11()

    def _zoom_100(self):
        self.view._fit_mode = False
        self.view.resetTransform()
        self.view._zoom = 1.0

    def _auto_check_for_updates(self):
        if getattr(sys, "frozen", False):
            self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool = False):
        if self._update_check_worker and self._update_check_worker.isRunning():
            if manual:
                self.statusBar().showMessage("Проверка обновлений уже выполняется.", 3000)
            return

        self._update_check_worker = UpdateCheckWorker(APP_UPDATE_FEED_URL, APP_VERSION)
        self._update_check_worker.finished.connect(
            lambda info: self._on_update_check_finished(info, manual)
        )
        self._update_check_worker.error.connect(
            lambda message: self._on_update_check_error(message, manual)
        )
        self._update_check_worker.start()

        if manual:
            self.statusBar().showMessage("Проверяю обновления...", 3000)

    def _on_update_check_finished(self, info: dict, manual: bool):
        self._update_info = info if info.get("update_available") else None
        if info.get("update_available"):
            self._show_update_banner(info)
            self.statusBar().showMessage(
                f"Доступно обновление {info['version']} (у вас {APP_VERSION}).",
                5000,
            )
            if manual:
                self._prompt_update(info)
        else:
            self._hide_update_banner()
            if manual:
                QMessageBox.information(
                    self,
                    "Обновление",
                    f"У вас уже актуальная версия {APP_VERSION}.",
                )
            else:
                self.statusBar().showMessage("Обновлений не найдено.", 3000)

        self._update_check_worker = None

    def _on_update_check_error(self, message: str, manual: bool):
        self._update_check_worker = None
        if manual:
            QMessageBox.warning(
                self,
                "Обновление",
                f"Не удалось проверить обновления.\n\n{message}",
            )
        else:
            self.statusBar().showMessage("Не удалось проверить обновления.", 3000)

    def _show_update_banner(self, info: dict):
        published_at = f", опубликовано {info['published_at']}" if info.get("published_at") else ""
        self.lbl_update_banner.setText(
            f"Доступна новая версия {info['version']} (у вас {APP_VERSION}{published_at})."
        )
        self.update_banner.setVisible(True)

    def _hide_update_banner(self):
        self.update_banner.setVisible(False)

    def _start_pending_update(self):
        if self._update_info:
            self._begin_update_download(self._update_info)

    def _prompt_update(self, info: dict):
        parts = [f"Доступна версия {info['version']} (у вас {APP_VERSION})."]
        if info.get("headline"):
            parts.append("")
            parts.append(info["headline"])
        if info.get("notes"):
            parts.append("")
            parts.append("Что изменилось:")
            parts.extend(f"- {note}" for note in info["notes"])

        reply = QMessageBox.question(
            self,
            "Доступно обновление",
            "\n".join(parts),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._begin_update_download(info)

    def _begin_update_download(self, info: dict):
        download_url = info.get("download_url", "").strip()
        if not download_url:
            QMessageBox.warning(
                self,
                "Обновление",
                "Для этой версии не указана ссылка на скачивание.",
            )
            return

        if not getattr(sys, "frozen", False) or os.name != "nt":
            QDesktopServices.openUrl(QUrl(download_url))
            QMessageBox.information(
                self,
                "Обновление",
                "Автообновление работает в установленной Windows-версии. "
                "Ссылка на загрузку открыта в браузере.",
            )
            return

        if not is_direct_download_url(download_url):
            QDesktopServices.openUrl(QUrl(download_url))
            QMessageBox.information(
                self,
                "Обновление",
                "Для этой версии доступна страница загрузки. Я открыл ее в браузере.",
            )
            return

        if self._update_download_worker and self._update_download_worker.isRunning():
            QMessageBox.information(
                self,
                "Обновление",
                "Скачивание обновления уже выполняется.",
            )
            return

        file_name = Path(urlparse(download_url).path).name or Path(sys.executable).name
        download_dir = Path(tempfile.gettempdir()) / "neurowings-updates"
        destination = download_dir / file_name

        self._update_progress_dialog = QProgressDialog("Скачивание обновления...", None, 0, 0, self)
        self._update_progress_dialog.setWindowTitle("Обновление")
        self._update_progress_dialog.setCancelButton(None)
        self._update_progress_dialog.setWindowModality(Qt.WindowModal)
        self._update_progress_dialog.show()

        self._update_download_worker = UpdateDownloadWorker(info, destination)
        self._update_download_worker.progress.connect(self._on_update_download_progress)
        self._update_download_worker.finished.connect(
            lambda path_str: self._on_update_download_finished(path_str, info)
        )
        self._update_download_worker.error.connect(self._on_update_download_error)
        self._update_download_worker.start()

    def _on_update_download_progress(self, current: int, total: int):
        if not self._update_progress_dialog:
            return

        if total > 0:
            self._update_progress_dialog.setRange(0, total)
            self._update_progress_dialog.setValue(current)
            self._update_progress_dialog.setLabelText(
                f"Скачивание обновления... {current / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} МБ"
            )
        else:
            self._update_progress_dialog.setRange(0, 0)

    def _on_update_download_finished(self, path_str: str, info: dict):
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        self._update_download_worker = None
        downloaded_path = Path(path_str)

        reply = QMessageBox.question(
            self,
            "Обновление скачано",
            f"Версия {info['version']} скачана.\n\n"
            "Сейчас программа закроется, заменит текущий EXE и запустится заново.\n\n"
            "Применить обновление сейчас?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._install_download(downloaded_path)

    def _on_update_download_error(self, message: str):
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        self._update_download_worker = None
        QMessageBox.warning(
            self,
            "Обновление",
            f"Не удалось скачать обновление.\n\n{message}",
        )

    def _install_download(self, downloaded_path: Path):
        if not self._confirm_close():
            return

        try:
            script_path = create_windows_update_script(
                downloaded_path,
                Path(sys.executable),
                os.getpid(),
            )
            launch_windows_update_script(script_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Обновление",
                f"Не удалось запустить установку обновления.\n\n{exc}",
            )
            return

        self._skip_unsaved_prompt = True
        QApplication.instance().quit()

    def _confirm_close(self) -> bool:
        """Подтвердить выход, если есть несохраненные данные."""
        if not self.isVisible() or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return True
        modified = [d for d in self.images.values() if d.is_modified]
        if not modified:
            return True

        reply = QMessageBox.question(
            self,
            "Сохранить?",
            f"Есть {len(modified)} несохранённых файлов. Сохранить?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )

        if reply == QMessageBox.Save:
            self._save_all()
            return True
        if reply == QMessageBox.Cancel:
            return False
        return True

    def _show_about(self):
        """О программе"""
        dialog = QDialog(self)
        dialog.setWindowTitle("О программе")
        dialog.resize(560, 290)

        layout = QVBoxLayout(dialog)

        current_update = "обновления будут проверяться с сервера"
        if self._update_info:
            current_update = f"доступна версия {html.escape(self._update_info['version'])}"

        label = QLabel(
            f"<h2>{html.escape(APP_NAME)} v{html.escape(APP_VERSION)}</h2>"
            f"<p>Автоматическая морфометрия крыльев пчёл и генерация PDF-Паспортов семей</p>"
            f"<p><b>Автор:</b> {html.escape(APP_AUTHOR)}</p>"
            f"<p><b>MAX:</b> <a href='{html.escape(APP_MAX_URL)}'>{html.escape(APP_MAX_URL)}</a></p>"
            f"<p><b>Telegram:</b> <a href='{html.escape(APP_TELEGRAM_URL)}'>"
            f"{html.escape(APP_TELEGRAM_LABEL)}</a></p>"
            f"<p><b>Статус обновлений:</b> {current_update}</p>"
        )
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        btn_check_update = QPushButton("Проверить обновление")
        btn_check_update.clicked.connect(dialog.accept)
        btn_check_update.clicked.connect(lambda: self._check_for_updates(manual=True))
        buttons.addButton(btn_check_update, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec_()

    def closeEvent(self, event):
        """Закрытие окна с безопасным таймаутом ожидания фоновых потоков (2000 мс)"""
        if self._skip_unsaved_prompt or self._confirm_close():
            for worker in (
                getattr(self, 'worker', None),
                self._update_check_worker,
                self._update_download_worker,
                *self.findChildren(QThread),
            ):
                if worker and worker.isRunning():
                    if hasattr(worker, 'stop'):
                        worker.stop()
                    worker.wait(2000)
            event.accept()
            return
        event.ignore()
