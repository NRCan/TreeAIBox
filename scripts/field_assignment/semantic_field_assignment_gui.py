#!/usr/bin/env python3
"""
Field Tree Assignment GUI (PySide6 / PyQt6)
===========================================

A modern graphical interface for matching LiDAR-extracted trees (trunk metrics)
with Ground-Truth Field Survey inventories using spatial proximity and shared
physical attributes (DBH, Height / Height Class).

Features:
---------
- Auto layer detection for ESRI File Geodatabase (.gdb), GeoPackage, Shapefiles
- Interactive sliders & real-time normalized weight percentages
- Choice between Hungarian Global Optimal vs Greedy assignment
- Non-blocking asynchronous worker thread with progress feedback
- Metric summary cards (Match rates, Mean Error, RMSE, DBH Pearson r)
- Interactive searchable & sortable results table with confidence badges
- Height class confusion matrix display
- Export to CSV, Summary Report, and GIS Vector lines (GeoJSON)
- Direct buttons to open results in Excel / Explorer / QGIS
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from collections import defaultdict
import numpy as np

# Ensure scripts directory is on sys.path regardless of execution CWD
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Qt Import Fallback (PySide6 prioritized, PyQt6 compatible)
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
        QFrame, QSplitter, QMessageBox, QLineEdit, QGroupBox, QComboBox,
        QDoubleSpinBox, QSlider, QTableWidget, QTableWidgetItem, QHeaderView,
        QTabWidget, QGridLayout, QAbstractItemView
    )
    from PySide6.QtCore import Qt, QThread, Signal, Slot
    from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QCursor
    QT_BINDING = "PySide6"
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
        QFrame, QSplitter, QMessageBox, QLineEdit, QGroupBox, QComboBox,
        QDoubleSpinBox, QSlider, QTableWidget, QTableWidgetItem, QHeaderView,
        QTabWidget, QGridLayout, QAbstractItemView
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QCursor
    QT_BINDING = "PyQt6"

# Import core backend functions from semantic_field_assignment
from semantic_field_assignment import (
    read_field_points,
    read_lidar_metrics,
    match_trees,
    write_outputs,
    resolve_gdb_path,
    class_to_height_range,
    class_to_midpoint_height,
    HEIGHT_CLASS_RANGES,
    HEIGHT_CLASS_MIDPOINTS
)


# ---------------------------------------------------------------------------
# Background Worker Thread
# ---------------------------------------------------------------------------
class AssignmentWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        try:
            p = self.params
            self.progress.emit(10, "Reading field survey data...")
            field_trees = read_field_points(
                gdb_path=p['gdb'],
                layer=p['layer'],
                height_class_field=p.get('height_class_field', 'hightlevel'),
                dbh_field=p.get('dbh_field', 'dbh_cm'),
                tree_id_field=p.get('tree_id_field', 'treeid'),
                species_field=p.get('species_field', 'species'),
            )
            if not field_trees:
                raise ValueError("No valid tree points found in field data layer.")

            self.progress.emit(35, f"Loaded {len(field_trees)} field trees. Reading LiDAR metrics...")
            lidar_trees = read_lidar_metrics(
                metrics_path=p['metrics'],
                tree_id_field=p.get('lidar_id_field', 'tree_ids'),
                height_field=p.get('lidar_height_field', 'tree_height_m'),
                dbh_field=p.get('lidar_dbh_field', 'dbh_cm'),
                x_field=p.get('lidar_x_field', 'location_x_m'),
                y_field=p.get('lidar_y_field', 'location_y_m')
            )
            if not lidar_trees:
                raise ValueError("No valid LiDAR trees found in metrics CSV.")

            self.progress.emit(60, f"Matching {len(lidar_trees)} LiDAR trees against {len(field_trees)} field trees...")
            assignments = match_trees(
                field_trees=field_trees,
                lidar_trees=lidar_trees,
                tolerance_m=p['tolerance'],
                weight_spatial=p['weight_spatial'],
                weight_dbh=p['weight_dbh'],
                weight_height=p['weight_height'],
                dbh_scale_cm=p['dbh_scale'],
                method=p['method']
            )

            self.progress.emit(85, "Exporting assignment CSV, GIS vectors, and report...")
            write_outputs(
                assignments=assignments,
                lidar_trees=lidar_trees,
                field_trees=field_trees,
                out_dir=p['out_dir'],
                export_geojson=p.get('export_geojson', True)
            )

            self.progress.emit(100, "Matching complete!")
            self.finished.emit({
                'assignments': assignments,
                'lidar_trees': lidar_trees,
                'field_trees': field_trees,
                'out_dir': p['out_dir']
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Main GUI Window
# ---------------------------------------------------------------------------
class FieldAssignmentGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TreeAIBox - LiDAR to Field Inventory Matcher")
        self.resize(1180, 840)
        self.setMinimumSize(960, 680)

        self.worker = None
        self.last_results = None
        self.setup_theme()
        self.init_ui()

    def setup_theme(self):
        """Apply a sleek, modern dark styling palette."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1f29;
                color: #e2e8f0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: bold;
                color: #38bdf8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #1e1f29;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f8fafc;
                selection-background-color: #0284c7;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #38bdf8;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:pressed {
                background-color: #1e293b;
            }
            QPushButton#primaryBtn {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 14px;
                padding: 10px 24px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #0369a1;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #1e293b;
                color: #64748b;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                background-color: #0f172a;
                color: #f8fafc;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 5px;
            }
            QTableWidget {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #f1f5f9;
                selection-background-color: #0369a1;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                padding: 6px;
                border: 1px solid #334155;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                border-radius: 6px;
                background-color: #1e1f29;
            }
            QTabBar::tab {
                background-color: #0f172a;
                color: #94a3b8;
                padding: 8px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1f29;
                color: #38bdf8;
                border: 1px solid #334155;
                border-bottom: 1px solid #1e1f29;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QSlider::groove:horizontal {
                border: 1px solid #334155;
                height: 6px;
                background: #0f172a;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0284c7;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #38bdf8;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
        """)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Banner
        header_layout = QHBoxLayout()
        title_label = QLabel("LiDAR ➔ Field Tree Assignment Engine")
        title_label.setStyleSheet("font-size: 19px; font-weight: bold; color: #f8fafc;")
        subtitle_label = QLabel("Spatial Proximity + Shared DBH & Height Optimization")
        subtitle_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        
        v_title = QVBoxLayout()
        v_title.addWidget(title_label)
        v_title.addWidget(subtitle_label)
        header_layout.addLayout(v_title)
        header_layout.addStretch()

        binding_badge = QLabel(f"Backend: {QT_BINDING} | NumPy & SciPy")
        binding_badge.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; padding: 4px 10px; border-radius: 12px; color: #38bdf8; font-size: 11px;")
        header_layout.addWidget(binding_badge)
        main_layout.addLayout(header_layout)

        # 2. Main Content Splitter (Left: Controls, Right: Visual Dashboard)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # LEFT PANEL: Inputs & Parameters
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)

        # Group 1: Data Inputs
        data_group = QGroupBox("1. Input Data Sources")
        data_layout = QGridLayout(data_group)
        data_layout.setSpacing(8)

        # Field GDB / Vector
        data_layout.addWidget(QLabel("Field Survey (.gdb/shp):"), 0, 0)
        self.field_path_edit = QLineEdit()
        self.field_path_edit.setPlaceholderText("Select .gdb folder or shapefile...")
        self.field_path_edit.editingFinished.connect(lambda: self.auto_populate_layers(self.field_path_edit.text()))
        data_layout.addWidget(self.field_path_edit, 0, 1)
        browse_field_btn = QPushButton("Browse...")
        browse_field_btn.clicked.connect(self.browse_field_data)
        data_layout.addWidget(browse_field_btn, 0, 2)

        # Layer Dropdown
        data_layout.addWidget(QLabel("Survey Layer:"), 1, 0)
        self.layer_combo = QComboBox()
        self.layer_combo.setEditable(True)
        self.layer_combo.setPlaceholderText("Enter or select layer...")
        data_layout.addWidget(self.layer_combo, 1, 1, 1, 2)

        # LiDAR Metrics CSV
        data_layout.addWidget(QLabel("LiDAR Metrics CSV:"), 2, 0)
        self.metrics_path_edit = QLineEdit()
        self.metrics_path_edit.setPlaceholderText("Select trunk_metrics.csv...")
        data_layout.addWidget(self.metrics_path_edit, 2, 1)
        browse_metrics_btn = QPushButton("Browse...")
        browse_metrics_btn.clicked.connect(self.browse_metrics_data)
        data_layout.addWidget(browse_metrics_btn, 2, 2)

        # Output Dir
        data_layout.addWidget(QLabel("Output Directory:"), 3, 0)
        self.out_dir_edit = QLineEdit()
        self.out_dir_edit.setText(os.path.abspath("semantic_assignment_out"))
        data_layout.addWidget(self.out_dir_edit, 3, 1)
        browse_out_btn = QPushButton("Browse...")
        browse_out_btn.clicked.connect(self.browse_output_dir)
        data_layout.addWidget(browse_out_btn, 3, 2)

        left_layout.addWidget(data_group)

        # Group 2: Matching Parameters
        param_group = QGroupBox("2. Matching Weights & Constraints")
        param_layout = QGridLayout(param_group)
        param_layout.setSpacing(10)

        # Algorithm Selection
        param_layout.addWidget(QLabel("Solver Algorithm:"), 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItem("Hungarian Global Optimal (Recommended)", "optimal")
        self.method_combo.addItem("Greedy 1-to-1 Matching", "greedy")
        param_layout.addWidget(self.method_combo, 0, 1, 1, 2)

        # Spatial Tolerance
        param_layout.addWidget(QLabel("Max Search Distance (m):"), 1, 0)
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.5, 50.0)
        self.tol_spin.setSingleStep(0.5)
        self.tol_spin.setValue(2.5)
        param_layout.addWidget(self.tol_spin, 1, 1, 1, 2)

        # DBH Scaling (sigma)
        param_layout.addWidget(QLabel("DBH Tolerance Scale (cm):"), 2, 0)
        self.dbh_scale_spin = QDoubleSpinBox()
        self.dbh_scale_spin.setRange(1.0, 100.0)
        self.dbh_scale_spin.setSingleStep(1.0)
        self.dbh_scale_spin.setValue(12.0)
        param_layout.addWidget(self.dbh_scale_spin, 2, 1, 1, 2)

        # Spatial Weight Slider
        param_layout.addWidget(QLabel("Spatial Proximity:"), 3, 0)
        self.w_spatial_slider = QSlider(Qt.Orientation.Horizontal)
        self.w_spatial_slider.setRange(0, 100)
        self.w_spatial_slider.setValue(50)
        self.w_spatial_lbl = QLabel("50% (0.50)")
        param_layout.addWidget(self.w_spatial_slider, 3, 1)
        param_layout.addWidget(self.w_spatial_lbl, 3, 2)

        # DBH Weight Slider
        param_layout.addWidget(QLabel("DBH Similarity:"), 4, 0)
        self.w_dbh_slider = QSlider(Qt.Orientation.Horizontal)
        self.w_dbh_slider.setRange(0, 100)
        self.w_dbh_slider.setValue(25)
        self.w_dbh_lbl = QLabel("25% (0.25)")
        param_layout.addWidget(self.w_dbh_slider, 4, 1)
        param_layout.addWidget(self.w_dbh_lbl, 4, 2)

        # Height Weight Slider
        param_layout.addWidget(QLabel("Height Class Match:"), 5, 0)
        self.w_height_slider = QSlider(Qt.Orientation.Horizontal)
        self.w_height_slider.setRange(0, 100)
        self.w_height_slider.setValue(25)
        self.w_height_lbl = QLabel("25% (0.25)")
        param_layout.addWidget(self.w_height_slider, 5, 1)
        param_layout.addWidget(self.w_height_lbl, 5, 2)

        self.w_spatial_slider.valueChanged.connect(self.update_weight_labels)
        self.w_dbh_slider.valueChanged.connect(self.update_weight_labels)
        self.w_height_slider.valueChanged.connect(self.update_weight_labels)

        left_layout.addWidget(param_group)

        # Run Button & Progress Bar
        self.run_btn = QPushButton("▶ Run Optimal Assignment")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self.start_assignment)
        left_layout.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_status = QLabel("Ready")
        self.progress_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        left_layout.addWidget(self.progress_bar)
        left_layout.addWidget(self.progress_status)
        left_layout.addStretch()

        splitter.addWidget(left_widget)

        # RIGHT PANEL: Results Dashboard (Tabs)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.tabs = QTabWidget()
        
        # Tab 1: Overview Dashboard
        self.tab_overview = QWidget()
        self.setup_overview_tab()
        self.tabs.addTab(self.tab_overview, "📊 Summary & Metrics")

        # Tab 2: Matched Trees Table
        self.tab_table = QWidget()
        self.setup_table_tab()
        self.tabs.addTab(self.tab_table, "📋 Matched Pairs Table")

        # Tab 3: Detailed Text Report
        self.tab_report = QWidget()
        self.setup_report_tab()
        self.tabs.addTab(self.tab_report, "📄 Full Report Log")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)
        splitter.setSizes([440, 700])

    def setup_overview_tab(self):
        """Construct the summary statistics cards and confusion matrix."""
        layout = QVBoxLayout(self.tab_overview)
        layout.setSpacing(14)

        # Top metric cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        def _create_card(title, initial_val, color="#38bdf8"):
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 10px;
                }}
            """)
            v = QVBoxLayout(frame)
            v.setContentsMargins(4, 4, 4, 4)
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
            lbl_val = QLabel(initial_val)
            lbl_val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            v.addWidget(lbl_title)
            v.addWidget(lbl_val)
            return frame, lbl_val

        self.card_matched, self.val_matched = _create_card("MATCH RATE", "-- / -- (0%)", "#34d399")
        self.card_dist_err, self.val_dist_err = _create_card("AVG DISTANCE ERROR", "-- m", "#38bdf8")
        self.card_dbh_mae, self.val_dbh_mae = _create_card("DBH MAE / RMSE", "-- cm", "#f59e0b")
        self.card_dbh_corr, self.val_dbh_corr = _create_card("DBH CORRELATION (r)", "--", "#a78bfa")

        cards_layout.addWidget(self.card_matched)
        cards_layout.addWidget(self.card_dist_err)
        cards_layout.addWidget(self.card_dbh_mae)
        cards_layout.addWidget(self.card_dbh_corr)
        layout.addLayout(cards_layout)

        # Height Class Agreement Table
        hc_group = QGroupBox("Height Class Agreement Matrix (1 to 5)")
        hc_layout = QVBoxLayout(hc_group)
        self.hc_table = QTableWidget(5, 5)
        self.hc_table.setHorizontalHeaderLabels([f"LiDAR {c}" for c in range(1, 6)])
        self.hc_table.setVerticalHeaderLabels([f"Field {c}" for c in range(1, 6)])
        self.hc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hc_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hc_layout.addWidget(self.hc_table)
        
        hc_legend = QLabel("Height Classes: 1 (<5m) | 2 (5-10m) | 3 (10-15m) | 4 (15-20m) | 5 (>20m)")
        hc_legend.setStyleSheet("color: #94a3b8; font-size: 11px; padding-top: 4px;")
        hc_layout.addWidget(hc_legend)
        layout.addWidget(hc_group)

        # Action Buttons
        actions_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("📁 Open Output Directory")
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.open_folder_btn.setEnabled(False)

        self.open_csv_btn = QPushButton("📊 Open CSV Table")
        self.open_csv_btn.clicked.connect(self.open_output_csv)
        self.open_csv_btn.setEnabled(False)

        actions_layout.addWidget(self.open_folder_btn)
        actions_layout.addWidget(self.open_csv_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        layout.addStretch()

    def setup_table_tab(self):
        """Construct the interactive table of assigned trees."""
        layout = QVBoxLayout(self.tab_table)
        layout.setSpacing(8)

        # Search & View Filter
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("View:"))
        self.table_view_combo = QComboBox()
        self.table_view_combo.addItem("All Records (Matched + Unmatched)", "all")
        self.table_view_combo.addItem("Matched Pairs Only", "matched")
        self.table_view_combo.addItem("Unmatched LiDAR Trees Only", "unmatched_lidar")
        self.table_view_combo.addItem("Unmatched Field Trees Only", "unmatched_field")
        self.table_view_combo.currentIndexChanged.connect(self.filter_table)
        search_layout.addWidget(self.table_view_combo)

        search_layout.addWidget(QLabel("Search:"))
        self.table_search_edit = QLineEdit()
        self.table_search_edit.setPlaceholderText("Filter by Tree ID, Species, etc...")
        self.table_search_edit.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.table_search_edit)
        layout.addLayout(search_layout)

        # Table
        self.results_table = QTableWidget()
        headers = [
            "LiDAR ID", "Field ID", "Distance (m)", "Score",
            "LiDAR DBH (cm)", "Field DBH (cm)", "DBH Diff (cm)",
            "LiDAR Height Class", "Field Height Class", "Species"
        ]
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSortingEnabled(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results_table)

    def setup_report_tab(self):
        """Construct full text report view."""
        layout = QVBoxLayout(self.tab_report)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        layout.addWidget(self.report_text)

    # -----------------------------------------------------------------------
    # Event Handlers & Helper Methods
    # -----------------------------------------------------------------------
    def update_weight_labels(self):
        ws = self.w_spatial_slider.value()
        wd = self.w_dbh_slider.value()
        wh = self.w_height_slider.value()
        total = max(ws + wd + wh, 1)

        pct_s = (ws / total) * 100
        pct_d = (wd / total) * 100
        pct_h = (wh / total) * 100

        self.w_spatial_lbl.setText(f"{pct_s:.0f}% ({ws/total:.2f})")
        self.w_dbh_lbl.setText(f"{pct_d:.0f}% ({wd/total:.2f})")
        self.w_height_lbl.setText(f"{pct_h:.0f}% ({wh/total:.2f})")

    def browse_field_data(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Field Survey File Geodatabase (.gdb)"
        )
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Field Survey Vector File", "",
                "Spatial Datasets (*.gdb *.shp *.gpkg *.geojson *.json);;All Files (*)"
            )
        if path:
            self.field_path_edit.setText(path)
            self.auto_populate_layers(path)

    def auto_populate_layers(self, gdb_path):
        """Detect and populate layer names in the dropdown, handling nested GDB paths."""
        if not gdb_path or not gdb_path.strip():
            return
        gdb_path = gdb_path.strip()
        resolved_path = resolve_gdb_path(gdb_path)

        self.layer_combo.clear()
        try:
            import pyogrio
            layers = pyogrio.list_layers(resolved_path)
            layer_names = [l[0] for l in layers] if len(layers) > 0 and isinstance(layers[0], (list, tuple, np.ndarray)) else list(layers)
            self.layer_combo.addItems([str(name) for name in layer_names])
            # Auto-select layer with stemCenter or tree in name if exists
            for idx, name in enumerate(layer_names):
                name_str = str(name).lower()
                if "stemcenter" in name_str or "field_points" in name_str or "tree" in name_str:
                    self.layer_combo.setCurrentIndex(idx)
                    break
        except Exception as e:
            print(f"Layer detection notice: {e}")
            if not self.layer_combo.count():
                self.layer_combo.addItem("TreePosition_LiDARGeom_Transect1stemCenter")

    def browse_metrics_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select LiDAR Trunk Metrics CSV", "",
            "CSV Files (*_trunk_metrics.csv *.csv);;All Files (*)"
        )
        if path:
            self.metrics_path_edit.setText(path)
            # Default output directory next to metrics
            parent = Path(path).parent
            self.out_dir_edit.setText(str(parent / "field_assignment_out"))

    def browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.out_dir_edit.setText(path)

    def start_assignment(self):
        gdb_path = self.field_path_edit.text().strip()
        layer = self.layer_combo.currentText().strip()
        metrics_path = self.metrics_path_edit.text().strip()
        out_dir = self.out_dir_edit.text().strip()

        if not gdb_path or not os.path.exists(gdb_path):
            QMessageBox.warning(self, "Missing Input", "Please select a valid Field Survey (.gdb/shapefile) path.")
            return
        if not metrics_path or not os.path.exists(metrics_path):
            QMessageBox.warning(self, "Missing Input", "Please select a valid LiDAR metrics CSV path.")
            return

        ws = self.w_spatial_slider.value()
        wd = self.w_dbh_slider.value()
        wh = self.w_height_slider.value()
        total = max(ws + wd + wh, 1)

        params = {
            'gdb': gdb_path,
            'layer': layer,
            'metrics': metrics_path,
            'out_dir': out_dir,
            'tolerance': self.tol_spin.value(),
            'dbh_scale': self.dbh_scale_spin.value(),
            'weight_spatial': ws / total,
            'weight_dbh': wd / total,
            'weight_height': wh / total,
            'method': self.method_combo.currentData(),
            'export_geojson': True
        }

        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(5)
        self.progress_status.setText("Starting assignment worker...")

        self.worker = AssignmentWorker(params)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    @Slot(int, str)
    def on_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.progress_status.setText(msg)

    @Slot(str)
    def on_error(self, err_msg):
        self.run_btn.setEnabled(True)
        self.progress_status.setText(f"Error: {err_msg}")
        QMessageBox.critical(self, "Execution Error", f"Assignment failed:\n\n{err_msg}")

    @Slot(dict)
    def on_finished(self, results):
        self.run_btn.setEnabled(True)
        self.last_results = results
        self.open_folder_btn.setEnabled(True)
        self.open_csv_btn.setEnabled(True)
        self.progress_status.setText("Assignment completed successfully!")

        self.populate_dashboard(results)
        QMessageBox.information(
            self, "Assignment Complete",
            f"Successfully assigned trees!\nSaved outputs to:\n{results['out_dir']}"
        )

    def populate_dashboard(self, results):
        assignments = results['assignments']
        lidar_trees = results['lidar_trees']
        field_trees = results['field_trees']
        out_dir = results['out_dir']

        matched = [a for a in assignments if a.get('lidar_tree_id') is not None and a.get('field_treeid') is not None]
        n_field = len(field_trees)
        field_pct = (n_matched / max(n_field, 1)) * 100
        lidar_pct = (n_matched / max(n_lidar, 1)) * 100

        # Update Metric Cards
        self.val_matched.setText(f"{n_matched} / {n_field} ({field_pct:.1f}%)")

        if matched:
            dists = [a['distance_m'] for a in matched if a.get('distance_m') is not None]
            if dists:
                self.val_dist_err.setText(f"{np.mean(dists):.2f} m (±{np.std(dists):.2f})")
            else:
                self.val_dist_err.setText("N/A")

            dbh_pairs = [(a['lidar_dbh_cm'], a['field_dbh_cm']) for a in matched
                         if a['lidar_dbh_cm'] is not None and a['field_dbh_cm'] is not None]
            if dbh_pairs:
                l_dbhs = np.array([p[0] for p in dbh_pairs])
                f_dbhs = np.array([p[1] for p in dbh_pairs])
                diffs = l_dbhs - f_dbhs
                mae = np.mean(np.abs(diffs))
                rmse = np.sqrt(np.mean(diffs**2))
                self.val_dbh_mae.setText(f"{mae:.1f} / {rmse:.1f} cm")

                if len(dbh_pairs) > 2 and np.std(l_dbhs) > 1e-4 and np.std(f_dbhs) > 1e-4:
                    corr = np.corrcoef(l_dbhs, f_dbhs)[0, 1]
                    self.val_dbh_corr.setText(f"{corr:.3f}")
                else:
                    self.val_dbh_corr.setText("N/A")
            else:
                self.val_dbh_mae.setText("N/A")
                self.val_dbh_corr.setText("N/A")

            # Height Class Confusion Matrix
            conf = defaultdict(lambda: defaultdict(int))
            for a in matched:
                fc = a['field_height_class']
                lc = a['lidar_height_class']
                if 1 <= fc <= 5 and 1 <= lc <= 5:
                    conf[fc][lc] += 1

            for r in range(5):
                for c in range(5):
                    val = conf[r+1][c+1]
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if r == c and val > 0:
                        item.setBackground(QColor("#065f46"))  # Green highlight for diagonal
                    self.hc_table.setItem(r, c, item)

        # Populate Results Table
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(assignments))
        for row_idx, a in enumerate(assignments):
            tid = a['lidar_tree_id']
            fid = a['field_treeid']
            dist = a['distance_m']
            score = a['score']
            l_dbh = a['lidar_dbh_cm']
            f_dbh = a['field_dbh_cm']
            dbh_diff = (l_dbh - f_dbh) if (l_dbh is not None and f_dbh is not None) else None
            l_ht = a['lidar_height_m']
            f_ht = a['field_height_m']
            f_derived_ht = a.get('field_derived_height_m')
            f_ht_range = a.get('field_height_range')
            l_hc = a['lidar_height_class']
            f_hc = a['field_height_class']
            sp = a['field_species']

            cols = [
                str(tid) if tid is not None else "(Unmatched)",
                str(fid) if fid is not None else "(Unmatched)",
                f"{dist:.2f}" if dist is not None else "-",
                f"{score:.3f}" if score is not None else "-",
                f"{l_dbh:.1f}" if l_dbh is not None else "-",
                f"{f_dbh:.1f}" if f_dbh is not None else "-",
                f"{dbh_diff:+.1f}" if dbh_diff is not None else "-",
                str(l_hc) if l_hc else "-",
                str(f_hc) if f_hc else "-",
                str(sp or "-")
            ]

            for col_idx, text in enumerate(cols):
                item = QTableWidgetItem(text)
                if tid is None or fid is None:
                    item.setForeground(QColor("#94a3b8"))  # Dim unmatched rows
                elif col_idx in (0, 1):
                    item.setForeground(QColor("#38bdf8"))  # Cyan for matched IDs
                
                # Add descriptive tooltips to height class columns
                if col_idx == 7 and l_hc:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    l_ht_txt = f"{l_ht:.2f}m" if l_ht is not None else "N/A"
                    item.setToolTip(f"LiDAR Height: {l_ht_txt} | Class {l_hc}: {class_to_height_range(l_hc)}")
                elif col_idx == 8 and f_hc:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(f"Field Height Class {f_hc}: {class_to_height_range(f_hc)}")
                
                self.results_table.setItem(row_idx, col_idx, item)

        self.results_table.setSortingEnabled(True)

        # Populate Report Log
        report_file = os.path.join(out_dir, "match_report.txt")
        if os.path.exists(report_file):
            with open(report_file, 'r', encoding='utf-8') as f:
                self.report_text.setPlainText(f.read())

    def filter_table(self):
        mode = self.table_view_combo.currentData() if hasattr(self, 'table_view_combo') else 'all'
        q = self.table_search_edit.text().strip().lower() if hasattr(self, 'table_search_edit') else ''

        for row in range(self.results_table.rowCount()):
            lidar_item = self.results_table.item(row, 0)
            field_item = self.results_table.item(row, 1)
            lidar_txt = lidar_item.text() if lidar_item else ""
            field_txt = field_item.text() if field_item else ""

            is_matched = (lidar_txt != "(Unmatched)") and (field_txt != "(Unmatched)")
            is_unmatched_lidar = (field_txt == "(Unmatched)")
            is_unmatched_field = (lidar_txt == "(Unmatched)")

            # View mode check
            if mode == 'matched' and not is_matched:
                self.results_table.setRowHidden(row, True)
                continue
            elif mode == 'unmatched_lidar' and not is_unmatched_lidar:
                self.results_table.setRowHidden(row, True)
                continue
            elif mode == 'unmatched_field' and not is_unmatched_field:
                self.results_table.setRowHidden(row, True)
                continue

            # Text query check
            if q:
                matched_query = False
                for col in range(self.results_table.columnCount()):
                    item = self.results_table.item(row, col)
                    if item and q in item.text().lower():
                        matched_query = True
                        break
                self.results_table.setRowHidden(row, not matched_query)
            else:
                self.results_table.setRowHidden(row, False)

    def open_output_folder(self):
        out_dir = self.out_dir_edit.text()
        if os.path.exists(out_dir):
            if sys.platform == 'win32':
                os.startfile(out_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', out_dir])
            else:
                subprocess.Popen(['xdg-open', out_dir])

    def open_output_csv(self):
        out_dir = self.out_dir_edit.text()
        csv_file = os.path.join(out_dir, 'field_assignment.csv')
        if os.path.exists(csv_file):
            if sys.platform == 'win32':
                os.startfile(csv_file)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', csv_file])
            else:
                subprocess.Popen(['xdg-open', csv_file])


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = FieldAssignmentGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
