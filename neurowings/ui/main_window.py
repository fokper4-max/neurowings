#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NeuroWings - Главное окно приложения
"""

import html
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
    WingPoint, BBox, Wing, ImageData, EditMode,
    get_device, load_stage2_model, load_stage2_portable_model, load_subpixel_model, TORCH_AVAILABLE
)
from ..core.update_manager import (
    create_windows_update_script,
    is_direct_download_url,
    launch_windows_update_script,
)
from ..core.tps_io import load_tps_into_image, save_tps_from_image

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsScene, QGraphicsPixmapItem, QListWidget, QListWidgetItem,
    QPushButton, QToolButton, QLabel, QCheckBox, QGroupBox,
    QSplitter, QToolBar, QFileDialog, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QShortcut, QRadioButton, QButtonGroup, QAction, QTabWidget, QGridLayout,
    QApplication, QMenu, QSizePolicy, QDialog, QDialogButtonBox, QProgressDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QUrl
from PyQt5.QtGui import QPixmap, QColor, QKeySequence, QPen, QDesktopServices

from .graphics_items import PointItem, WingLabelItem, BBoxItem, MeasurementLineItem
from .graphics_view import ZoomableGraphicsView
from .analysis_widget import AnalysisWidget
from .graphs_widget import GraphsWidget
from .interpretation_widget import InterpretationWidget, GlobalInterpretationWidget
from .batch_widget import BatchResultsWidget
from .dialogs import PointSettingsDialog

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
        
        # Данные
        self.images: Dict[str, ImageData] = {}
        self.current_image: Optional[ImageData] = None
        self.current_folder: Optional[Path] = None
        
        # Модели
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
        self._saved_right_size = 250
        
        # Состояние UI
        self.point_items: List[PointItem] = []
        self.wing_labels = []
        self.bbox_items = []
        self.measurement_lines = []
        self.edit_mode = EditMode.VIEW
        self.selected_wing_idx = -1
        self.adding_points: List[Tuple[float, float]] = []
        self.temp_add_items = []
        
        # Настройки
        self.point_color = COLOR_NORMAL
        self.point_radius = DEFAULT_POINT_RADIUS
        
        # Флаги отображения (все выключены по умолчанию)
        self.show_gt = False
        self.show_yolo = False
        self.show_stage1 = False
        self.show_stage2 = False
        self.show_bboxes = False
        self.show_measurement_lines = False
        self._update_info = None
        self._update_check_worker = None
        self._update_download_worker = None
        self._update_progress_dialog = None
        self._skip_unsaved_prompt = False
        
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_shortcuts()
        self._apply_light_theme()
        self._load_models()
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
        self.btn_select_all.setToolTip("Выбрать все")
        self.btn_select_all.clicked.connect(self._select_all_files)
        files_header.addWidget(self.btn_select_all)
        
        self.btn_select_none = QToolButton()
        self.btn_select_none.setText("✗")
        self.btn_select_none.setToolTip("Снять выбор")
        self.btn_select_none.clicked.connect(self._deselect_all_files)
        files_header.addWidget(self.btn_select_none)
        
        left_layout.addLayout(files_header)
        
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._on_file_clicked)
        left_layout.addWidget(self.file_list)
        
        self.lbl_files_stats = QLabel("0 файлов")
        left_layout.addWidget(self.lbl_files_stats)
        
        self.left_panel.setMaximumWidth(200)
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
        self.view.setFocusPolicy(Qt.StrongFocus)
        image_layout.addWidget(self.view)
        
        # Информационная панель
        info_bar = QWidget()
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(10, 3, 10, 3)
        
        self.lbl_filename = QLabel("Файл: —")
        self.lbl_size = QLabel("Размер: —")
        self.lbl_wings_count = QLabel("Крыльев: 0")
        self.lbl_mode = QLabel("Режим: Просмотр")
        
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
        # Устанавливаем callback для сохранения TPS при экспорте
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
        
        wings_label = QLabel("🦋 Крылья")
        wings_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(wings_label)
        
        self.wings_table = QTableWidget()
        self.wings_table.setColumnCount(4)
        self.wings_table.setHorizontalHeaderLabels(["№", "Порода", "CI", "✓"])
        self.wings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wings_table.itemClicked.connect(self._on_wing_selected)
        right_layout.addWidget(self.wings_table)
        
        self.btn_delete_wing = QPushButton("🗑 Удалить крыло")
        self.btn_delete_wing.clicked.connect(self._delete_selected_wing)
        right_layout.addWidget(self.btn_delete_wing)
        
        # Группа отображения
        display_group = QGroupBox("👁 Отображение")
        display_layout = QVBoxLayout(display_group)
        
        self.chk_gt = QCheckBox("🟢 TPS")
        self.chk_gt.setChecked(False)
        self.chk_gt.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_gt)

        self.chk_yolo_raw = QCheckBox("🔴 Модель 1")
        self.chk_yolo_raw.setChecked(False)
        self.chk_yolo_raw.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_yolo_raw)

        self.chk_stage1 = QCheckBox("🔵 Модель 2")
        self.chk_stage1.setChecked(False)
        self.chk_stage1.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_stage1)

        self.chk_stage2 = QCheckBox("🟣 Модель 2 с уточнением")
        self.chk_stage2.setChecked(False)
        self.chk_stage2.toggled.connect(lambda checked: self._on_display_toggle(checked))
        display_layout.addWidget(self.chk_stage2)

        right_layout.addWidget(display_group)
        
        # Группа выбора модели точек
        self.point_selection_group = QGroupBox("Модель точек")
        sel_layout = QGridLayout(self.point_selection_group)
        sel_layout.setSpacing(2)
        
        # Заголовки столбцов - кликабельные кнопки для массового переключения
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
            
            rb_stage2.setChecked(True)  # По умолчанию выбран итеративный Stage2
            group.buttonClicked.connect(self._on_point_model_changed)
            self.point_model_groups.append(group)
        
        # Кнопки применения выбора
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
        
        right_layout.addWidget(self.point_selection_group)

        # Группа вспомогательных элементов
        auxiliary_group = QGroupBox("🔧 Вспомогательные")
        aux_layout = QVBoxLayout(auxiliary_group)

        self.chk_bbox = QCheckBox("🟠 Рамка")
        self.chk_bbox.setChecked(False)  # По умолчанию выключено
        self.chk_bbox.toggled.connect(lambda checked: self._on_display_toggle(checked))
        aux_layout.addWidget(self.chk_bbox)

        self.chk_measurement = QCheckBox("📏 Линии измерений")
        self.chk_measurement.setChecked(False)  # По умолчанию выключено
        self.chk_measurement.toggled.connect(lambda checked: self._on_display_toggle(checked))
        aux_layout.addWidget(self.chk_measurement)

        right_layout.addWidget(auxiliary_group)

        right_layout.addStretch()

        self.right_panel.setMaximumWidth(250)
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setSizes([180, 950, 250])
        self._saved_splitter_sizes = self.main_splitter.sizes()
        if len(self._saved_splitter_sizes) >= 1:
            self._saved_left_size = self._saved_splitter_sizes[0]
        if len(self._saved_splitter_sizes) >= 3:
            self._saved_right_size = self._saved_splitter_sizes[2]

        # Подключаем сигнал смены вкладки ПОСЛЕ того, как весь UI создан
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Устанавливаем начальное состояние правой панели (вкладка "Изображение" активна по умолчанию)
        self.right_panel.setVisible(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
    
    def _setup_menu(self):
        """Настройка меню"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("Файл")
        file_menu.addAction("Открыть папку...", self._open_folder, "Ctrl+O")
        file_menu.addSeparator()
        file_menu.addAction("Сохранить TPS", self._save_current, "Ctrl+S")
        file_menu.addAction("Сохранить все TPS", self._save_all)
        file_menu.addSeparator()
        file_menu.addAction("Экспорт в Excel...", self._export_excel)
        file_menu.addSeparator()
        file_menu.addAction("Выход", self.close)
        
        edit_menu = menubar.addMenu("Правка")
        edit_menu.addAction("Удалить крыло", self._delete_selected_wing, "Delete")
        
        view_menu = menubar.addMenu("Вид")
        view_menu.addAction("Увеличить", lambda: self._zoom(1.25))
        view_menu.addAction("Уменьшить", lambda: self._zoom(0.8))
        view_menu.addAction("По размеру", self._fit_view)
        view_menu.addAction("1:1", self._zoom_100)
        view_menu.addSeparator()
        view_menu.addAction("Настройки точек...", self._show_point_settings)
        
        help_menu = menubar.addMenu("Справка")
        help_menu.addAction("Проверить обновление", lambda: self._check_for_updates(manual=True))
        help_menu.addSeparator()
        help_menu.addAction("О программе", self._show_about)

        gpt_menu = menubar.addMenu("GPT")
        gpt_menu.addAction("Настройки GPT...", self._show_gpt_settings)
    
    def _setup_toolbar(self):
        """Настройка панели инструментов"""
        toolbar = QToolBar("Инструменты")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
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
        
        toolbar.addSeparator()
        toolbar.addAction("⚡ Обработать", self._process_smart)
        toolbar.addAction("💾 Сохранить", self._save_current)

        # Кнопки сворачивания панелей
        toolbar.addSeparator()
        toolbar.addAction("⬅ панель", self._toggle_left_panel)
        toolbar.addAction("панель ➡", self._toggle_right_panel)

        # Спейсер и чекбокс одиночного крыла справа
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.chk_single_wing = QCheckBox("Режим одиночного крыла")
        self.chk_single_wing.setToolTip("Анализ/графики по всем фото сразу (1 фото = 1 крыло)")
        self.chk_single_wing.setChecked(False)
        self.chk_single_wing.toggled.connect(self._toggle_single_wing_mode)
        toolbar.addWidget(self.chk_single_wing)
    
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

    def _on_tab_changed(self, index):
        """Обработка смены вкладки"""
        # Показываем правую панель только на вкладке "Изображение" (index=0)
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

        # Если открыли вкладку общей интерпретации — пересчитать (лениво)
        if self.tab_widget.widget(index) is self.global_interpretation_widget:
            self._update_global_interpretation(force=True)

    def _apply_light_theme(self):
        """Применить светлую тему оформления"""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                color: #222222;
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
        """)

    def _load_models(self):
        """Загрузка моделей"""
        try:
            from ultralytics import YOLO

            # В сборках PyInstaller модели могут лежать в _MEIPASS, рядом с EXE
            # или в _internal. Оставляем и старые пути исходников.
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
            
            # Поиск модели детекции
            for name in ["yolo_detect_best.pt", "detect_best.pt"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        print(f"Загрузка модели детекции: {path}")
                        self.model_det = YOLO(str(path))
                        break
                if self.model_det:
                    break

            if not self.model_det:
                print(f"ОШИБКА: Модель детекции не найдена! Искали в: {search_dirs}")

            # Поиск модели позы
            for name in ["yolo_pose_best.pt", "pose_best.pt", "best.pt"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        print(f"Загрузка модели позы: {path}")
                        self.model_pose = YOLO(str(path))
                        break
                if self.model_pose:
                    break

            if not self.model_pose:
                print(f"ОШИБКА: Модель позы не найдена! Искали в: {search_dirs}")
            
            # Поиск модели Stage2
            for name in ["stage2_best.pth", "stage2.pth"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        self.model_stage2 = load_stage2_model(str(path), self.device)
                        break
                if self.model_stage2:
                    break

            # Поиск портативной Stage2 (нормализованный выход, старая логика)
            for name in ["stage2_portable.pth", "stage2_portable_best.pth", "stage2_old.pth"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        self.model_stage2_portable = load_stage2_portable_model(str(path), self.device)
                        break
                if self.model_stage2_portable:
                    break

            # Поиск модели SubPixel
            for name in ["subpixel_best.pth", "subpixel.pth"]:
                for search_dir in search_dirs:
                    path = search_dir / name
                    if path.exists():
                        self.model_subpixel = load_subpixel_model(str(path), self.device)
                        break
                if self.model_subpixel:
                    break

            status = []
            if self.model_det:
                status.append("Det✓")
            if self.model_pose:
                status.append("Pose✓")
            if self.model_stage2:
                status.append("Stage2✓")
            if self.model_stage2_portable:
                status.append("Stage2-old✓")
            if self.model_subpixel:
                status.append("SubPixel✓")
            self.statusBar().showMessage(f"Модели: {' | '.join(status) if status else 'не найдены'}")
            
        except ImportError:
            self.statusBar().showMessage("ultralytics не установлен - обработка недоступна")
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_point_settings(self):
        """Показать настройки точек"""
        from .dialogs import PointSettingsDialog
        dialog = PointSettingsDialog(self.point_radius, self.point_color, self)
        if dialog.exec_():
            self.point_radius, self.point_color = dialog.get_settings()
            self._update_display()
    
    def _open_folder(self):
        """Открыть папку с изображениями"""
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку")
        if folder:
            self.current_folder = Path(folder)
            self._load_folder()
    
    def _load_folder(self):
        """Загрузить файлы из папки"""
        if not self.current_folder:
            return
        
        self.images.clear()
        self.file_list.clear()
        
        # Собираем уникальные файлы (на Windows *.jpg и *.JPG возвращают одни и те же файлы)
        images_set = set()
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            images_set.update(self.current_folder.glob(ext))
        images = list(images_set)
        
        for idx, img_path in enumerate(sorted(images), start=1):
            img_data = ImageData(path=img_path)
            self.images[str(img_path)] = img_data
            
            tps_path = img_path.with_suffix('.tps')
            if tps_path.exists():
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
    
    def _load_tps_for_image(self, img_data: ImageData, tps_path: Path):
        """Загрузить TPS файл (через tps_io)"""
        try:
            load_tps_into_image(img_data, tps_path)
            # Точки из TPS считаем ground truth
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
        
        pixmap = QPixmap(path)
        self.current_image.width = pixmap.width()
        self.current_image.height = pixmap.height()
        
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
        self.lbl_files_stats.setText(f"{with_data}/{total}")
    
    def _refresh_batch_table(self):
        """Обновить сводную таблицу - пересчитать анализ для всех изображений"""
        # Пересчитываем анализ для всех изображений с крыльями
        # Используем calculate_analysis_results вместо update_statistics,
        # чтобы избежать обновления UI для каждого изображения
        for img_data in self.images.values():
            if img_data.wings:
                self.analysis_widget.calculate_analysis_results(img_data)

        # Теперь обновляем таблицу с новыми результатами
        self.batch_widget.update_batch_results(self.images)
    
    def _on_display_toggle(self, checked):
        """Переключение отображения"""
        # Обновляем флаги отображения
        self.show_gt = self.chk_gt.isChecked()
        self.show_yolo = self.chk_yolo_raw.isChecked()
        self.show_stage1 = self.chk_stage1.isChecked()
        self.show_stage2 = self.chk_stage2.isChecked()
        self.show_bboxes = self.chk_bbox.isChecked()
        self.show_measurement_lines = self.chk_measurement.isChecked()
        
        # Принудительно обновляем отображение
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
                wing.point_sources[point_idx] = model_type

        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()

    def _get_point_model_selection(self):
        """Считать выбранные модели для каждой точки из радиокнопок"""
        selection = []
        for group in self.point_model_groups:
            checked = group.checkedButton()
            selection.append(checked.property('model_type') if checked else 'stage2')
        return selection

    def _apply_point_selection(self, scope: str):
        """
        Применить текущий выбор моделей точек.
        scope: 'current' — только текущее фото; 'all' — все открытые.
        """
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

        # Получаем индекс выбранного крыла
        selected_wing_idx = self.wings_table.currentRow()
        if selected_wing_idx < 0 or selected_wing_idx >= len(self.current_image.wings):
            # Если ничего не выбрано, применяем ко всем крыльям
            wings_to_update = self.current_image.wings
        else:
            # Иначе только к выбранному крылу
            wings_to_update = [self.current_image.wings[selected_wing_idx]]

        # Обновляем данные в крыльях
        for wing in wings_to_update:
            # Обновляем источники для всех точек
            for point_idx in range(NUM_POINTS):
                if point_idx < len(wing.point_sources):
                    wing.point_sources[point_idx] = model_type
            # Обновляем активную модель крыла
            wing.active_model = model_type

        # Обновляем радиокнопки в UI
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
        """Обновить отображение"""
        if not self.current_image:
            return
        
        # Очистка
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
        
        self._sort_wings_internal()
        for wing_idx, wing in enumerate(self.current_image.wings):
            cx, cy = wing.get_center()
            
            is_ok = wing.analysis.is_identified if wing.analysis else False
            wing_label = WingLabelItem(wing_idx, cx, cy, is_ok)
            self.scene.addItem(wing_label)
            self.wing_labels.append(wing_label)
            
            # BBOX
            if self.show_bboxes and wing.bbox:
                bbox_item = BBoxItem(wing.bbox.x1, wing.bbox.y1, wing.bbox.x2, wing.bbox.y2, wing_idx)
                self.scene.addItem(bbox_item)
                self.bbox_items.append(bbox_item)
            
            # Линии измерений
            if self.show_measurement_lines and len(wing.points) == 8:
                points = wing.get_active_points()
                self._draw_measurement_lines(points, wing.analysis, wing.bbox)
            
            problem_points = wing.analysis.problem_points if wing.analysis else []
            active_points = wing.get_active_points()

            # АКТИВНЫЕ ТОЧКИ - ВСЕГДА показываются (это точки, которые идут в расчет и TPS)
            # Цвет точки зависит от её источника (yolo/stage1/stage2/gt)
            if active_points:
                for point_idx in range(min(8, len(active_points))):
                    px, py = active_points[point_idx]
                    if px == 0 and py == 0:
                        continue  # Пропускаем неинициализированные точки
                    is_problem = point_idx in problem_points

                    # Определяем источник и цвет точки
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'

                    # Цвет зависит от источника
                    if source == 'yolo':
                        point_color = COLOR_YOLO
                    elif source == 'stage1':
                        point_color = COLOR_STAGE1
                    elif source == 'stage2':
                        point_color = COLOR_STAGE2
                    elif source == 'gt':
                        point_color = COLOR_GT
                    elif source == 'manual':
                        point_color = COLOR_STAGE2
                    else:
                        point_color = COLOR_STAGE2

                    global_idx = wing_idx * 8 + point_idx
                    pt_item = PointItem(
                        px, py, global_idx, wing_idx, point_idx,
                        radius=self.point_radius, color=point_color,
                        is_problem=is_problem, source_type=source
                    )
                    # Активные точки должны быть поверх всех остальных (z-value = 200)
                    pt_item.setZValue(200)

                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)
            # ДОПОЛНИТЕЛЬНЫЕ ТОЧКИ ДЛЯ СРАВНЕНИЯ (оверлеи) - показываются только если включены соответствующие чекбоксы
            # Это точки из других моделей, которые НЕ используются в расчетах, но показываются для сравнения

            # YOLO точки для сравнения
            if self.show_yolo and hasattr(wing, 'points_yolo') and wing.points_yolo:
                for point_idx, point in enumerate(wing.points_yolo):
                    if point_idx >= 8:
                        break
                    # Проверяем, что это не активная точка
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'yolo':
                        continue  # Эта точка уже показана как активная
                    # Показываем как дополнительную точку БЕЗ номера
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_YOLO,
                        is_problem=False, source_type='yolo_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            # Stage1 точки для сравнения
            if self.show_stage1 and hasattr(wing, 'points_stage1') and wing.points_stage1:
                for point_idx, point in enumerate(wing.points_stage1):
                    if point_idx >= 8:
                        break
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'stage1':
                        continue  # Эта точка уже показана как активная
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_STAGE1,
                        is_problem=False, source_type='stage1_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            # Stage2 точки для сравнения
            if self.show_stage2 and hasattr(wing, 'points_stage2') and wing.points_stage2:
                for point_idx, point in enumerate(wing.points_stage2):
                    if point_idx >= 8:
                        break
                    source = wing.point_sources[point_idx] if point_idx < len(wing.point_sources) else 'stage2'
                    if source == 'stage2':
                        continue  # Эта точка уже показана как активная
                    pt_item = PointItem(
                        point.x, point.y, -100, wing_idx, point_idx,
                        radius=self.point_radius * 0.7, color=COLOR_STAGE2,
                        is_problem=False, source_type='stage2_compare'
                    )
                    pt_item.setOpacity(0.5)
                    pt_item.setZValue(90)
                    self.scene.addItem(pt_item)
                    self.point_items.append(pt_item)

            # Ground Truth точки (TPS) - показываем если включен чекбокс для сравнения
            # Это точки из TPS файла, если они отличаются от активных точек
            if self.show_gt:
                # Показываем только если активные точки НЕ являются GT
                # и если есть отдельные Ground Truth точки для сравнения
                if hasattr(wing, 'points') and wing.points:
                    # Проверяем, что активные точки не являются GT
                    source = wing.point_sources[0] if wing.point_sources else 'stage2'
                    if source != 'gt':
                        for point_idx, point in enumerate(wing.points):
                            if point_idx >= 8:
                                break
                            # Проверяем, что это не те же точки, что активные
                            if point_idx < len(active_points):
                                apx, apy = active_points[point_idx]
                                if abs(point.x - apx) < 0.1 and abs(point.y - apy) < 0.1:
                                    continue  # Это те же точки, что активные, пропускаем
                            # Дополнительные точки показываем БЕЗ номеров (global_idx не используется)
                            pt_item = PointItem(
                                point.x, point.y, -100, wing_idx, point_idx,  # global_idx < 0 - без номера
                                radius=self.point_radius * 0.7, color=COLOR_GT,
                                is_problem=False, source_type='gt_compare'
                            )
                            pt_item.setOpacity(0.5)
                            pt_item.setZValue(90)  # Ниже активных точек
                            self.scene.addItem(pt_item)
                            self.point_items.append(pt_item)
        
        self._update_wings_table()
        
        self.lbl_filename.setText(f"Файл: {self.current_image.path.name}")
        self.lbl_size.setText(f"{self.current_image.width}×{self.current_image.height}")
        
        total_wings = len(self.current_image.wings)
        identified = sum(1 for w in self.current_image.wings if w.analysis and w.analysis.is_identified)
        self.lbl_wings_count.setText(f"Крыльев: {total_wings} (✓{identified})")
    
    def _draw_measurement_lines(self, points, analysis, bbox=None):
        """Отрисовка линий измерений"""
        if len(points) != 8:
            return
        
        p1, p2, p3, p4, p5, p6, p7, p8 = points
        
        # P1-P2 (базовая линия)
        line = MeasurementLineItem(p1[0], p1[1], p2[0], p2[1], QColor(0, 100, 255), 2, Qt.SolidLine)
        self.scene.addItem(line)
        self.measurement_lines.append(line)

        # Убраны все красные и зеленые перпендикулярные линии по запросу пользователя
        
        # P3-P4, P5-P6, P6-P7, P5-P7
        for (pa, pb, color, style) in [
            (p3, p4, QColor(200, 0, 200), Qt.SolidLine),
            (p5, p6, QColor(255, 50, 50), Qt.SolidLine),
            (p6, p7, QColor(180, 0, 0), Qt.SolidLine),
            (p5, p7, QColor(255, 100, 150), Qt.DashDotLine),
        ]:
            line = MeasurementLineItem(pa[0], pa[1], pb[0], pb[1], color, 2, style)
            self.scene.addItem(line)
            self.measurement_lines.append(line)
    
    def _sort_wings_internal(self):
        """Сортировка крыльев"""
        if not self.current_image or not self.current_image.wings:
            return
        
        wings_with_centers = [(wing, *wing.get_center()) for wing in self.current_image.wings]
        wings_with_centers.sort(key=lambda w: (w[2], w[1]))
        
        rows = []
        current_row = []
        current_y = None
        row_tolerance = 100
        
        for wing, cx, cy in wings_with_centers:
            if current_y is None or abs(cy - current_y) < row_tolerance:
                current_row.append((wing, cx, cy))
                if current_y is None:
                    current_y = cy
            else:
                rows.append(current_row)
                current_row = [(wing, cx, cy)]
                current_y = cy
        
        if current_row:
            rows.append(current_row)
        
        sorted_wings = []
        for row in rows:
            row.sort(key=lambda w: w[1])
            sorted_wings.extend([w[0] for w in row])
        
        self.current_image.wings = sorted_wings
    
    def _update_wings_table(self):
        """Обновить таблицу крыльев"""
        if not self.current_image:
            self.wings_table.setRowCount(0)
            return

        self.wings_table.setRowCount(len(self.current_image.wings))

        for i, wing in enumerate(self.current_image.wings):
            self.wings_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

            if wing.analysis:
                breeds = ", ".join(wing.analysis.breeds) if wing.analysis.breeds else "—"
                self.wings_table.setItem(i, 1, QTableWidgetItem(breeds))
                self.wings_table.setItem(i, 2, QTableWidgetItem(f"{wing.analysis.CI:.2f}"))

                status = "✅" if wing.analysis.is_identified else "❌"
                self.wings_table.setItem(i, 3, QTableWidgetItem(status))
            else:
                # Если анализ отсутствует, заполняем пустыми значениями
                self.wings_table.setItem(i, 1, QTableWidgetItem("—"))
                self.wings_table.setItem(i, 2, QTableWidgetItem("—"))
                self.wings_table.setItem(i, 3, QTableWidgetItem("❌"))

        # Принудительно обновляем виджет таблицы
        self.wings_table.viewport().update()
    
    def _on_wing_selected(self, item):
        """Выбор крыла"""
        row = item.row()
        if row < 0 or not self.current_image:
            return

        self.selected_wing_idx = row

        for pt_item in self.point_items:
            pt_item.set_selected(False)

        if row < len(self.current_image.wings):
            for pt_item in self.point_items:
                if pt_item.wing_idx == row and pt_item.source_type == 'active':
                    pt_item.set_selected(True)

            cx, cy = self.current_image.wings[row].get_center()

            # Автоматически увеличиваем масштаб до ~1.6x (эквивалент двух нажатий "-" от 2x) и центрируем на крыле
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
            if pt_item.wing_idx == wing_idx and pt_item.source_type == 'active':
                pt_item.set_selected(True)

        cx, cy = self.current_image.wings[wing_idx].get_center()
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
        
        if mode != EditMode.ADD:
            self._cancel_adding()
    
    def _on_point_clicked(self, global_idx: int, wing_idx: int, point_idx: int):
        """Клик по точке"""
        for item in self.point_items:
            item.set_selected(False)
        
        if 0 <= global_idx < len(self.point_items):
            self.point_items[global_idx].set_selected(True)
        
        self.wings_table.selectRow(wing_idx)
    
    def _on_point_moved(self, wing_idx: int, point_idx: int, x: float, y: float):
        """Перемещение точки"""
        if not self.current_image:
            return

        if 0 <= wing_idx < len(self.current_image.wings):
            wing = self.current_image.wings[wing_idx]
            if 0 <= point_idx < len(wing.points):
                wing.points[point_idx].x = x
                wing.points[point_idx].y = y
                wing.points[point_idx].is_manual = True
                if point_idx < len(wing.point_sources):
                    wing.point_sources[point_idx] = 'manual'
                self.current_image.is_modified = True

                wing.analyze(image_height=self.current_image.height if self.current_image.height > 0 else None)
                self.current_image.analyze_all_wings()  # Пересчитываем все крылья
                self._update_display()
                self._update_analysis_widget()
                self._update_interpretation_widgets()
                self._update_wings_table()  # Обновляем таблицу крыльев ПОСЛЕ всех расчетов
                self.batch_widget.update_batch_results(self.images)
    
    def _on_bbox_created(self, x1, y1, x2, y2):
        """Создание рамки"""
        if not self.current_image:
            return

        wing = Wing(
            points=[WingPoint(x=0, y=0) for _ in range(8)],
            bbox=BBox(x1, y1, x2, y2)
        )
        self.current_image.wings.append(wing)
        self.current_image.is_modified = True
        self._update_display()

    def _on_bbox_changed(self, wing_idx, x1, y1, x2, y2):
        """Изменение размера рамки"""
        if not self.current_image:
            return

        if 0 <= wing_idx < len(self.current_image.wings):
            wing = self.current_image.wings[wing_idx]
            wing.bbox = BBox(x1, y1, x2, y2)
        self.current_image.is_modified = True
        self.current_image.analyze_all_wings()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)

    def _on_point_delete(self, wing_idx, point_idx):
        """Удаление точки или крыла"""
        if not self.current_image:
            return

        if wing_idx < 0 or wing_idx >= len(self.current_image.wings):
            return

        wing = self.current_image.wings[wing_idx]

        # Если point_idx указан - удаляем конкретную точку
        if point_idx >= 0:
            reply = QMessageBox.question(
                self, "Удаление", f"Удалить точку {point_idx + 1} с крыла {wing_idx + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Удаляем точку из активной модели
                active_model = wing.active_model
                points_dict = {
                    'yolo': wing.points_yolo,
                    'stage1': wing.points_stage1,
                    'stage2': wing.points_stage2,
                    'gt': wing.points
                }

                if active_model in points_dict and points_dict[active_model]:
                    points = points_dict[active_model]
                    if 0 <= point_idx < len(points):
                        # Удаляем точку (заменяем на None или удаляем объект)
                        # В WingPoint можно установить координаты в 0 или удалить из списка
                        points[point_idx].x = 0
                        points[point_idx].y = 0
                        self.current_image.is_modified = True
                        wing.analyze()  # Пересчитываем только это крыло
                        self._update_display()
                        self._update_analysis_widget()
                        self._update_interpretation_widgets()
        else:
            # Удаляем всё крыло
            reply = QMessageBox.question(
                self, "Удаление", f"Удалить крыло {wing_idx + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del self.current_image.wings[wing_idx]
                self.current_image.is_modified = True
                self.current_image.analyze_all_wings()  # Пересчитываем все крылья
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
        """Клик по сцене"""
        if self.edit_mode != EditMode.ADD or not self.current_image:
            return
        
        self.adding_points.append((x, y))
        
        global_idx = len(self.current_image.wings) * NUM_POINTS + len(self.adding_points)
        pt_item = PointItem(
            x, y, global_idx - 1, -1, len(self.adding_points) - 1,
            radius=self.point_radius, color=QColor(255, 165, 0)
        )
        self.scene.addItem(pt_item)
        self.temp_add_items.append(pt_item)
        
        self.statusBar().showMessage(f"Точек: {len(self.adding_points)}/8")
        
        if len(self.adding_points) == NUM_POINTS:
            wing = Wing(points=[WingPoint(x=pt[0], y=pt[1], is_manual=True) for pt in self.adding_points])
            wing.analyze(image_height=self.current_image.height if self.current_image.height > 0 else None)
            self.current_image.wings.append(wing)
            self.current_image.is_modified = True
            self._cancel_adding()
            self._update_display()
            self._update_analysis_widget()
            self.batch_widget.update_batch_results(self.images)
            self.statusBar().showMessage("Крыло добавлено!")
    
    def _cancel_adding(self):
        """Отмена добавления"""
        self.adding_points.clear()
        for item in self.temp_add_items:
            self.scene.removeItem(item)
        self.temp_add_items.clear()
    
    def _cancel_action(self):
        """Отмена действия"""
        if self.edit_mode == EditMode.ADD and self.adding_points:
            self._cancel_adding()
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
            self.statusBar().showMessage("Выберите файлы")
    
    def _process_images(self, paths):
        """Обработать изображения"""
        if not self.model_det or not self.model_pose:
            QMessageBox.critical(self, "Ошибка", "Модели не загружены!")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(paths))

        self.worker = ProcessingWorker(
            paths, self.model_det, self.model_pose,
            self.model_stage2, self.device,
            model_subpixel=self.model_subpixel,
            model_stage2_portable=self.model_stage2_portable
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_progress(self, current, total, message):
        """Прогресс обработки"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.statusBar().showMessage(message)
        QApplication.processEvents()
    
    def _on_finished(self, results):
        """Завершение обработки"""
        self.progress_bar.setVisible(False)
        
        for path_str, wings in results.items():
            if path_str in self.images:
                img_data = self.images[path_str]
                img_data.wings = wings
                img_data.is_processed = True
                
                # Убедимся, что размеры изображения установлены для правильных расчетов
                if img_data.height == 0:
                    pixmap = QPixmap(str(img_data.path))
                    img_data.width = pixmap.width()
                    img_data.height = pixmap.height()
                
                img_data.analyze_all_wings()
        
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            path = item.data(Qt.UserRole)
            if path in self.images and self.images[path].wings:
                text = item.text()
                if text.startswith("â—‹"):
                    item.setText("✓" + text[1:])
        
        self._update_files_stats()
        self._update_display()
        self._update_analysis_widget()
        self._update_interpretation_widgets()
        self.batch_widget.update_batch_results(self.images)
        
        self.statusBar().showMessage(f"Готово: {len(results)}")
    
    def _on_error(self, msg):
        """Ошибка обработки"""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", msg)

    def _toggle_left_panel(self):
        """Свернуть/развернуть левую панель со списком файлов"""
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
        """Свернуть/развернуть правую панель"""
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
        self._gpt_model = cfg.get("model", "gpt-4o-mini")
        self._gpt_enabled = bool(cfg.get("enabled", False) and self._gpt_api_key)
        self._init_gpt_client()

    def _save_gpt_config(self):
        cfg = {"api_key": self._gpt_api_key, "model": self._gpt_model, "enabled": self._gpt_enabled}
        try:
            self._gpt_config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"Не удалось сохранить GPT конфиг: {e}")

    def _init_gpt_client(self):
        try:
            if self._gpt_enabled and self._gpt_api_key:
                from openai import OpenAI
                self._gpt_client = OpenAI(api_key=self._gpt_api_key)
            else:
                self._gpt_client = None
        except Exception as e:
            print(f"GPT инициализация не удалась: {e}")
            self._gpt_client = None

    def _show_gpt_settings(self):
        from PyQt5.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QCheckBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки GPT")
        layout = QFormLayout(dlg)
        key_edit = QLineEdit(self._gpt_api_key)
        key_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        model_edit = QLineEdit(self._gpt_model or "gpt-4o-mini")
        enabled_chk = QCheckBox("Включить GPT интерпретацию")
        enabled_chk.setChecked(self._gpt_enabled)
        layout.addRow("API ключ:", key_edit)
        layout.addRow("Модель:", model_edit)
        layout.addRow("", enabled_chk)

        test_btn = QPushButton("Проверить ключ")

        def _test_key():
            key = key_edit.text().strip()
            model_name = model_edit.text().strip() or "gpt-4o-mini"
            if not key:
                QMessageBox.warning(dlg, "GPT", "Введите API ключ.")
                return
            try:
                try:
                    from openai import OpenAI
                except ImportError:
                    QMessageBox.critical(
                        dlg,
                        "GPT",
                        "Библиотека openai не установлена. Установи её: pip install -r requirements.txt",
                    )
                    return
                try:
                    client = OpenAI(api_key=key)
                    client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=5,
                        temperature=0.0,
                    )
                    QMessageBox.information(dlg, "GPT", "Ключ работает.")
                except Exception as e:
                    QMessageBox.critical(dlg, "GPT", f"Ошибка проверки: {e}")
            except Exception as e:
                QMessageBox.critical(dlg, "GPT", f"Ошибка проверки: {e}")

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
            self._save_gpt_config()
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
            self.analysis_widget.update_statistics(agg_wings if agg_wings else [])
        else:
            self.analysis_widget.update_statistics(self.current_image)

    def _collect_all_wings(self):
        """Собрать все крылья со всех изображений (возвращает wings, width, height)"""
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
        # Пер-фото интерпретация
        self.interpretation_widget.update_interpretation(self.current_image)

        # Общая интерпретация — только если открыта соответствующая вкладка (чтобы избежать тормозов)
        if self.tab_widget.currentWidget() is self.global_interpretation_widget:
            self._update_global_interpretation(force=True)
        else:
            if self.single_wing_mode:
                self.global_interpretation_widget.set_message("Режим одиночного крыла: общая интерпретация отключена.")
            else:
                self.global_interpretation_widget.set_message("Откройте вкладку \"🌐 Общая интерпретация\" для расчёта.")

    def _update_global_interpretation(self, force: bool = False):
        """Обновить общую интерпретацию по всем файлам (лениво, только при открытой вкладке)"""
        if self.single_wing_mode:
            self.global_interpretation_widget.set_message("Режим одиночного крыла: общая интерпретация отключена.")
            return
        if not force and self.tab_widget.currentWidget() is not self.global_interpretation_widget:
            return
        self.global_interpretation_widget.update_global(self.images, self.single_wing_mode)
    
    def _save_current(self):
        """Сохранить текущий TPS"""
        if not self.current_image:
            return
        self._save_tps(self.current_image)
        self.statusBar().showMessage(f"Сохранено: {self.current_image.path.stem}.tps")
    
    def _save_all(self):
        """Сохранить все TPS"""
        saved = 0
        for img_data in self.images.values():
            if img_data.wings:
                self._save_tps(img_data)
                saved += 1
        self.statusBar().showMessage(f"Сохранено: {saved}")
    
    def _save_tps(self, img_data):
        """Сохранить TPS файл в формате WingsDig"""
        if not img_data.wings:
            return
        
        tps_path = img_data.path.with_suffix('.tps')
        save_tps_from_image(img_data, tps_path)
        img_data.is_modified = False
    
    def _export_excel(self):
        """Экспорт в Excel"""
        if not self.current_image:
            return
        self.analysis_widget._export_to_excel()
    
    def _fit_view(self):
        """По размеру"""
        self.view.fit_in_view()
    
    def _zoom(self, factor):
        """Масштабирование"""
        self.view.scale(factor, factor)
        self.view._zoom *= factor
    
    def _zoom_100(self):
        """Масштаб 1:1"""
        self.view.resetTransform()
        self.view._zoom = 1.0

    def _auto_check_for_updates(self):
        """Автоматическая проверка обновлений после запуска EXE."""
        if getattr(sys, "frozen", False):
            self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool = False):
        """Проверить наличие новой версии."""
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
        """Обработка результата проверки обновлений."""
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
        """Ошибка проверки обновлений."""
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
        """Показать верхнюю плашку о доступном обновлении."""
        published_at = f", опубликовано {info['published_at']}" if info.get("published_at") else ""
        self.lbl_update_banner.setText(
            f"Доступна новая версия {info['version']} (у вас {APP_VERSION}{published_at})."
        )
        self.update_banner.setVisible(True)

    def _hide_update_banner(self):
        """Скрыть верхнюю плашку обновления."""
        self.update_banner.setVisible(False)

    def _start_pending_update(self):
        """Запустить скачивание найденного обновления."""
        if self._update_info:
            self._begin_update_download(self._update_info)

    def _prompt_update(self, info: dict):
        """Показать пользователю найденное обновление."""
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
        """Скачать обновление или открыть страницу загрузки."""
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
        """Обновить прогресс скачивания."""
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
        """После скачивания предложить применить EXE."""
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
        """Ошибка скачивания обновления."""
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
        """Подготовить замену текущего EXE после выхода из приложения."""
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
        dialog.resize(560, 280)

        layout = QVBoxLayout(dialog)

        current_update = "обновления будут проверяться с сервера"
        if self._update_info:
            current_update = f"доступна версия {html.escape(self._update_info['version'])}"

        label = QLabel(
            f"<h2>{html.escape(APP_NAME)} v{html.escape(APP_VERSION)}</h2>"
            f"<p>Автоматическая морфометрия крыльев пчёл</p>"
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
        """Закрытие окна"""
        if self._skip_unsaved_prompt or self._confirm_close():
            event.accept()
            return
        event.ignore()
