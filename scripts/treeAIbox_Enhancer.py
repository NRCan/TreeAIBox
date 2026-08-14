#!/usr/bin/env python3
"""
Modern Tree Visualization GUI using PyQt6 and PyVista.
Allows loading LAS files, selecting tree IDs from 'itc' scalar field, and visualizing individual trees.
"""

import sys
import os
import numpy as np
import pandas as pd
import laspy
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit, QLabel, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QFrame, QComboBox, QCheckBox,
    QGroupBox, QScrollArea, QTextEdit, QDialog, QButtonGroup, QRadioButton, QSpinBox, QDoubleSpinBox, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from sklearn.cluster import DBSCAN
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import cdist
from scipy.spatial import KDTree
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing


class ModernButton(QPushButton):
    """Custom button with modern styling."""
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 11px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)


class PolygonSelectionDialog(QDialog):
    """Dialog for 2D polygon selection on flattened point cloud."""
    
    polygon_completed = pyqtSignal(np.ndarray)  # Signal emitted when polygon is completed
    
    def __init__(self, points_3d, itc_values, parent=None):
        super().__init__(parent)
        self.points_3d = points_3d  # Full 3D points
        self.itc_values = itc_values  # Corresponding ITC values
        self.view_mode = 'top'  # 'top', 'bottom', 'front', 'back', 'left', 'right'
        self.polygon_points = []
        self.polygon_lines = []
        self.finished = False
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("2D Polygon Selection")
        # Make window full screen for better visualization
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen)
        self.setMinimumSize(screen.width(), screen.height())
        
        layout = QVBoxLayout(self)
        
        # View selection
        view_group = QHBoxLayout()
        view_label = QLabel("View:")
        view_label.setStyleSheet("font-weight: bold;")
        view_group.addWidget(view_label)
        
        self.view_button_group = QButtonGroup(self)
        
        self.top_view_radio = QRadioButton("Top (XY)")
        self.top_view_radio.setChecked(True)
        self.top_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.top_view_radio)
        view_group.addWidget(self.top_view_radio)
        
        self.bottom_view_radio = QRadioButton("Bottom (XY)")
        self.bottom_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.bottom_view_radio)
        view_group.addWidget(self.bottom_view_radio)
        
        self.front_view_radio = QRadioButton("Front (XZ)")
        self.front_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.front_view_radio)
        view_group.addWidget(self.front_view_radio)
        
        self.back_view_radio = QRadioButton("Back (XZ)")
        self.back_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.back_view_radio)
        view_group.addWidget(self.back_view_radio)
        
        self.left_view_radio = QRadioButton("Left (YZ)")
        self.left_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.left_view_radio)
        view_group.addWidget(self.left_view_radio)
        
        self.right_view_radio = QRadioButton("Right (YZ)")
        self.right_view_radio.toggled.connect(self.on_view_changed)
        self.view_button_group.addButton(self.right_view_radio)
        view_group.addWidget(self.right_view_radio)
        
        view_group.addStretch()
        layout.addLayout(view_group)
        
        # Instructions
        instructions = QLabel("Click to add polygon points. Right-click to finish.\nPoints will be manually placed, not snapped to existing points.")
        instructions.setStyleSheet("font-weight: bold; color: #4CAF50; margin: 10px;")
        layout.addWidget(instructions)
        
        # Matplotlib figure - make it more portrait for tree visualization
        self.figure = Figure(figsize=(6, 10))  # width=6, height=10 inches
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Connect matplotlib events
        self.canvas.mpl_connect('button_press_event', self.on_canvas_click)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.finish_button = QPushButton("Finish Polygon")
        self.finish_button.clicked.connect(self.finish_polygon)
        self.finish_button.setEnabled(False)
        button_layout.addWidget(self.finish_button)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_polygon)
        button_layout.addWidget(self.clear_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Initial plot
        self.plot_points()
        
    def on_view_changed(self):
        """Handle view mode change."""
        if self.top_view_radio.isChecked():
            self.view_mode = 'top'
        elif self.bottom_view_radio.isChecked():
            self.view_mode = 'bottom'
        elif self.front_view_radio.isChecked():
            self.view_mode = 'front'
        elif self.back_view_radio.isChecked():
            self.view_mode = 'back'
        elif self.left_view_radio.isChecked():
            self.view_mode = 'left'
        elif self.right_view_radio.isChecked():
            self.view_mode = 'right'
        
        # Clear polygon when switching views
        self.clear_polygon()
        self.plot_points()
        
    def plot_points(self):
        """Plot the 2D points."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        # Get 2D coordinates based on view mode
        if self.view_mode == 'top':
            points_2d = self.points_3d[:, :2]  # X, Y coordinates
            xlabel = 'X Coordinate'
            ylabel = 'Y Coordinate'
            title = 'Top View (XY) - Click to draw polygon'
        elif self.view_mode == 'bottom':
            # Bottom view: flip Y coordinates to simulate viewing from below
            points_2d = self.points_3d[:, :2].copy()  # X, Y coordinates
            points_2d[:, 1] = -points_2d[:, 1]  # Flip Y axis
            xlabel = 'X Coordinate'
            ylabel = 'Y Coordinate (Flipped)'
            title = 'Bottom View (XY) - Click to draw polygon'
        elif self.view_mode == 'front':
            points_2d = self.points_3d[:, [0, 2]]  # X, Z coordinates
            xlabel = 'X Coordinate'
            ylabel = 'Z Coordinate (Height)'
            title = 'Front View (XZ) - Click to draw polygon'
        elif self.view_mode == 'back':
            # Back view: flip X coordinates to simulate viewing from behind
            points_2d = self.points_3d[:, [0, 2]].copy()  # X, Z coordinates
            points_2d[:, 0] = -points_2d[:, 0]  # Flip X axis
            xlabel = 'X Coordinate (Flipped)'
            ylabel = 'Z Coordinate (Height)'
            title = 'Back View (XZ) - Click to draw polygon'
        elif self.view_mode == 'left':
            points_2d = self.points_3d[:, [1, 2]]  # Y, Z coordinates
            xlabel = 'Y Coordinate'
            ylabel = 'Z Coordinate (Height)'
            title = 'Left View (YZ) - Click to draw polygon'
        elif self.view_mode == 'right':
            # Right view: flip Y coordinates to simulate viewing from right
            points_2d = self.points_3d[:, [1, 2]].copy()  # Y, Z coordinates
            points_2d[:, 0] = -points_2d[:, 0]  # Flip Y axis
            xlabel = 'Y Coordinate (Flipped)'
            ylabel = 'Z Coordinate (Height)'
            title = 'Right View (YZ) - Click to draw polygon'
        else:
            # Default to top view
            points_2d = self.points_3d[:, :2]
            xlabel = 'X Coordinate'
            ylabel = 'Y Coordinate'
            title = 'Top View (XY) - Click to draw polygon'
        
        # Plot points colored by ITC values using the same 9-color scheme as 3D view
        # Create color indices for 9 cycling colors
        color_indices = self.itc_values % 9
        scatter = ax.scatter(points_2d[:, 0], points_2d[:, 1], 
                           c=color_indices, s=3, alpha=0.8, cmap='tab10', vmin=0, vmax=8)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        
        # Set aspect ratio to 'equal' for accurate spatial representation
        # This ensures points maintain their true spatial relationships without distortion
        ax.set_aspect('equal', adjustable='datalim')
        
        # Add colorbar with ITC value labels
        cbar = self.figure.colorbar(scatter, ax=ax, shrink=0.8, ticks=[0, 1, 2, 3, 4, 5, 6, 7, 8])
        cbar.set_label('ITC Color Group')
        cbar.set_ticklabels(['0-8', '1-9', '2-10', '3-11', '4-12', '5-13', '6-14', '7-15', '8-16'])
        
        # Plot current polygon
        if len(self.polygon_points) > 0:
            poly_x = [p[0] for p in self.polygon_points]
            poly_y = [p[1] for p in self.polygon_points]
            
            # Plot points
            ax.scatter(poly_x, poly_y, c='red', s=50, marker='x', linewidth=2)
            
            # Plot lines
            if len(self.polygon_points) > 1:
                for i in range(len(self.polygon_points) - 1):
                    ax.plot([poly_x[i], poly_x[i+1]], [poly_y[i], poly_y[i+1]], 
                           'r-', linewidth=2)
        
        self.canvas.draw()
        
    def on_canvas_click(self, event):
        """Handle mouse clicks on the canvas."""
        if event.button == 1 and event.xdata is not None and event.ydata is not None:  # Left click
            # Add point manually (not snapped to existing points)
            point = [event.xdata, event.ydata]
            self.polygon_points.append(point)
            self.plot_points()
            
            if len(self.polygon_points) >= 3:
                self.finish_button.setEnabled(True)
                
        elif event.button == 3:  # Right click
            if len(self.polygon_points) >= 3:
                self.finish_polygon()
    
    def finish_polygon(self):
        """Finish the polygon and emit signal."""
        if len(self.polygon_points) >= 3:
            self.finished = True
            polygon_array = np.array(self.polygon_points)
            self.polygon_completed.emit(polygon_array)
            self.accept()
    
    def clear_polygon(self):
        """Clear the current polygon."""
        self.polygon_points = []
        self.finish_button.setEnabled(False)
        self.plot_points()


class ITCAssignmentDialog(QDialog):
    """Dialog for assigning ITC values to selected points."""

    def __init__(self, unique_itc_values, parent=None):
        super().__init__(parent)
        self.unique_itc_values = sorted(unique_itc_values)
        self.selected_itc = None
        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("Assign ITC Value")
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Select ITC value to assign to selected points:")
        title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title)

        # Create scroll area for buttons
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Add buttons for each unique ITC value
        for itc_value in self.unique_itc_values:
            button = ModernButton(f"ITC {itc_value}")
            button.clicked.connect(lambda checked, val=itc_value: self.select_itc(val))
            scroll_layout.addWidget(button)

        # Add noise button
        noise_button = ModernButton("Noise (9999)")
        noise_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        noise_button.clicked.connect(lambda: self.select_itc(9999))
        scroll_layout.addWidget(noise_button)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(400)
        layout.addWidget(scroll_area)

        # Manual input section
        manual_layout = QHBoxLayout()
        manual_layout.addWidget(QLabel("Or enter custom ITC value:"))
        
        self.custom_itc_input = QSpinBox()
        self.custom_itc_input.setRange(1, 999999)
        self.custom_itc_input.setValue(1)
        self.custom_itc_input.setFixedWidth(100)
        manual_layout.addWidget(self.custom_itc_input)
        
        assign_custom_button = ModernButton("Assign Custom")
        assign_custom_button.clicked.connect(lambda: self.select_itc(self.custom_itc_input.value()))
        manual_layout.addWidget(assign_custom_button)
        
        manual_layout.addStretch()
        layout.addLayout(manual_layout)

        # Cancel button
        cancel_button = ModernButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

    def select_itc(self, itc_value):
        """Select the ITC value and close dialog."""
        self.selected_itc = itc_value
        self.accept()


class BatchSkipOptionsDialog(QDialog):
    """Dialog to ask whether to skip certain trees during batch processing."""

    def __init__(self, parent=None, default_threshold=50):
        super().__init__(parent)
        self.default_threshold = int(default_threshold)
        self.selected = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Batch: Skip Options")
        self.setModal(True)
        layout = QVBoxLayout(self)

        title = QLabel("Batch skip options (applies to all trees):")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self.skip_no_trunk_cb = QCheckBox("Skip trees with no trunk detected")
        self.skip_no_trunk_cb.setChecked(True)
        layout.addWidget(self.skip_no_trunk_cb)

        h = QHBoxLayout()
        self.skip_small_trunk_cb = QCheckBox("Skip trees when largest trunk has <")
        self.skip_small_trunk_cb.setChecked(True)
        h.addWidget(self.skip_small_trunk_cb)
        self.small_trunk_threshold = QSpinBox()
        self.small_trunk_threshold.setRange(1, 1000000)
        self.small_trunk_threshold.setValue(self.default_threshold)
        self.small_trunk_threshold.setSuffix(" pts")
        h.addWidget(self.small_trunk_threshold)
        layout.addLayout(h)

        info = QLabel("These settings are applied once at the start for all trees in the batch.")
        layout.addWidget(info)

        btns = QHBoxLayout()
        ok = ModernButton("OK")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        cancel = ModernButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_options(self):
        return {
            'skip_no_trunk': bool(self.skip_no_trunk_cb.isChecked()),
            'skip_small_trunk': bool(self.skip_small_trunk_cb.isChecked()),
            'small_trunk_threshold': int(self.small_trunk_threshold.value())
        }


class BatchTrunkParamsDialog(QDialog):
    """Dialog to configure trunk-detection parameters for batch runs."""

    def __init__(self, parent=None, defaults=None):
        super().__init__(parent)
        self.defaults = defaults or {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Batch: Trunk Detection Parameters")
        self.setModal(True)
        layout = QVBoxLayout(self)

        # Slice height (cm)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Slice height (cm):"))
        self.slice_height_spin = QSpinBox()
        self.slice_height_spin.setRange(1, 200)
        self.slice_height_spin.setValue(int(self.defaults.get('slice_height_cm', 25)))
        h1.addWidget(self.slice_height_spin)
        layout.addLayout(h1)

        # Base zone height (m)
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Base zone height (m, 0=full):"))
        self.base_zone = QDoubleSpinBox()
        self.base_zone.setRange(0.0, 100.0)
        self.base_zone.setDecimals(2)
        self.base_zone.setValue(float(self.defaults.get('base_zone_height_m', 0.0)))
        h2.addWidget(self.base_zone)
        layout.addLayout(h2)

        # DBSCAN eps and min_samples
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("DBSCAN eps (m):"))
        self.eps = QDoubleSpinBox()
        self.eps.setRange(0.0, 10.0)
        self.eps.setDecimals(3)
        self.eps.setValue(float(self.defaults.get('eps_m', 0.18)))
        h3.addWidget(self.eps)
        h3.addWidget(QLabel("min_samples:"))
        self.min_samples = QSpinBox()
        self.min_samples.setRange(1, 1000)
        self.min_samples.setValue(int(self.defaults.get('min_samples', 8)))
        h3.addWidget(self.min_samples)
        layout.addLayout(h3)

        # Merge distance, min points, min span
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("merge_dist (m):"))
        self.merge_dist = QDoubleSpinBox()
        self.merge_dist.setRange(0.0, 10.0)
        self.merge_dist.setDecimals(3)
        self.merge_dist.setValue(float(self.defaults.get('merge_dist_m', 0.25)))
        h4.addWidget(self.merge_dist)
        h4.addWidget(QLabel("min_trunk_points:"))
        self.min_trunk_points = QSpinBox()
        self.min_trunk_points.setRange(1, 100000)
        self.min_trunk_points.setValue(int(self.defaults.get('min_trunk_points', 120)))
        h4.addWidget(self.min_trunk_points)
        layout.addLayout(h4)

        h5 = QHBoxLayout()
        h5.addWidget(QLabel("min_vertical_span_m:"))
        self.min_span = QDoubleSpinBox()
        self.min_span.setRange(0.0, 100.0)
        self.min_span.setDecimals(2)
        self.min_span.setValue(float(self.defaults.get('min_vertical_span_m', 1.0)))
        h5.addWidget(self.min_span)
        h5.addWidget(QLabel("full_height_assign_dist_m:"))
        self.full_assign = QDoubleSpinBox()
        self.full_assign.setRange(0.0, 10.0)
        self.full_assign.setDecimals(3)
        self.full_assign.setValue(float(self.defaults.get('full_height_assign_dist_m', 0.45)))
        h5.addWidget(self.full_assign)
        layout.addLayout(h5)

        # DBH reference height (m) — asked here too so batch always uses an
        # explicit value even if the user forgot to set it in the main window.
        h6 = QHBoxLayout()
        h6.addWidget(QLabel("DBH reference height (m):"))
        self.dbh_height = QDoubleSpinBox()
        self.dbh_height.setRange(0.1, 10.0)
        self.dbh_height.setSingleStep(0.1)
        self.dbh_height.setDecimals(2)
        self.dbh_height.setValue(float(self.defaults.get('dbh_reference_height', 1.3)))
        self.dbh_height.setToolTip("DBH reference height above ground (standard: 1.3m). Used for DBH calculation and export location/DBH details.")
        h6.addWidget(self.dbh_height)
        layout.addLayout(h6)

        btns = QHBoxLayout()
        ok = ModernButton("OK")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        cancel = ModernButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_params(self):
        return {
            'slice_height_cm': int(self.slice_height_spin.value()),
            'base_zone_height_m': float(self.base_zone.value()),
            'eps_m': float(self.eps.value()),
            'min_samples': int(self.min_samples.value()),
            'merge_dist_m': float(self.merge_dist.value()),
            'min_trunk_points': int(self.min_trunk_points.value()),
            'min_vertical_span_m': float(self.min_span.value()),
            'full_height_assign_dist_m': float(self.full_assign.value()),
            'dbh_reference_height': float(self.dbh_height.value())
        }


class BatchBranchParamsDialog(QDialog):
    """Dialog to configure branch-detection parameters for batch runs."""

    def __init__(self, parent=None, defaults=None):
        super().__init__(parent)
        self.defaults = defaults or {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Batch: Branch Detection Parameters")
        self.setModal(True)
        layout = QVBoxLayout(self)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Slice height (cm):"))
        self.slice_height = QSpinBox()
        self.slice_height.setRange(1, 200)
        self.slice_height.setValue(int(self.defaults.get('slice_height_cm', 25)))
        h1.addWidget(self.slice_height)
        layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Branch DBSCAN eps (m):"))
        self.branch_eps = QDoubleSpinBox()
        self.branch_eps.setRange(0.0, 10.0)
        self.branch_eps.setDecimals(3)
        self.branch_eps.setValue(float(self.defaults.get('branch_eps', 0.12)))
        h2.addWidget(self.branch_eps)
        h2.addWidget(QLabel("min_samples:"))
        self.branch_min_samples = QSpinBox()
        self.branch_min_samples.setRange(1, 1000)
        self.branch_min_samples.setValue(int(self.defaults.get('branch_min_samples', 6)))
        h2.addWidget(self.branch_min_samples)
        layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("merge_dist (m):"))
        self.branch_merge = QDoubleSpinBox()
        self.branch_merge.setRange(0.0, 10.0)
        self.branch_merge.setDecimals(3)
        self.branch_merge.setValue(float(self.defaults.get('branch_merge_dist', 0.25)))
        h3.addWidget(self.branch_merge)
        layout.addLayout(h3)

        btns = QHBoxLayout()
        ok = ModernButton("OK")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        cancel = ModernButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_params(self):
        return {
            'slice_height_cm': int(self.slice_height.value()),
            'branch_eps': float(self.branch_eps.value()),
            'branch_min_samples': int(self.branch_min_samples.value()),
            'branch_merge_dist': float(self.branch_merge.value())
        }



class GdbImportDialog(QDialog):
    """Dialog for importing points from an ESRI File Geodatabase (.gdb) to view in 3D space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gdb_path = None
        self.selected_layer = None
        self.z_field = None
        self.z_constant = 0.0
        self.color = "#FF3333"
        self.point_size = 8
        self.render_spheres = True
        self._layer_schema = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Import Points from Geodatabase")
        self.setModal(True)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Import & View Point Features from Geodatabase (.gdb)")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #4CAF50; margin-bottom: 4px;")
        title.setWordWrap(True)
        layout.addWidget(title)

        gdb_group = QGroupBox("Geodatabase")
        gdb_layout = QHBoxLayout(gdb_group)
        self.gdb_path_label = QLabel("No geodatabase selected")
        self.gdb_path_label.setStyleSheet("color: #bbbbbb;")
        self.gdb_path_label.setWordWrap(True)
        gdb_layout.addWidget(self.gdb_path_label, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_gdb)
        gdb_layout.addWidget(browse_btn)
        layout.addWidget(gdb_group)

        layer_group = QGroupBox("Feature Layer")
        layer_layout = QVBoxLayout(layer_group)
        self.layer_combo = QComboBox()
        self.layer_combo.setEnabled(False)
        self.layer_combo.addItem("<Select a geodatabase first>")
        self.layer_combo.currentTextChanged.connect(self._on_layer_changed)
        layer_layout.addWidget(self.layer_combo)
        self.layer_info_label = QLabel("")
        self.layer_info_label.setStyleSheet("color: #bbbbbb; font-size: 10px;")
        layer_layout.addWidget(self.layer_info_label)
        layout.addWidget(layer_group)

        z_group = QGroupBox("Z Elevation")
        z_layout = QGridLayout(z_group)
        z_layout.setSpacing(8)
        z_layout.addWidget(QLabel("Z elevation field:"), 0, 0)
        self.z_field_combo = QComboBox()
        self.z_field_combo.setEnabled(False)
        self.z_field_combo.setToolTip(
            "Attribute column containing Z elevation (metres).\n"
            "<Use geometry Z / constant> reads Z from feature geometry if present."
        )
        self.z_field_combo.currentTextChanged.connect(self._on_z_field_changed)
        z_layout.addWidget(self.z_field_combo, 0, 1)
        self.z_const_label = QLabel("Constant Z value (m):")
        self.z_const_label.setStyleSheet("color: #bbbbbb; font-size: 10px;")
        z_layout.addWidget(self.z_const_label, 1, 0)
        self.z_const_spin = QDoubleSpinBox()
        self.z_const_spin.setRange(-9999.0, 99999.0)
        self.z_const_spin.setDecimals(3)
        self.z_const_spin.setValue(0.0)
        self.z_const_spin.setFixedWidth(110)
        self.z_const_spin.setToolTip("Fallback height if features lack 3D Z coordinates.")
        z_layout.addWidget(self.z_const_spin, 1, 1)
        layout.addWidget(z_group)

        style_group = QGroupBox("3D Display Settings")
        style_layout = QGridLayout(style_group)
        style_layout.setSpacing(8)
        style_layout.addWidget(QLabel("Marker Color:"), 0, 0)
        self.color_combo = QComboBox()
        self.colors_map = {
            "Red": "#FF3333", "Yellow": "#FFDD33", "Cyan": "#33DDFF",
            "Magenta": "#FF33FF", "Lime Green": "#33FF57",
            "Bright Orange": "#FF8C00", "White": "#FFFFFF", "Blue": "#3366FF"
        }
        for name in self.colors_map:
            self.color_combo.addItem(name)
        style_layout.addWidget(self.color_combo, 0, 1)
        style_layout.addWidget(QLabel("Point Size / Radius:"), 1, 0)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 50)
        self.size_spin.setValue(8)
        style_layout.addWidget(self.size_spin, 1, 1)
        self.spheres_cb = QCheckBox("Render as 3D Spheres")
        self.spheres_cb.setChecked(True)
        style_layout.addWidget(self.spheres_cb, 2, 0, 1, 2)
        layout.addWidget(style_group)

        note = QLabel("\u2139\ufe0f  Requires: pyogrio and geopandas  (pip install pyogrio geopandas)")
        note.setStyleSheet("color: #888888; font-size: 10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Display in 3D")
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_gdb(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select ESRI File Geodatabase (.gdb folder)", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not path:
            return
        if not path.lower().endswith(".gdb"):
            QMessageBox.warning(self, "Not a Geodatabase",
                                f"Please select a folder with the .gdb extension.\n\nSelected: {path}")
            return
        self.gdb_path = path
        self.gdb_path_label.setText(path)
        self.gdb_path_label.setStyleSheet("color: #e0e0e0;")
        self._populate_layers()

    def _populate_layers(self):
        has_pyogrio = False
        has_fiona = False
        try:
            import pyogrio; has_pyogrio = True
        except ImportError:
            pass
        try:
            import fiona; has_fiona = True
        except ImportError:
            pass
        if not has_pyogrio and not has_fiona:
            QMessageBox.critical(self, "Missing Dependency",
                "pyogrio or fiona is required.\n\npip install pyogrio geopandas")
            return
        point_layers = []
        if has_pyogrio:
            try:
                import pyogrio
                for lyr, gtype in pyogrio.list_layers(self.gdb_path):
                    if gtype and "point" in str(gtype).lower():
                        point_layers.append(lyr)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Could not list layers:\n{exc}"); return
        else:
            try:
                import fiona
                for lyr in fiona.listlayers(self.gdb_path):
                    try:
                        with fiona.open(self.gdb_path, layer=lyr) as src:
                            if "point" in src.schema.get("geometry","").lower():
                                point_layers.append(lyr)
                    except Exception:
                        pass
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Could not list layers:\n{exc}"); return
        self.layer_combo.clear()
        if not point_layers:
            self.layer_combo.addItem("<No Point layers found>")
            self.layer_combo.setEnabled(False)
            self.layer_info_label.setText("No Point layers found in this GDB.")
            return
        self.layer_combo.addItem("<Select layer>")
        for lyr in point_layers:
            self.layer_combo.addItem(lyr)
        self.layer_combo.setEnabled(True)

    def _on_layer_changed(self, layer_name):
        if not self.gdb_path or not layer_name or layer_name.startswith("<"):
            self.ok_btn.setEnabled(False); return
        try:
            import pyogrio
            info = pyogrio.read_info(self.gdb_path, layer=layer_name)
            gtype = info.get("geometry_type","?")
            n = info.get("features", 0)
            fields = info.get("fields", [])
            dtypes = info.get("dtypes", [])
            self._layer_schema = dict(zip(fields, [str(d) for d in dtypes]))
            self.layer_info_label.setText(f"Geometry: {gtype}  |  Features: {n:,}  |  Fields: {len(self._layer_schema)}")
        except ImportError:
            try:
                import fiona
                with fiona.open(self.gdb_path, layer=layer_name) as src:
                    schema = src.schema
                    self._layer_schema = schema.get("properties",{})
                    self.layer_info_label.setText(
                        f"Geometry: {schema.get('geometry','?')}  |  Features: {len(src):,}  |  Fields: {len(self._layer_schema)}")
            except Exception as exc:
                self.layer_info_label.setText(f"Error: {exc}")
                self._layer_schema = {}; self.ok_btn.setEnabled(False); return
        except Exception as exc:
            self.layer_info_label.setText(f"Error: {exc}")
            self._layer_schema = {}; self.ok_btn.setEnabled(False); return
        self.z_field_combo.clear()
        self.z_field_combo.addItem("<Use geometry Z / constant>")
        for f, t in self._layer_schema.items():
            if any(k in str(t).lower() for k in ("int","float","num")):
                self.z_field_combo.addItem(f)
        self.z_field_combo.setEnabled(True)
        self.ok_btn.setEnabled(True)

    def _on_z_field_changed(self, field_name):
        use_const = field_name.startswith("<")
        self.z_const_label.setStyleSheet(
            "color: #e0e0e0; font-size: 10px;" if use_const else "color: #555555; font-size: 10px;"
        )
        self.z_const_spin.setEnabled(use_const)

    def _on_ok(self):
        if not self.gdb_path:
            QMessageBox.warning(self, "No GDB", "Please select a geodatabase first."); return
        layer_name = self.layer_combo.currentText()
        if not layer_name or layer_name.startswith("<"):
            QMessageBox.warning(self, "No Layer", "Please select a feature layer."); return
        self.selected_layer = layer_name
        z_txt = self.z_field_combo.currentText()
        self.z_field = None if z_txt.startswith("<") else z_txt
        self.z_constant = self.z_const_spin.value()
        self.accept()

    def get_import_params(self):
        color_name = self.color_combo.currentText()
        return {
            "gdb_path": self.gdb_path,
            "layer": self.selected_layer,
            "z_field": self.z_field,
            "z_constant": self.z_constant,
            "color": self.colors_map.get(color_name, "#FF3333"),
            "color_name": color_name,
            "point_size": self.size_spin.value(),
            "render_spheres": self.spheres_cb.isChecked(),
        }


class TreeVisualizerGUI(QMainWindow):
    """Main window for tree visualization GUI."""

    def __init__(self):
        import time
        init_start = time.perf_counter()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - TreeVisualizerGUI.__init__ starting...")
        
        super().__init__()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - super().__init__ done ({time.perf_counter() - init_start:.3f}s)")
        
        self.las_data = None
        self.current_las_path = None
        self.las_layers = []  # List of layer dicts: {'path', 'name', 'num_points', 'num_trees', 'has_stemcls', 'checked'}
        self._updating_las_layer_list = False
        self.unique_itc_values = []
        self.current_tree_points = None
        self.current_tree_id = None
        self.current_mask = None
        self.current_color_values = None
        self.current_color_field = None
        self.all_masks = None
        self.current_itc_values = None
        self.current_itc_values = None
        self.plotter = None
        # GDB overlay layers: name -> {coords, color, point_size, visible, render_spheres}
        self.gdb_layers = {}
        # When True, the point picker resolves GDB overlay points instead of tree points
        self.gdb_pick_mode = False
        # Polygon selection variables
        self.polygon_selection_mode = False
        self.polygon_points = []
        self.selected_polygon = None
        self.selected_point_indices = None
        self.radius_selection_active = False
        self.radius_selection_center = None
        
        # Volume calculation accumulation variables
        self.accumulated_volume_sections = []  # List of (points, circles_data) tuples
        self.trees_with_volume_data = set()  # Track tree IDs that have volume calculation data
        self.volume_folder_path = None  # Path to folder containing volume data files
        self.itc_changes = []  # Track all ITC assignments in session
        self.last_analyzed_points = None  # Store points from last AI analysis for noise conversion
        self.tree_centroids_cache = {}  # Cache for tree centroids to speed up neighbor calculations
        self.centroids_kdtree = None  # KDTree for fast spatial queries
        self.centroids_kdtree_tree_ids = None  # Tree IDs in the same row order as centroids_kdtree
        
        # Trunk detection variables (Phase 1)
        self.trunk_assignment = None  # Array: -1 = noise, >=0 = trunk_id
        self.trunk_models = {}  # Dict: trunk_id -> {'trajectory': [centroids], 'points': count, 'z_span': (min, max)}
        self.trunk_detection_params = {
            'slice_height_cm': 25,
            'base_zone_height_m': 0.0,
            'eps_m': 0.18,
            'min_samples': 8,
            'merge_dist_m': 0.25,
            'min_trunk_points': 120,
            'min_vertical_span_m': 1.0,
            'full_height_assign_dist_m': 0.45
        }
        # Detection state/versioning to prevent redundant recalculation
        self._trunk_detection_version = 0
        self._branch_detection_version = 0
        # Signature of last volume calculation: (tree_id, trunk_version, branch_version)
        self._last_volume_calc_signature = None
        # DBH reference height (customizable by user, default = 1.3m)
        self.dbh_reference_height = 1.3
        # Last used detection parameters for change detection
        self._last_trunk_detection_params = None
        self._last_branch_detection_params = None
        # Monotonic counter to keep volume overlay actor names unique per successful calculation run
        self._volume_calc_run_id = 0
        
        # Branch detection variables
        self.branch_assignment = None  # Array: -1 = noise, >=0 = branch_id
        self.branch_meta = {}  # Dict: global_branch_id -> {trunk_id, local_id, point_count, z_span}
        print(f"[INIT] {time.strftime('%H:%M:%S')} - Instance variables set ({time.perf_counter() - init_start:.3f}s)")
        

        
        ui_start = time.perf_counter()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - Starting init_ui...")
        self.init_ui()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - init_ui done ({time.perf_counter() - ui_start:.3f}s)")
        
        style_start = time.perf_counter()
        self.apply_stylesheet()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - apply_stylesheet done ({time.perf_counter() - style_start:.3f}s)")
        print(f"[INIT] {time.strftime('%H:%M:%S')} - __init__ complete ({time.perf_counter() - init_start:.3f}s total)")

    def set_camera_view(self, view_type):
        """Set the camera to a standard orthographic view."""
        if not self.plotter:
            return
            
        # Get the bounds of the current scene to determine appropriate camera distance and focal point
        bounds = self.plotter.bounds
        if bounds is not None:
            # Calculate the center of the bounding box
            center_x = (bounds[0] + bounds[1]) / 2
            center_y = (bounds[2] + bounds[3]) / 2
            center_z = (bounds[4] + bounds[5]) / 2
            focal_point = (center_x, center_y, center_z)
            
            # Calculate the diagonal of the bounding box to determine camera distance
            x_range = bounds[1] - bounds[0]
            y_range = bounds[3] - bounds[2] 
            z_range = bounds[5] - bounds[4]
            diagonal = np.sqrt(x_range**2 + y_range**2 + z_range**2)
            camera_distance = diagonal * 2.0  # Place camera at 2x the diagonal distance
        else:
            focal_point = (0, 0, 0)
            camera_distance = 100.0  # Default fallback distance
        
        # Reset camera to default position first
        self.plotter.reset_camera()
        
        if view_type == 'view_front':
            # Front view: looking along positive Y axis
            self.plotter.camera.position = (focal_point[0], focal_point[1] - camera_distance, focal_point[2])
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, 0, 1)
        elif view_type == 'view_back':
            # Back view: looking along negative Y axis
            self.plotter.camera.position = (focal_point[0], focal_point[1] + camera_distance, focal_point[2])
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, 0, 1)
        elif view_type == 'view_top':
            # Top view: looking down negative Z axis
            self.plotter.camera.position = (focal_point[0], focal_point[1], focal_point[2] + camera_distance)
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, 1, 0)
        elif view_type == 'view_bottom':
            # Bottom view: looking up positive Z axis
            self.plotter.camera.position = (focal_point[0], focal_point[1], focal_point[2] - camera_distance)
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, -1, 0)
        elif view_type == 'view_left':
            # Left view: looking along positive X axis
            self.plotter.camera.position = (focal_point[0] - camera_distance, focal_point[1], focal_point[2])
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, 0, 1)
        elif view_type == 'view_right':
            # Right view: looking along negative X axis
            self.plotter.camera.position = (focal_point[0] + camera_distance, focal_point[1], focal_point[2])
            self.plotter.camera.focal_point = focal_point
            self.plotter.camera.up = (0, 0, 1)
        
        # Reset camera to ensure proper zoom for the new view
        self.plotter.reset_camera()
        self.plotter.update()

    def log_to_console(self, message):
        """Add a message to the console output."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        self.console.append(formatted_msg)
        # Also print to terminal for visibility
        print(formatted_msg)
        # Auto-scroll to bottom
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def log_many_to_console(self, messages):
        """Append many messages to the console in ONE widget update.

        Much faster than calling log_to_console() per message for bulk output
        (avoids one Qt repaint + auto-scroll per line).
        """
        if not messages:
            return
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        block = "\n".join(f"[{timestamp}] {m}" for m in messages)
        self.console.append(block)
        print(block)
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_progress(self, value, text=None):
        """Update the determinate progress bar and keep the UI responsive."""
        try:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))
            if text:
                self.progress_bar.setFormat(f"{text}  %p%")
            self.progress_bar.setVisible(True)
            QApplication.processEvents()
        except Exception:
            pass

    def _start_volume_load_profile(self):
        """Start a timed Load Data profile log on disk."""
        import time
        from datetime import datetime

        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analysis_log')
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(log_dir, f'volume_load_profile_{stamp}.log')
        self._volume_load_profile_path = path
        self._volume_load_profile_t0 = time.perf_counter()
        self._volume_load_profile_last = self._volume_load_profile_t0
        header = (
            f"Volume Load Data profile started {datetime.now().isoformat(timespec='seconds')}\n"
            f"Log file: {path}\n"
        )
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(header)
                handle.flush()
        except Exception as exc:
            self._volume_load_profile_path = None
            self.log_to_console(f"⚠️ Could not create load-data profile log: {exc}")
            return None
        self.log_to_console(f"📝 Load Data profile log: {path}")
        return path

    def _profile_volume_load(self, step_name, extra=''):
        """Record elapsed time for one Load Data step to the profile log and console."""
        import time
        from datetime import datetime

        path = getattr(self, '_volume_load_profile_path', None)
        if not path:
            return
        now = time.perf_counter()
        dt = now - getattr(self, '_volume_load_profile_last', now)
        total = now - getattr(self, '_volume_load_profile_t0', now)
        self._volume_load_profile_last = now
        extra_text = f"  | {extra}" if extra else ""
        line = (
            f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  "
            f"+{dt:8.3f}s  total={total:8.3f}s  {step_name}{extra_text}\n"
        )
        try:
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(line)
                handle.flush()
        except Exception:
            pass
        self.log_to_console(f"⏱ {step_name}: {dt:.3f}s (total {total:.3f}s){extra_text}")

    def _finish_volume_load_profile(self, status='done'):
        """Close the Load Data profile log with a final status line."""
        path = getattr(self, '_volume_load_profile_path', None)
        if not path:
            return
        self._profile_volume_load(f'LOAD_DATA_{status.upper()}')
        self._volume_load_profile_path = None

    def apply_stylesheet(self):
        """Apply modern dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                color: #e0e0e0;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QGroupBox {
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                margin-top: 1ex;
                background-color: #363636;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 7px;
                padding: 0px 5px 0px 5px;
                color: #4CAF50;
                font-weight: bold;
            }
            QComboBox {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                border: 1px solid #555555;
                selection-background-color: #4CAF50;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #555555;
                background-color: #333333;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 2px solid #4CAF50;
            }
            QLabel {
                color: #e0e0e0;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 5px;
                text-align: center;
                background-color: #333333;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #404040;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #4CAF50;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #e0e0e0;
                border: 2px solid #4CAF50;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                border-color: #66BB6A;
            }
        """)

    def init_ui(self):
        """Initialize the user interface."""
        import time
        ui_start = time.perf_counter()
        print(f"[UI] {time.strftime('%H:%M:%S')} - init_ui starting...")
        
        self.setWindowTitle("Tree Visualizer - TreeAIBox")
        self.setGeometry(100, 100, 1400, 900)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Create top section with sidebar and plotter
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # Create sidebar
        sidebar_start = time.perf_counter()
        print(f"[UI] {time.strftime('%H:%M:%S')} - Creating sidebar...")
        sidebar = self.create_sidebar()
        print(f"[UI] {time.strftime('%H:%M:%S')} - Sidebar created ({time.perf_counter() - sidebar_start:.3f}s)")
        top_layout.addWidget(sidebar, 1)

        # Create main content area - 3D visualization
        plotter_frame = QFrame()
        plotter_frame.setObjectName("plotterFrame")
        plotter_frame.setStyleSheet("""
            #plotterFrame {
                background-color: #2e2e2e; /* Lighter background color */
                border: 1px solid #444444;
                border-radius: 8px;
            }
        """)
        
        plotter_layout = QVBoxLayout(plotter_frame)
        plotter_layout.setContentsMargins(5, 5, 5, 5)
        
        # Add view control buttons above the plotter
        view_buttons_layout = QHBoxLayout()
        view_buttons_layout.setSpacing(5)
        
        # Create view buttons
        self.view_buttons = {}
        view_configs = [
            ('Front', 'view_front'),
            ('Back', 'view_back'), 
            ('Top', 'view_top'),
            ('Bottom', 'view_bottom'),
            ('Left', 'view_left'),
            ('Right', 'view_right')
        ]
        
        for label, view_type in view_configs:
            button = ModernButton(label)
            button.setFixedSize(60, 30)
            button.clicked.connect(lambda checked, vt=view_type: self.set_camera_view(vt))
            view_buttons_layout.addWidget(button)
            self.view_buttons[view_type] = button
        
        # Add stretch to push buttons to the left
        view_buttons_layout.addStretch()
        
        plotter_layout.addLayout(view_buttons_layout)
        
        plotter_start = time.perf_counter()
        print(f"[UI] {time.strftime('%H:%M:%S')} - Creating QtInteractor (3D plotter)...")
        self.plotter = QtInteractor()
        print(f"[UI] {time.strftime('%H:%M:%S')} - QtInteractor created ({time.perf_counter() - plotter_start:.3f}s)")
        self.plotter.set_background('#2e2e2e')  # Lighter background color
        plotter_layout.addWidget(self.plotter.interactor)

        # Enable point picking
        self.plotter.enable_point_picking(callback=self.on_point_picked, show_message=False)
        
        # Add instruction text
        self.plotter.add_text("Click on points to see ITC values", position='lower_left', 
                            font_size=10, color='#FFFFFF', name='itc_instruction_text')
        print(f"[UI] {time.strftime('%H:%M:%S')} - Plotter setup complete ({time.perf_counter() - plotter_start:.3f}s)")

        top_layout.addWidget(plotter_frame, 4)
        main_layout.addLayout(top_layout, 4)

        # Create console at the bottom
        console_frame = QFrame()
        console_frame.setObjectName("consoleFrame")
        console_frame.setStyleSheet("""
            #consoleFrame {
                background-color: #1e1e1e;
                border: 1px solid #444444;
                border-radius: 8px;
            }
        """)
        console_frame.setMaximumHeight(150)
        console_frame.setMinimumHeight(100)
        
        console_layout = QVBoxLayout(console_frame)
        console_layout.setContentsMargins(5, 5, 5, 5)
        
        console_label = QLabel("Console Output:")
        console_label.setStyleSheet("color: #4CAF50; font-weight: bold; margin-bottom: 5px;")
        console_layout.addWidget(console_label)
        
        self.console = QTextEdit()
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(120)
        console_layout.addWidget(self.console)

        main_layout.addWidget(console_frame, 1)
        print(f"[UI] {time.strftime('%H:%M:%S')} - Console created")

        # Initialize empty plot
        self.clear_plot()
        print(f"[UI] {time.strftime('%H:%M:%S')} - init_ui complete ({time.perf_counter() - ui_start:.3f}s total)")

    def create_sidebar(self):
        """Create the sidebar with file loading and visualization controls."""
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet("#sidebar { background-color: #363636; border-radius: 8px; }")
        sidebar.setMinimumWidth(420)
        sidebar.setMaximumWidth(560)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(sidebar)
        scroll_area.setMinimumWidth(420)
        scroll_area.setMaximumWidth(560)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #363636;
                width: 15px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #4CAF50;
                border-radius: 4px;
                min-height: 20px;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # File loading section
        file_group = QGroupBox("File Management")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(10)

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: #bbbbbb;")
        file_layout.addWidget(self.file_label)

        self.load_button = ModernButton("Add LAS File(s)")
        self.load_button.setToolTip("Add single or multiple LAS/LAZ files to layer manager")
        self.load_button.clicked.connect(self.load_las_file)
        file_layout.addWidget(self.load_button)

        # ── LAS Layer Manager Widget ──
        self.las_layer_group = QGroupBox("LAS Layer Manager")
        las_layer_vbox = QVBoxLayout(self.las_layer_group)
        las_layer_vbox.setSpacing(6)
        las_layer_vbox.setContentsMargins(8, 10, 8, 8)

        las_btn_grid = QGridLayout()
        las_btn_grid.setSpacing(4)

        self.remove_las_btn = ModernButton("Remove")
        self.remove_las_btn.setToolTip("Remove selected LAS file from layer manager")
        self.remove_las_btn.setFixedHeight(26)
        self.remove_las_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 4px; }")
        self.remove_las_btn.clicked.connect(self.remove_selected_las_layer)
        las_btn_grid.addWidget(self.remove_las_btn, 0, 0)

        self.toggle_las_batch_btn = ModernButton("Check All")
        self.toggle_las_batch_btn.setToolTip("Toggle checking all LAS files for batch processing")
        self.toggle_las_batch_btn.setFixedHeight(26)
        self.toggle_las_batch_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 4px; }")
        self.toggle_las_batch_btn.clicked.connect(self.toggle_las_batch_checks)
        las_btn_grid.addWidget(self.toggle_las_batch_btn, 0, 1)

        las_layer_vbox.addLayout(las_btn_grid)

        self.las_layer_list = QListWidget()
        self.las_layer_list.setMaximumHeight(140)
        self.las_layer_list.setToolTip("Loaded LAS layers. Check items to include in multi-LAS batch processing.\nClick an item to switch active viewer.")
        self.las_layer_list.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #1976D2;
                color: white;
            }
        """)
        self.las_layer_list.itemClicked.connect(self._on_las_layer_clicked)
        self.las_layer_list.itemChanged.connect(self._on_las_layer_check_changed)
        las_layer_vbox.addWidget(self.las_layer_list)

        file_layout.addWidget(self.las_layer_group)

        self.import_gdb_button = ModernButton("Import Points from GDB")
        self.import_gdb_button.clicked.connect(self.import_points_from_gdb)
        self.import_gdb_button.setToolTip(
            "Import point features from a .gdb geodatabase and view them in 3D.\n"
            "Requires: pyogrio + geopandas  (pip install pyogrio geopandas)"
        )
        self.import_gdb_button.setStyleSheet("""
            QPushButton {
                background-color: #1976D2; border: none; color: white;
                padding: 8px 16px; font-size: 11px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
        """)
        file_layout.addWidget(self.import_gdb_button)

        layout.addWidget(file_group)

        # ── GDB Layer Manager ─────────────────────────────────────────
        self.gdb_layer_group = QGroupBox("GDB Layer Manager")
        self.gdb_layer_group.setVisible(False)
        gdb_layer_vbox = QVBoxLayout(self.gdb_layer_group)
        gdb_layer_vbox.setSpacing(6)
        gdb_layer_vbox.setContentsMargins(8, 14, 8, 8)

        self.gdb_pick_mode_button = QPushButton("Pick GDB Points: OFF")
        self.gdb_pick_mode_button.setCheckable(True)
        self.gdb_pick_mode_button.setToolTip(
            "Toggle GDB pick mode. When ON, clicking a GDB sphere shows its attributes "
            "from the geodatabase. When OFF, normal tree point picking is used."
        )
        self.gdb_pick_mode_button.setStyleSheet("""
            QPushButton {
                background-color: #363636; border: 1px solid #555555; color: #e0e0e0;
                padding: 6px 10px; font-size: 11px; border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #1976D2; border: 1px solid #1976D2; color: white;
            }
        """)
        self.gdb_pick_mode_button.clicked.connect(self._on_gdb_pick_mode_toggled)
        gdb_layer_vbox.addWidget(self.gdb_pick_mode_button)

        self.gdb_layers_scroll = QScrollArea()
        self.gdb_layers_scroll.setWidgetResizable(True)
        self.gdb_layers_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gdb_layers_scroll.setMinimumHeight(240)
        self.gdb_layers_scroll.setMaximumHeight(350)
        self.gdb_layers_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.gdb_layers_container = QWidget()
        self.gdb_layers_container_layout = QVBoxLayout(self.gdb_layers_container)
        self.gdb_layers_container_layout.setSpacing(4)
        self.gdb_layers_container_layout.setContentsMargins(0, 0, 0, 0)
        self.gdb_layers_container_layout.addStretch()
        self.gdb_layers_scroll.setWidget(self.gdb_layers_container)
        gdb_layer_vbox.addWidget(self.gdb_layers_scroll)

        layout.addWidget(self.gdb_layer_group)

        # Volume folder management section
        volume_group = QGroupBox("Volume Folder Management")
        volume_layout = QVBoxLayout(volume_group)
        volume_layout.setSpacing(8)

        # Volume folder display (auto-assigned on save/load)
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Volume Folder:")
        folder_label.setFixedWidth(100)
        self.volume_folder_label = QLabel("Auto-assigned")
        self.volume_folder_label.setStyleSheet("color: #4CAF50; font-style: italic;")
        self.volume_folder_label.setWordWrap(True)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.volume_folder_label, 1)
        volume_layout.addLayout(folder_layout)

        # Volume folder options
        self.volume_folder_checkbox = QCheckBox("Check volume folder on visualize")
        self.volume_folder_checkbox.setChecked(False)
        self.volume_folder_checkbox.setStyleSheet("margin-top: 5px;")
        self.volume_folder_checkbox.setToolTip("When enabled, tree IDs with saved volume data in the selected folder will be colored red")
        volume_layout.addWidget(self.volume_folder_checkbox)

        # Connect checkbox signal
        self.volume_folder_checkbox.stateChanged.connect(self.on_volume_folder_checkbox_changed)

        layout.addWidget(volume_group)

        # Visualization controls section
        viz_group = QGroupBox("Visualization Controls")
        viz_layout = QVBoxLayout(viz_group)
        viz_layout.setSpacing(12)

        # Tree ID selection
        id_layout = QVBoxLayout()
        id_label = QLabel("Tree IDs (multi-select):")
        id_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        
        # Create list widget for multiple selection
        self.tree_list = QListWidget()
        self.tree_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.tree_list.setMaximumHeight(150)
        self.tree_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
                selection-background-color: #4CAF50;
            }
            QListWidget::item {
                padding: 3px;
                border-bottom: 1px solid #333333;
            }
            QListWidget::item:selected {
                background-color: #4CAF50;
                color: #ffffff;
            }
        """)
        
        # Add selection control buttons
        button_layout_small = QHBoxLayout()
        self.select_all_button = ModernButton("Select All")
        self.select_all_button.clicked.connect(self.select_all_trees)
        self.select_all_button.setFixedHeight(25)
        self.select_all_button.setStyleSheet("QPushButton { font-size: 11px; padding: 3px 8px; }")
        
        self.clear_selection_button = ModernButton("Clear All")
        self.clear_selection_button.clicked.connect(self.clear_tree_selection)
        self.clear_selection_button.setFixedHeight(25)
        self.clear_selection_button.setStyleSheet("QPushButton { font-size: 11px; padding: 3px 8px; }")
        
        button_layout_small.addWidget(self.select_all_button)
        button_layout_small.addWidget(self.clear_selection_button)
        
        id_layout.addWidget(id_label)
        id_layout.addWidget(self.tree_list)
        id_layout.addLayout(button_layout_small)
        viz_layout.addLayout(id_layout)

        # Scalar field for coloring
        color_layout = QVBoxLayout()
        color_label = QLabel("Color by:")
        color_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        self.color_combo = QComboBox()
        self.color_combo.addItem("Default (green)")
        self.color_combo.setMinimumHeight(30)
        self.color_combo.currentTextChanged.connect(self.update_tree_colors)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        viz_layout.addLayout(color_layout)

        # DBH reference height (editable)
        dbh_ref_layout = QHBoxLayout()
        dbh_ref_label = QLabel("DBH Ref Height (m):")
        dbh_ref_label.setFixedWidth(130)
        dbh_ref_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        self.dbh_height_input = QDoubleSpinBox()
        self.dbh_height_input.setRange(0.1, 10.0)
        self.dbh_height_input.setSingleStep(0.1)
        self.dbh_height_input.setDecimals(2)
        self.dbh_height_input.setValue(1.3)
        self.dbh_height_input.setMinimumHeight(28)
        self.dbh_height_input.setToolTip("DBH reference height above ground (standard: 1.3m).\nChanging this affects DBH calculations, batch analysis, and the orange DBH marker line.")
        self.dbh_height_input.valueChanged.connect(self._on_dbh_height_changed)
        dbh_ref_layout.addWidget(dbh_ref_label)
        dbh_ref_layout.addWidget(self.dbh_height_input)
        dbh_ref_layout.addStretch()
        viz_layout.addLayout(dbh_ref_layout)

        # Split detection parameters
        split_group = QGroupBox("Split Detection Parameters")
        split_layout = QVBoxLayout(split_group)
        split_layout.setSpacing(8)

        # Max height
        max_height_layout = QHBoxLayout()
        max_height_label = QLabel("Max Height (m):")
        max_height_label.setFixedWidth(100)
        max_height_label.setToolTip("Maximum height above base to analyze for splits (auto-set to trunk height)")
        self.max_height_input = QLineEdit("8.0")
        self.max_height_input.setMaximumWidth(60)
        self.max_height_input.setToolTip("Maximum height above base to analyze for splits (auto-set to trunk height)")
        max_height_layout.addWidget(max_height_label)
        max_height_layout.addWidget(self.max_height_input)
        max_height_layout.addStretch()
        split_layout.addLayout(max_height_layout)

        # Step distance
        step_layout = QHBoxLayout()
        step_label = QLabel("Step (m):")
        step_label.setFixedWidth(100)
        step_label.setToolTip("Height interval between analysis slices")
        self.step_input = QLineEdit("1.0")
        self.step_input.setMaximumWidth(60)
        self.step_input.setToolTip("Height interval between analysis slices")
        step_layout.addWidget(step_label)
        step_layout.addWidget(self.step_input)
        step_layout.addStretch()
        split_layout.addLayout(step_layout)

        # Slice thickness
        thickness_layout = QHBoxLayout()
        thickness_label = QLabel("Thickness (m):")
        thickness_label.setFixedWidth(100)
        thickness_label.setToolTip("Thickness of horizontal slice at each height")
        self.thickness_input = QLineEdit("0.1")
        self.thickness_input.setMaximumWidth(60)
        self.thickness_input.setToolTip("Thickness of horizontal slice at each height")
        thickness_layout.addWidget(thickness_label)
        thickness_layout.addWidget(self.thickness_input)
        thickness_layout.addStretch()
        split_layout.addLayout(thickness_layout)

        # Min points
        min_points_layout = QHBoxLayout()
        min_points_label = QLabel("Min Points:")
        min_points_label.setFixedWidth(100)
        min_points_label.setToolTip("Minimum points needed to form a cluster")
        self.min_points_input = QLineEdit("3")
        self.min_points_input.setMaximumWidth(60)
        self.min_points_input.setToolTip("Minimum points needed to form a cluster")
        min_points_layout.addWidget(min_points_label)
        min_points_layout.addWidget(self.min_points_input)
        min_points_layout.addStretch()
        split_layout.addLayout(min_points_layout)

        viz_layout.addWidget(split_group)



        self.filter_checkbox = QCheckBox("Filter tree points (treefilter=2)")
        self.filter_checkbox.setChecked(True)
        self.filter_checkbox.setStyleSheet("margin-top: 5px;")
        self.filter_checkbox.stateChanged.connect(self.on_filter_changed)
        viz_layout.addWidget(self.filter_checkbox)

        # Neighbor view controls
        neighbor_layout = QHBoxLayout()
        neighbor_label = QLabel("Neighbor Radius (m):")
        neighbor_label.setFixedWidth(120)
        self.neighbor_radius_input = QLineEdit("20.0")
        self.neighbor_radius_input.setMaximumWidth(60)
        self.neighbor_radius_input.setToolTip("Radius in meters to search for neighboring trees")
        self.view_neighbors_button = ModernButton("Neighbour")
        self.view_neighbors_button.clicked.connect(self.view_neighbors)
        self.view_neighbors_button.setEnabled(False)
        neighbor_layout.addWidget(neighbor_label)
        neighbor_layout.addWidget(self.neighbor_radius_input)
        neighbor_layout.addWidget(self.view_neighbors_button)
        neighbor_layout.addStretch()
        viz_layout.addLayout(neighbor_layout)

        # Control buttons - organized by category
        button_layout = QVBoxLayout()
        button_layout.setSpacing(6)
        
        # === VISUALIZATION SECTION ===
        self.visualize_button = ModernButton("Visualize Tree")
        self.visualize_button.clicked.connect(self.visualize_tree)
        self.visualize_button.setEnabled(False)
        self.visualize_button.setFixedHeight(32)
        button_layout.addWidget(self.visualize_button)

        self.trunk_button = ModernButton("Trunk Visualization")
        self.trunk_button.clicked.connect(self.visualize_trunk)
        self.trunk_button.setEnabled(False)
        self.trunk_button.setFixedHeight(32)
        button_layout.addWidget(self.trunk_button)

        # === SELECTION SECTION ===
        selection_label = QLabel("Point Selection")
        selection_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(selection_label)
        
        selection_grid = QGridLayout()
        selection_grid.setSpacing(4)
        
        self.draw_polygon_button = ModernButton("Draw Polygon")
        self.draw_polygon_button.clicked.connect(self.on_draw_polygon_button_clicked)
        self.draw_polygon_button.setEnabled(False)
        self.draw_polygon_button.setFixedHeight(28)
        self.draw_polygon_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.draw_polygon_button.setToolTip("Draw a polygon to select points and assign new ITC values")
        self.polygon_selection_active = False
        selection_grid.addWidget(self.draw_polygon_button, 0, 0)

        self.radius_value_input = QDoubleSpinBox()
        self.radius_value_input.setMinimum(0.05)
        self.radius_value_input.setMaximum(100.0)
        self.radius_value_input.setSingleStep(0.1)
        self.radius_value_input.setDecimals(2)
        self.radius_value_input.setValue(1.0)
        self.radius_value_input.setSuffix(" m")
        self.radius_value_input.setFixedWidth(80)
        self.radius_value_input.setFixedHeight(26)
        self.radius_value_input.setStyleSheet("font-size: 9px;")
        self.radius_value_input.setToolTip("Radius around the picked point used to select nearby points")
        selection_grid.addWidget(self.radius_value_input, 0, 1)

        self.radius_export_button = ModernButton("Pick & Export Radius")
        self.radius_export_button.clicked.connect(self.on_radius_export_button_clicked)
        self.radius_export_button.setEnabled(False)
        self.radius_export_button.setFixedHeight(28)
        self.radius_export_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.radius_export_button.setToolTip("Pick a point in the 3D view, select points within the radius, and export them to a tree folder")
        selection_grid.addWidget(self.radius_export_button, 0, 2)
        
        self.select_all_points_button = ModernButton("Select All")
        self.select_all_points_button.clicked.connect(self.select_all_points)
        self.select_all_points_button.setEnabled(False)
        self.select_all_points_button.setFixedHeight(28)
        self.select_all_points_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.select_all_points_button.setToolTip("Select all points in the current visualization without drawing")
        selection_grid.addWidget(self.select_all_points_button, 1, 0)
        
        self.assign_itc_button = ModernButton("Assign ITC")
        self.assign_itc_button.clicked.connect(lambda: self.assign_itc_to_selection())
        self.assign_itc_button.setEnabled(False)
        self.assign_itc_button.setFixedHeight(28)
        self.assign_itc_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.assign_itc_button.setToolTip("Assign new ITC value to selected points")
        selection_grid.addWidget(self.assign_itc_button, 1, 1)

        radius_hint = QLabel("Radius selection exports immediately after one point pick.")
        radius_hint.setStyleSheet("color: #bbbbbb; font-size: 9px;")
        selection_grid.addWidget(radius_hint, 1, 2)
        
        button_layout.addLayout(selection_grid)

        # === VOLUME CALCULATION SECTION ===
        volume_label = QLabel("Volume Analysis")
        volume_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(volume_label)
        
        self.volume_calc_button = ModernButton("Calculate Volume")
        self.volume_calc_button.clicked.connect(self.calculate_volume_from_selection)
        self.volume_calc_button.setEnabled(False)
        self.volume_calc_button.setFixedHeight(32)
        self.volume_calc_button.setToolTip("Perform circle fitting on selected points for volume calculation")
        button_layout.addWidget(self.volume_calc_button)

        volume_data_grid = QGridLayout()
        volume_data_grid.setSpacing(4)
        
        self.save_volume_button = ModernButton("Save Data")
        self.save_volume_button.clicked.connect(self.save_volume_data)
        self.save_volume_button.setEnabled(False)
        self.save_volume_button.setFixedHeight(28)
        self.save_volume_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.save_volume_button.setToolTip("Save current volume calculation data to file")
        volume_data_grid.addWidget(self.save_volume_button, 0, 0)

        self.load_volume_button = ModernButton("Load Data")
        self.load_volume_button.clicked.connect(self.load_volume_data)
        self.load_volume_button.setEnabled(True)
        self.load_volume_button.setFixedHeight(28)
        self.load_volume_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.load_volume_button.setToolTip("Load volume calculation data from file (only the selected tree(s) if any are selected, otherwise all files)")
        volume_data_grid.addWidget(self.load_volume_button, 0, 1)

        self.clear_volume_button = ModernButton("Clear Results")
        self.clear_volume_button.clicked.connect(self.clear_accumulated_volume)
        self.clear_volume_button.setEnabled(False)
        self.clear_volume_button.setFixedHeight(28)
        self.clear_volume_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.clear_volume_button.setToolTip("Clear all accumulated volume calculation results")
        volume_data_grid.addWidget(self.clear_volume_button, 0, 2)

        self.export_trunks_button = ModernButton("Export Trunks")
        self.export_trunks_button.clicked.connect(self.export_trunk_metrics)
        self.export_trunks_button.setEnabled(False)
        self.export_trunks_button.setFixedHeight(28)
        self.export_trunks_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.export_trunks_button.setToolTip("Export detected trunk location, total volume, and DBH to CSV")
        volume_data_grid.addWidget(self.export_trunks_button, 1, 0, 1, 3)
        
        button_layout.addLayout(volume_data_grid)

        # === TRUNK DETECTION SECTION ===
        trunk_label = QLabel("Trunk Separation")
        trunk_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(trunk_label)
        
        trunk_grid = QGridLayout()
        trunk_grid.setSpacing(4)

        self.trunk_slice_height_input = QSpinBox()
        self.trunk_slice_height_input.setMinimum(5)
        self.trunk_slice_height_input.setMaximum(50)
        self.trunk_slice_height_input.setValue(25)
        self.trunk_slice_height_input.setSuffix(" cm")
        self.trunk_slice_height_input.setFixedWidth(70)
        self.trunk_slice_height_input.setFixedHeight(26)
        self.trunk_slice_height_input.setStyleSheet("font-size: 9px;")
        self.trunk_slice_height_input.setToolTip("Height of each trunk slice for trunk detection")

        self.trunk_base_zone_input = QDoubleSpinBox()
        self.trunk_base_zone_input.setMinimum(0.0)
        self.trunk_base_zone_input.setMaximum(50.0)
        self.trunk_base_zone_input.setSingleStep(0.1)
        self.trunk_base_zone_input.setDecimals(2)
        self.trunk_base_zone_input.setValue(0.0)
        self.trunk_base_zone_input.setSuffix(" m")
        self.trunk_base_zone_input.setFixedWidth(80)
        self.trunk_base_zone_input.setFixedHeight(26)
        self.trunk_base_zone_input.setStyleSheet("font-size: 9px;")
        self.trunk_base_zone_input.setToolTip("Trunk slice range from min Z. Set to 0.0 for full-height slicing")

        self.trunk_eps_input = QDoubleSpinBox()
        self.trunk_eps_input.setMinimum(0.01)
        self.trunk_eps_input.setMaximum(5.0)
        self.trunk_eps_input.setSingleStep(0.01)
        self.trunk_eps_input.setDecimals(2)
        self.trunk_eps_input.setValue(0.18)
        self.trunk_eps_input.setSuffix(" m")
        self.trunk_eps_input.setFixedWidth(75)
        self.trunk_eps_input.setFixedHeight(26)
        self.trunk_eps_input.setStyleSheet("font-size: 9px;")
        self.trunk_eps_input.setToolTip("DBSCAN eps radius for trunk clustering")

        self.trunk_min_samples_input = QSpinBox()
        self.trunk_min_samples_input.setMinimum(1)
        self.trunk_min_samples_input.setMaximum(1000)
        self.trunk_min_samples_input.setValue(8)
        self.trunk_min_samples_input.setFixedWidth(60)
        self.trunk_min_samples_input.setFixedHeight(26)
        self.trunk_min_samples_input.setStyleSheet("font-size: 9px;")
        self.trunk_min_samples_input.setToolTip("Minimum samples for trunk DBSCAN")

        self.trunk_merge_dist_input = QDoubleSpinBox()
        self.trunk_merge_dist_input.setMinimum(0.01)
        self.trunk_merge_dist_input.setMaximum(5.0)
        self.trunk_merge_dist_input.setSingleStep(0.01)
        self.trunk_merge_dist_input.setDecimals(2)
        self.trunk_merge_dist_input.setValue(0.25)
        self.trunk_merge_dist_input.setSuffix(" m")
        self.trunk_merge_dist_input.setFixedWidth(75)
        self.trunk_merge_dist_input.setFixedHeight(26)
        self.trunk_merge_dist_input.setStyleSheet("font-size: 9px;")
        self.trunk_merge_dist_input.setToolTip("Max centroid distance to merge clusters across slices")

        self.trunk_min_points_input = QSpinBox()
        self.trunk_min_points_input.setMinimum(1)
        self.trunk_min_points_input.setMaximum(100000)
        self.trunk_min_points_input.setValue(120)
        self.trunk_min_points_input.setFixedWidth(70)
        self.trunk_min_points_input.setFixedHeight(26)
        self.trunk_min_points_input.setStyleSheet("font-size: 9px;")
        self.trunk_min_points_input.setToolTip("Minimum trunk points after base-zone clustering")

        self.trunk_min_span_input = QDoubleSpinBox()
        self.trunk_min_span_input.setMinimum(0.0)
        self.trunk_min_span_input.setMaximum(50.0)
        self.trunk_min_span_input.setSingleStep(0.1)
        self.trunk_min_span_input.setDecimals(2)
        self.trunk_min_span_input.setValue(1.0)
        self.trunk_min_span_input.setSuffix(" m")
        self.trunk_min_span_input.setFixedWidth(75)
        self.trunk_min_span_input.setFixedHeight(26)
        self.trunk_min_span_input.setStyleSheet("font-size: 9px;")
        self.trunk_min_span_input.setToolTip("Minimum vertical span required to keep a trunk")

        self.trunk_full_assign_input = QDoubleSpinBox()
        self.trunk_full_assign_input.setMinimum(0.01)
        self.trunk_full_assign_input.setMaximum(10.0)
        self.trunk_full_assign_input.setSingleStep(0.01)
        self.trunk_full_assign_input.setDecimals(2)
        self.trunk_full_assign_input.setValue(0.45)
        self.trunk_full_assign_input.setSuffix(" m")
        self.trunk_full_assign_input.setFixedWidth(75)
        self.trunk_full_assign_input.setFixedHeight(26)
        self.trunk_full_assign_input.setStyleSheet("font-size: 9px;")
        self.trunk_full_assign_input.setToolTip("Max distance for extending trunk assignment to full height")

        trunk_grid.addWidget(QLabel("Slice"), 0, 0)
        trunk_grid.addWidget(self.trunk_slice_height_input, 0, 1)
        trunk_grid.addWidget(QLabel("Base"), 0, 2)
        trunk_grid.addWidget(self.trunk_base_zone_input, 0, 3)
        trunk_grid.addWidget(QLabel("eps"), 0, 4)
        trunk_grid.addWidget(self.trunk_eps_input, 0, 5)

        trunk_grid.addWidget(QLabel("minS"), 1, 0)
        trunk_grid.addWidget(self.trunk_min_samples_input, 1, 1)
        trunk_grid.addWidget(QLabel("merge"), 1, 2)
        trunk_grid.addWidget(self.trunk_merge_dist_input, 1, 3)
        trunk_grid.addWidget(QLabel("minPts"), 1, 4)
        trunk_grid.addWidget(self.trunk_min_points_input, 1, 5)

        trunk_grid.addWidget(QLabel("span"), 2, 0)
        trunk_grid.addWidget(self.trunk_min_span_input, 2, 1)
        trunk_grid.addWidget(QLabel("extend"), 2, 2)
        trunk_grid.addWidget(self.trunk_full_assign_input, 2, 3)
        
        self.detect_trunks_button = ModernButton("Detect Trunks")
        self.detect_trunks_button.clicked.connect(self.detect_trunks_in_slices)
        self.detect_trunks_button.setEnabled(False)
        self.detect_trunks_button.setFixedHeight(28)
        self.detect_trunks_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.detect_trunks_button.setToolTip("Separate individual trunks in base zone using horizontal slicing + DBSCAN")
        trunk_grid.addWidget(self.detect_trunks_button, 3, 0, 1, 6)

        self.raw_trunk_view_checkbox = QCheckBox("Raw")
        self.raw_trunk_view_checkbox.setChecked(False)
        self.raw_trunk_view_checkbox.setToolTip("Show raw base-zone trunk detections instead of filtered trunks")
        self.raw_trunk_view_checkbox.setFixedHeight(24)
        trunk_grid.addWidget(self.raw_trunk_view_checkbox, 3, 5, 1, 1)
        
        button_layout.addLayout(trunk_grid)

        # === BRANCH & ANALYSIS SECTION ===
        analysis_label = QLabel("Branch & Analysis")
        analysis_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(analysis_label)
        
        branch_grid = QGridLayout()
        branch_grid.setSpacing(4)
        
        self.slice_height_label = QLabel("Slice (cm):")
        self.slice_height_label.setFixedWidth(65)
        self.slice_height_label.setStyleSheet("font-size: 10px;")
        self.slice_height_input = QSpinBox()
        self.slice_height_input.setMinimum(5)
        self.slice_height_input.setMaximum(50)
        self.slice_height_input.setValue(25)
        self.slice_height_input.setSuffix(" cm")
        self.slice_height_input.setFixedWidth(70)
        self.slice_height_input.setFixedHeight(26)
        self.slice_height_input.setStyleSheet("font-size: 9px;")
        self.slice_height_input.setToolTip("Height of each horizontal slice for branch detection")

        self.branch_eps_input = QDoubleSpinBox()
        self.branch_eps_input.setMinimum(0.01)
        self.branch_eps_input.setMaximum(5.0)
        self.branch_eps_input.setSingleStep(0.01)
        self.branch_eps_input.setDecimals(2)
        self.branch_eps_input.setValue(0.08)
        self.branch_eps_input.setSuffix(" m")
        self.branch_eps_input.setFixedWidth(75)
        self.branch_eps_input.setFixedHeight(26)
        self.branch_eps_input.setStyleSheet("font-size: 9px;")
        self.branch_eps_input.setToolTip("DBSCAN eps radius for branch clustering")

        self.branch_min_samples_input = QSpinBox()
        self.branch_min_samples_input.setMinimum(1)
        self.branch_min_samples_input.setMaximum(1000)
        self.branch_min_samples_input.setValue(3)
        self.branch_min_samples_input.setFixedWidth(60)
        self.branch_min_samples_input.setFixedHeight(26)
        self.branch_min_samples_input.setStyleSheet("font-size: 9px;")
        self.branch_min_samples_input.setToolTip("Minimum samples for branch DBSCAN")

        self.branch_merge_dist_input = QDoubleSpinBox()
        self.branch_merge_dist_input.setMinimum(0.01)
        self.branch_merge_dist_input.setMaximum(5.0)
        self.branch_merge_dist_input.setSingleStep(0.01)
        self.branch_merge_dist_input.setDecimals(2)
        self.branch_merge_dist_input.setValue(0.15)
        self.branch_merge_dist_input.setSuffix(" m")
        self.branch_merge_dist_input.setFixedWidth(75)
        self.branch_merge_dist_input.setFixedHeight(26)
        self.branch_merge_dist_input.setStyleSheet("font-size: 9px;")
        self.branch_merge_dist_input.setToolTip("Max centroid distance to merge branch clusters across slices")

        branch_grid.addWidget(QLabel("Slice"), 0, 0)
        branch_grid.addWidget(self.slice_height_input, 0, 1)
        branch_grid.addWidget(QLabel("eps"), 0, 2)
        branch_grid.addWidget(self.branch_eps_input, 0, 3)
        branch_grid.addWidget(QLabel("minS"), 0, 4)
        branch_grid.addWidget(self.branch_min_samples_input, 0, 5)

        branch_grid.addWidget(QLabel("merge"), 1, 0)
        branch_grid.addWidget(self.branch_merge_dist_input, 1, 1)
        
        self.detect_branches_button = ModernButton("Detect")
        self.detect_branches_button.clicked.connect(self.detect_branch_clusters_in_slices)
        self.detect_branches_button.setEnabled(False)
        self.detect_branches_button.setFixedHeight(26)
        self.detect_branches_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 4px; }")
        self.detect_branches_button.setToolTip("Run DBSCAN on each slice to detect individual branches")

        branch_grid.addWidget(self.detect_branches_button, 1, 2, 1, 2)
        
        button_layout.addLayout(branch_grid)

        # === ANALYSIS SECTION ===
        analysis_label = QLabel("Analysis")
        analysis_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(analysis_label)

        analysis_grid = QGridLayout()
        analysis_grid.setSpacing(4)
        
        self.analyze_button = ModernButton("Analyze Tree")
        self.analyze_button.clicked.connect(self.analyze_tree_with_ai)
        self.analyze_button.setEnabled(False)
        self.analyze_button.setFixedHeight(28)
        self.analyze_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.analyze_button.setToolTip("Use AI to analyze tree structure and segmentation quality")
        analysis_grid.addWidget(self.analyze_button, 0, 0)

        self.batch_analyze_button = ModernButton("Batch Analyze")
        self.batch_analyze_button.clicked.connect(self.batch_analyze_trunk_volumes)
        self.batch_analyze_button.setEnabled(False)
        self.batch_analyze_button.setFixedHeight(28)
        self.batch_analyze_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.batch_analyze_button.setToolTip("Analyze all trees in list: visualize trunk → select all points → calculate volume → save")
        analysis_grid.addWidget(self.batch_analyze_button, 0, 1)
        
        button_layout.addLayout(analysis_grid)

        # === UTILITY SECTION ===
        utility_label = QLabel("Utilities")
        utility_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px; margin-bottom: 3px;")
        button_layout.addWidget(utility_label)
        
        utility_grid = QGridLayout()
        utility_grid.setSpacing(4)

        self.crown_polygon_button = ModernButton("Crown Polygon")
        self.crown_polygon_button.clicked.connect(self.create_tree_crown_polygon)
        self.crown_polygon_button.setEnabled(False)
        self.crown_polygon_button.setFixedHeight(28)
        self.crown_polygon_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.crown_polygon_button.setToolTip("Create 2D polygon from all tree points projected to XY plane")
        utility_grid.addWidget(self.crown_polygon_button, 0, 0)

        self.fit_to_screen_button = ModernButton("Fit View")
        self.fit_to_screen_button.clicked.connect(self.fit_to_screen)
        self.fit_to_screen_button.setEnabled(False)
        self.fit_to_screen_button.setFixedHeight(28)
        self.fit_to_screen_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.fit_to_screen_button.setToolTip("Reset camera to fit all visible objects in the view")
        utility_grid.addWidget(self.fit_to_screen_button, 0, 1)

        self.clear_button = ModernButton("Clear View")
        self.clear_button.clicked.connect(self.clear_plot)
        self.clear_button.setFixedHeight(28)
        self.clear_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self.clear_button.setToolTip("Clear the 3D view and reset to default colors (removes cluster highlighting)")
        utility_grid.addWidget(self.clear_button, 0, 2)

        self.save_button = ModernButton("Save LAS")
        self.save_button.clicked.connect(self.save_las_file)
        self.save_button.setEnabled(False)
        self.save_button.setFixedHeight(28)
        self.save_button.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        utility_grid.addWidget(self.save_button, 1, 0, 1, 3)
        
        button_layout.addLayout(utility_grid)

        # Remove the reset view button since clear_plot already resets the camera
        # self.reset_view_button = ModernButton("Reset View")
        # self.reset_view_button.clicked.connect(self.reset_view)
        # button_layout.addWidget(self.reset_view_button)
        
        viz_layout.addLayout(button_layout)

        layout.addWidget(viz_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(20)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        return scroll_area

    def load_las_file(self):
        """Open file dialog to add single or multiple LAS/LAZ files to the Layer Manager."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select LAS File(s)",
            "",
            "LAS files (*.las *.laz)"
        )
        if not file_paths:
            return

        added_paths = []
        for path in file_paths:
            rec = self._add_las_to_layers(path)
            if rec:
                added_paths.append(path)

        if added_paths:
            # Activate the last added layer
            self.activate_las_layer(added_paths[-1])

    def _add_las_to_layers(self, file_path):
        """Register a LAS file in self.las_layers if not already present."""
        norm_path = os.path.normpath(file_path)
        for layer in self.las_layers:
            if os.path.normpath(layer['path']) == norm_path:
                return layer  # Already present

        try:
            import laspy
            data = laspy.read(file_path)
            num_points = len(data.points)
            has_stemcls = 'stemcls' in data.point_format.dimension_names
            num_trees = 0
            if 'itc' in data.point_format.dimension_names:
                itc_vals = np.array(data['itc'])
                num_trees = len(np.unique(itc_vals[itc_vals > 0]))

            layer_rec = {
                'path': norm_path,
                'name': os.path.basename(file_path),
                'num_points': num_points,
                'num_trees': num_trees,
                'has_stemcls': has_stemcls,
                'checked': True
            }
            self.las_layers.append(layer_rec)
            self._update_las_layer_list_widget()
            return layer_rec
        except Exception as e:
            self.log_to_console(f"⚠️ Could not inspect metadata for {os.path.basename(file_path)}: {e}")
            return None

    def _update_las_layer_list_widget(self):
        """Re-populate the LAS layer list widget."""
        self._updating_las_layer_list = True
        self.las_layer_list.clear()

        for layer in self.las_layers:
            name = layer['name']
            pts = layer['num_points']
            trees = layer['num_trees']
            display_text = f"{name} ({trees} trees, {pts:,} pts)"

            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer.get('checked', True) else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, layer['path'])

            # Bold font if this layer is currently active
            if self.current_las_path and os.path.normpath(self.current_las_path) == os.path.normpath(layer['path']):
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.las_layer_list.addItem(item)

        self._updating_las_layer_list = False

    def _on_las_layer_clicked(self, item):
        """Handle user clicking a layer item to switch active viewer."""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and (not self.current_las_path or os.path.normpath(path) != os.path.normpath(self.current_las_path)):
            self.activate_las_layer(path)

    def _on_las_layer_check_changed(self, item):
        """Handle user toggling a layer checkbox."""
        if getattr(self, '_updating_las_layer_list', False):
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        is_checked = (item.checkState() == Qt.CheckState.Checked)
        for layer in self.las_layers:
            if os.path.normpath(layer['path']) == os.path.normpath(path):
                layer['checked'] = is_checked
                break

    def remove_selected_las_layer(self):
        """Remove the selected layer from self.las_layers."""
        current_item = self.las_layer_list.currentItem()
        if not current_item:
            return
        path = current_item.data(Qt.ItemDataRole.UserRole)
        self.las_layers = [l for l in self.las_layers if os.path.normpath(l['path']) != os.path.normpath(path)]
        self._update_las_layer_list_widget()
        if self.current_las_path and os.path.normpath(self.current_las_path) == os.path.normpath(path):
            if self.las_layers:
                self.activate_las_layer(self.las_layers[0]['path'])
            else:
                self.las_data = None
                self.current_las_path = None
                self.file_label.setText("No file loaded")
                self.tree_list.clear()

    def toggle_las_batch_checks(self):
        """Toggle check state of all LAS layers."""
        if not self.las_layers:
            return
        all_checked = all(l.get('checked', True) for l in self.las_layers)
        new_state = not all_checked
        for l in self.las_layers:
            l['checked'] = new_state
        self._update_las_layer_list_widget()
        if hasattr(self, 'toggle_las_batch_btn'):
            self.toggle_las_batch_btn.setText("Uncheck All" if new_state else "Check All")

    def activate_las_layer(self, file_path, silent=False):
        """Switch active LAS file, load data into memory, and update UI."""
        norm_path = os.path.normpath(file_path)
        # Ensure file is in layers list
        found = False
        for l in self.las_layers:
            if os.path.normpath(l['path']) == norm_path:
                found = True
                break
        if not found:
            self._add_las_to_layers(file_path)

        self.load_las_data(file_path, silent=silent)
        self._update_las_layer_list_widget()

    def load_las_data(self, file_path, silent=False):
        """Load LAS file and extract ITC values."""
        import time
        load_start = time.perf_counter()
        print(f"[LOAD] {time.strftime('%H:%M:%S')} - Starting to load: {os.path.basename(file_path)}")
        self.log_to_console(f"📂 Loading file: {os.path.basename(file_path)}")
        
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress

            # Load LAS file
            read_start = time.perf_counter()
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Reading LAS file...")
            self.las_data = laspy.read(file_path)
            read_time = time.perf_counter() - read_start
            num_points = len(self.las_data.points)
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - LAS file read: {num_points:,} points, {file_size_mb:.1f} MB ({read_time:.2f}s)")
            self.log_to_console(f"📊 File read: {num_points:,} points, {file_size_mb:.1f} MB in {read_time:.2f}s")
            
            self.file_label.setText(f"Loaded: {os.path.basename(file_path)}")
            # Remember the current LAS file path for automatic saves
            try:
                self.current_las_path = os.path.normpath(file_path)
            except Exception:
                self.current_las_path = None

            # Ensure file is registered in self.las_layers
            norm_path = os.path.normpath(file_path)
            if not any(os.path.normpath(l['path']) == norm_path for l in self.las_layers):
                has_stemcls_check = 'stemcls' in self.las_data.point_format.dimension_names
                num_trees_check = 0
                if 'itc' in self.las_data.point_format.dimension_names:
                    itc_v = np.array(self.las_data['itc'])
                    num_trees_check = len(np.unique(itc_v[itc_v > 0]))
                self.las_layers.append({
                    'path': norm_path,
                    'name': os.path.basename(file_path),
                    'num_points': num_points,
                    'num_trees': num_trees_check,
                    'has_stemcls': has_stemcls_check,
                    'checked': True
                })

            # Check for ITC field
            if 'itc' not in self.las_data.point_format.dimension_names:
                if not silent:
                    QMessageBox.warning(self, "Warning",
                                      "No 'itc' scalar field found in the LAS file.")
                self.las_data = None
                return

            # Check for stemcls field for trunk visualization
            has_stemcls = 'stemcls' in self.las_data.point_format.dimension_names
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Fields: itc=True, stemcls={has_stemcls}")

            # Extract unique ITC values
            itc_start = time.perf_counter()
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Extracting ITC values...")
            itc_values = np.array(self.las_data['itc'])
            self.unique_itc_values = np.unique(itc_values[itc_values > 0]).astype(int)  # Exclude 0 (likely unassigned) and convert to int
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Found {len(self.unique_itc_values)} unique ITC values ({time.perf_counter() - itc_start:.3f}s)")

            # Filter tree IDs by stemcls = 2 if stemcls field exists
            # For large files (>50M points), ask user if they want to filter
            perform_stemcls_filter = False
            if has_stemcls:
                LARGE_FILE_THRESHOLD = 50_000_000  # 50 million points
                if num_points > LARGE_FILE_THRESHOLD and not silent:
                    reply = QMessageBox.question(
                        self,
                        "Large File Detected",
                        f"This file has {num_points:,} points ({len(self.unique_itc_values)} trees).\n\n"
                        f"Filtering by stemcls=2 (stem points) may take a while.\n\n"
                        f"Do you want to filter trees by stem presence?\n"
                        f"• Yes = Show only trees with stem points (slower)\n"
                        f"• No = Show all trees (faster)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No  # Default to No for large files
                    )
                    perform_stemcls_filter = (reply == QMessageBox.StandardButton.Yes)
                    print(f"[LOAD] {time.strftime('%H:%M:%S')} - User chose {'to filter' if perform_stemcls_filter else 'to skip filtering'} for large file")
                else:
                    perform_stemcls_filter = True  # Always filter for smaller files
                    
            if has_stemcls and perform_stemcls_filter:
                filter_start = time.perf_counter()
                print(f"[LOAD] {time.strftime('%H:%M:%S')} - Filtering by stemcls=2...")
                self.log_to_console(f"⏳ Filtering {len(self.unique_itc_values)} trees by stem presence... (this may take a while)")
                QApplication.processEvents()  # Update UI to show message
                
                stemcls_values = np.array(self.las_data['stemcls'])
                filtered_ids = []
                for tree_id in self.unique_itc_values:
                    mask = (itc_values == tree_id) & (stemcls_values == 2)
                    if np.any(mask):
                        filtered_ids.append(tree_id)
                self.unique_itc_values = np.array(filtered_ids)
                print(f"[LOAD] {time.strftime('%H:%M:%S')} - Filtered to {len(self.unique_itc_values)} trees with stems ({time.perf_counter() - filter_start:.3f}s)")
                self.log_to_console(f"✅ Filtered to {len(self.unique_itc_values)} trees with stem points")
            elif has_stemcls and not perform_stemcls_filter:
                print(f"[LOAD] {time.strftime('%H:%M:%S')} - Skipped stemcls filtering (user choice)")
                self.log_to_console(f"⚡ Skipped stem filtering - showing all {len(self.unique_itc_values)} trees")

            # Populate tree list widget
            list_start = time.perf_counter()
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Populating tree list...")
            self.tree_list.clear()
            for value in sorted(self.unique_itc_values):
                item = QListWidgetItem(str(value))
                # Color red if this tree has volume data
                if str(value) in self.trees_with_volume_data:
                    item.setForeground(QColor('red'))
                self.tree_list.addItem(item)
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Tree list populated ({time.perf_counter() - list_start:.3f}s)")

            # Populate color field combo box
            available_fields = list(self.las_data.point_format.dimension_names)
            color_fields = [field for field in available_fields
                           if field not in ['x', 'y', 'z']]  # Include itc for multiple tree coloring

            self.color_combo.clear()
            self.color_combo.addItem("Default (green)")
            
            # Check if RGB fields exist
            has_red = 'red' in available_fields
            has_green = 'green' in available_fields
            has_blue = 'blue' in available_fields
            if has_red and has_green and has_blue:
                self.color_combo.addItem("RGB (red, green, blue)")
            
            for field in sorted(color_fields):
                self.color_combo.addItem(field)

            self.visualize_button.setEnabled(True)
            self.trunk_button.setEnabled(has_stemcls)
            self.batch_analyze_button.setEnabled(has_stemcls)
            self.crown_polygon_button.setEnabled(True)  # Always enabled since it doesn't require stemcls
            self.view_neighbors_button.setEnabled(True)
            self.draw_polygon_button.setEnabled(True)
            self.radius_export_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.fit_to_screen_button.setEnabled(True)

            total_time = time.perf_counter() - load_start
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Load complete: {total_time:.2f}s total")
            self.log_to_console(f"✅ Loaded {len(self.unique_itc_values)} trees from {num_points:,} points in {total_time:.2f}s")
            
            if not silent:
                QMessageBox.information(self, "Success",
                                      f"Loaded {len(self.unique_itc_values)} unique tree IDs from {len(self.las_data.points)} points.")

        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "Error", f"Failed to load LAS file:\n{str(e)}")
            self.las_data = None
        finally:
            self.progress_bar.setVisible(False)

    # ------------------------------------------------------------------
    # GDB Import & 3D Overlay
    # ------------------------------------------------------------------
    def import_points_from_gdb(self):
        """Open GDB import dialog and render features in 3D. No LAS file required."""
        dlg = GdbImportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        params = dlg.get_import_params()
        gdb_path       = params["gdb_path"]
        layer_name     = params["layer"]
        z_field        = params["z_field"]
        z_constant     = params["z_constant"]
        color          = params["color"]
        color_name     = params["color_name"]
        point_size     = params["point_size"]
        render_spheres = params["render_spheres"]

        try:
            import geopandas as gpd
        except ImportError:
            QMessageBox.critical(self, "Missing Dependency",
                "geopandas is required.\n\npip install pyogrio geopandas"); return

        try:
            import pyogrio  # noqa
        except ImportError:
            try:
                import fiona  # noqa
            except ImportError:
                QMessageBox.critical(self, "Missing Dependency",
                    "pyogrio or fiona is required.\n\npip install pyogrio geopandas"); return

        if not self.plotter:
            QMessageBox.warning(self, "Warning", "3D viewer not initialized."); return

        self.log_to_console(f"\U0001f4c2 Reading GDB layer: {layer_name} from {os.path.basename(gdb_path)}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        QApplication.processEvents()

        try:
            gdf = gpd.read_file(gdb_path, layer=layer_name)
        except Exception as exc:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Read Error", f"Failed to read layer:\n{exc}"); return

        if gdf.empty:
            self.progress_bar.setVisible(False)
            QMessageBox.warning(self, "Empty Layer", f"Layer '{layer_name}' has no features."); return

        n_features = len(gdf)
        self.log_to_console(f"\U0001f4ca GDB layer read: {n_features:,} features")

        try:
            xs = gdf.geometry.x.to_numpy(dtype=float)
            ys = gdf.geometry.y.to_numpy(dtype=float)
            if z_field:
                zs = gdf[z_field].to_numpy(dtype=float)
            else:
                try:
                    zs = gdf.geometry.z.to_numpy(dtype=float)
                    if not np.all(np.isfinite(zs)):
                        raise ValueError("Non-finite Z")
                except Exception:
                    zs = np.full(n_features, z_constant, dtype=float)
                    self.log_to_console(f"\u2139\ufe0f  No geometry Z – using constant {z_constant:.3f} m")
        except Exception as exc:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Coordinate Error", f"Could not extract XYZ:\n{exc}"); return

        try:
            coords = np.column_stack([xs, ys, zs])
            actor_name = f"gdb_layer_{layer_name}"
            idx = 2
            while actor_name in self.gdb_layers:
                actor_name = f"gdb_layer_{layer_name}_{idx}"
                idx += 1

            self.gdb_layers[actor_name] = {
                "coords": coords,
                "color": color,
                "color_name": color_name,
                "point_size": point_size,
                "render_spheres": render_spheres,
                "visible": True,
                "layer_name": layer_name,
                "n_features": n_features,
                "gdf": gdf,
                "label_field": None,
                "label_visible": False,
            }

            self.plotter.add_points(
                pv.PolyData(coords),
                color=color,
                point_size=point_size,
                render_points_as_spheres=render_spheres,
                name=actor_name
            )
            self._set_actor_pickable(actor_name, self.gdb_pick_mode)
            self.plotter.reset_camera()
            self.plotter.update()

            self._add_gdb_layer_row(actor_name)

            self.log_to_console(
                f"\u2705 Displayed {n_features:,} GDB points from \'{layer_name}\' ({color_name} markers)."
            )
            self.progress_bar.setVisible(False)
            QMessageBox.information(
                self, "Layer Rendered",
                f"Displayed {n_features:,} GDB points from \'{layer_name}\' in 3D viewer!\n\n"
                f"\u2022 Color: {color_name}\n"
                f"\u2022 Marker Size: {point_size}\n"
                f"\u2022 3D Spheres: {'Yes' if render_spheres else 'No'}\n\n"
                "Manage visibility and size in the \'GDB Layer Manager\' panel."
            )
        except Exception as exc:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Rendering Error", f"Could not render features:\n{exc}")
        finally:
            self.progress_bar.setVisible(False)

    def _restore_gdb_layers(self):
        """Re-render all visible GDB overlay layers after plotter.clear()."""
        if not self.plotter:
            return
        for actor_name, layer in self.gdb_layers.items():
            if not layer.get("visible", True):
                continue
            try:
                self.plotter.add_points(
                    pv.PolyData(layer["coords"]),
                    color=layer["color"],
                    point_size=layer["point_size"],
                    render_points_as_spheres=layer["render_spheres"],
                    name=actor_name,
                    reset_camera=False
                )
                self._set_actor_pickable(actor_name, self.gdb_pick_mode)
                # Restore labels if they were enabled
                if layer.get("label_visible") and layer.get("label_field"):
                    self._refresh_gdb_labels(actor_name)
            except Exception:
                pass
        # Re-arm point picking after scene rebuild
        self._rearm_point_picking()

    def _rearm_point_picking(self):
        """Re-enable point picking after the plotter has been cleared and repopulated.
        
        Must be called after every plotter.clear() + _restore_gdb_layers() to ensure
        accurate point picking across scene rebuilds (trunk detection, branch detection,
        color changes, etc.).
        """
        if self.plotter is None:
            return
        try:
            self.plotter.disable_picking()
        except Exception:
            pass
        try:
            self.plotter.enable_point_picking(callback=self.on_point_picked, show_message=False)
        except Exception:
            pass
        self._set_volume_overlay_actors_unpickable()

    def _set_actor_pickable(self, name, pickable):
        """Toggle picking on a named actor.

        Overlay layers (GDB imports, bounding box, DBH marker, etc.) are made
        non-pickable so they do not steal picks from the tree point cloud and
        corrupt point-picking accuracy.
        """
        if not self.plotter:
            return
        try:
            actors = self.plotter.actors
            actor = actors.get(name) if hasattr(actors, "get") else actors[name]
        except Exception:
            actor = None
        if actor is None:
            return
        candidates = [actor]
        try:
            prop = getattr(actor, "prop", None)
        except Exception:
            prop = None
        if prop is not None:
            candidates.append(prop)
        for obj in candidates:
            try:
                setter = getattr(obj, "SetPickable", None)
            except Exception:
                setter = None
            if callable(setter):
                try:
                    setter(bool(pickable))
                    return
                except Exception:
                    continue
            try:
                if hasattr(obj, "pickable"):
                    obj.pickable = bool(pickable)
                    return
            except Exception:
                continue

    def _set_volume_overlay_actors_unpickable(self):
        """Keep volume/DBH circle overlays out of the point picker.

        Loaded and calculated volume circles are dense PolyData (dozens of
        vertices per ring). If those actors stay pickable, vtkPointPicker
        snaps to the circle vertices instead of the tree point cloud.

        This iterates the actor dict ONCE and sets pickability directly on
        each actor (no per-actor re-lookup), so it stays fast even with
        thousands of actors.
        """
        if not self.plotter:
            return
        try:
            actors = self.plotter.actors
            items = list(actors.items()) if hasattr(actors, "items") else list(actors)
        except Exception:
            return

        overlay_tokens = (
            'dbh_',
            'volume_section_',
            'trunk_dbh_',
            'section_info_label',
            'volume_info_text',
            'circle',
            'trajectory',
        )

        def _set_pickable(obj, pickable):
            try:
                setter = getattr(obj, "SetPickable", None)
                if callable(setter):
                    setter(bool(pickable))
                    return
            except Exception:
                pass
            try:
                if hasattr(obj, "pickable"):
                    obj.pickable = bool(pickable)
            except Exception:
                pass

        for item in items:
            if isinstance(item, tuple):
                name, actor = item
            else:
                name, actor = item, None
            if name == 'tree_point_cloud':
                continue
            lname = str(name).lower()
            if not any(token in lname for token in overlay_tokens):
                continue
            if actor is not None:
                _set_pickable(actor, False)
                try:
                    prop = getattr(actor, "prop", None)
                except Exception:
                    prop = None
                if prop is not None:
                    _set_pickable(prop, False)

    def _on_gdb_pick_mode_toggled(self, checked):
        """Toggle between GDB point picking and tree point picking."""
        self.gdb_pick_mode = bool(checked)
        if hasattr(self, 'gdb_pick_mode_button'):
            self.gdb_pick_mode_button.setText("Pick GDB Points: ON" if checked else "Pick GDB Points: OFF")
        self._apply_pick_mode()
        if checked:
            self.log_to_console("GDB pick mode ON: click a GDB sphere to view its attributes.")
        else:
            self.log_to_console("GDB pick mode OFF: tree point picking restored.")

    def _apply_pick_mode(self):
        """Set actor pickability based on the current pick mode.

        GDB pick mode ON  -> GDB layers pickable, tree point cloud not pickable.
        GDB pick mode OFF -> tree point cloud pickable, GDB layers not pickable.
        """
        if not self.plotter:
            return
        gdb_mode = getattr(self, 'gdb_pick_mode', False)
        for actor_name in list(self.gdb_layers.keys()):
            self._set_actor_pickable(actor_name, gdb_mode)
        self._set_actor_pickable('tree_point_cloud', not gdb_mode)
        self._set_volume_overlay_actors_unpickable()

    def _extract_picked_position(self, picked_info):
        """Extract the 3D picked position from a PyVista pick callback payload."""
        try:
            if hasattr(picked_info, 'picked_point'):
                return np.asarray(picked_info.picked_point, dtype=float)
            if isinstance(picked_info, dict) and 'picked_point' in picked_info:
                return np.asarray(picked_info['picked_point'], dtype=float)
            if hasattr(picked_info, 'points') and picked_info.points is not None:
                return np.asarray(picked_info.points[0], dtype=float)
            if isinstance(picked_info, np.ndarray):
                return picked_info.ravel()
        except Exception:
            return None
        return None

    def _handle_gdb_pick(self, picked_info):
        """Resolve a pick against GDB overlay layers and show feature attributes."""
        picked_point = self._extract_picked_position(picked_info)
        if picked_point is None or len(picked_point) < 3:
            self.log_to_console("Warning: Could not resolve GDB pick position")
            return

        best = None  # (distance, actor_name, feature_index)
        for actor_name, layer in self.gdb_layers.items():
            if not layer.get("visible", True):
                continue
            coords = layer.get("coords")
            if coords is None or len(coords) == 0:
                continue
            d2 = np.sum((np.asarray(coords)[:, :3] - picked_point[:3]) ** 2, axis=1)
            idx = int(np.argmin(d2))
            dist = float(np.sqrt(d2[idx]))
            if best is None or dist < best[0]:
                best = (dist, actor_name, idx)

        if best is None:
            self.log_to_console("No visible GDB points available to pick.")
            return

        dist, actor_name, idx = best
        self._show_gdb_feature_details(actor_name, idx)

    def _show_gdb_feature_details(self, actor_name, feature_index):
        """Log the geodatabase attributes for a picked GDB feature to the UI console."""
        layer = self.gdb_layers.get(actor_name, {})
        layer_label = layer.get("layer_name", actor_name)
        coords = layer.get("coords")
        gdf = layer.get("gdf")

        self.log_to_console("=" * 50)
        self.log_to_console(f"🔍 GDB Point Picked — Layer: {layer_label}  |  Feature #{feature_index}")
        self.log_to_console("-" * 50)

        if coords is not None and 0 <= feature_index < len(coords):
            x, y, z = np.asarray(coords)[feature_index][:3]
            self.log_to_console(f"📍 X: {x:.3f}  Y: {y:.3f}  Z: {z:.3f}")
        self.log_to_console("-" * 50)

        if gdf is not None and 0 <= feature_index < len(gdf):
            try:
                geom_name = gdf.geometry.name
            except Exception:
                geom_name = 'geometry'
            row = gdf.iloc[feature_index]
            for col in gdf.columns:
                if col == geom_name:
                    continue
                self.log_to_console(f"   {col}: {row[col]}")
        else:
            self.log_to_console("(no attribute table stored for this layer)")

        self.log_to_console("=" * 50)

    def _show_text_dialog(self, title, text):
        """Show a simple read-only text dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(420, 480)
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    def _add_gdb_layer_row(self, actor_name):
        """Add a control row to the GDB Layer Manager sidebar panel."""
        layer = self.gdb_layers[actor_name]

        # Use a QFrame card matching the viewer theme
        row = QFrame()
        row.setObjectName(f"gdb_row_{actor_name}")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setSpacing(10)
        row.setStyleSheet("""
            QFrame {
                background-color: #2e2e2e;
                border: 1px solid #444444;
                border-radius: 6px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        # Top line: checkbox + color dot + layer name + point count + remove button
        top = QHBoxLayout()
        top.setSpacing(6)

        vis_cb = QCheckBox()
        vis_cb.setChecked(True)
        vis_cb.setToolTip("Toggle layer visibility in 3D view")

        color_dot = QLabel("●")
        color_dot.setStyleSheet(f"color: {layer['color']}; font-size: 14px; font-weight: bold;")
        color_dot.setObjectName(f"color_dot_{actor_name}")  # store actor_name for later lookup

        # Color picker button
        color_btn = QPushButton("🎨")
        color_btn.setFixedSize(24, 20)
        color_btn.setToolTip("Change point color for this layer")
        color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {layer['color']};
                border: 1px solid #555555;
                border-radius: 3px;
                font-size: 10px;
                padding: 0px;
            }}
            QPushButton:hover {{
                border-color: #888888;
            }}
        """)
        color_btn.clicked.connect(lambda _, an=actor_name, cd=color_dot, cb=color_btn:
            self._on_gdb_color_pick(an, cd, cb))

        name_lbl = QLabel(layer["layer_name"])
        name_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold;")
        name_lbl.setWordWrap(False)

        feat_lbl = QLabel(f"{layer['n_features']:,} pts")
        feat_lbl.setStyleSheet("color: #aaaaaa; font-size: 9px; background-color: #383838; padding: 2px 5px; border-radius: 3px;")

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setToolTip("Remove layer from 3D view")
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d2424;
                color: #ff6666;
                border: 1px solid #663333;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #5c2c2c;
                color: #ff9999;
                border-color: #884444;
            }
        """)
        remove_btn.clicked.connect(lambda _, an=actor_name, r=row: self._remove_gdb_layer(an, r))

        top.addWidget(vis_cb)
        top.addWidget(color_dot)
        top.addWidget(color_btn)
        top.addWidget(name_lbl, 1)
        top.addWidget(feat_lbl)
        top.addWidget(remove_btn)
        row_layout.addLayout(top)

        # Size slider line
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        size_lbl = QLabel("Size:")
        size_lbl.setStyleSheet("color: #bbbbbb; font-size: 10px;")
        size_lbl.setFixedWidth(28)
        size_slider = QSlider(Qt.Orientation.Horizontal)
        size_slider.setMinimum(1)
        size_slider.setMaximum(50)
        size_slider.setValue(layer["point_size"])
        size_slider.setToolTip("Adjust marker point / sphere size")

        size_val_lbl = QLabel(str(layer["point_size"]))
        size_val_lbl.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 10px; min-width: 18px;")

        def on_size_change(val, an=actor_name, vl=size_val_lbl):
            vl.setText(str(val))
            self.gdb_layers[an]["point_size"] = val
            if self.gdb_layers[an]["visible"] and self.plotter:
                try:
                    self.plotter.add_points(
                        pv.PolyData(self.gdb_layers[an]["coords"]),
                        color=self.gdb_layers[an]["color"],
                        point_size=val,
                        render_points_as_spheres=self.gdb_layers[an]["render_spheres"],
                        name=an,
                        reset_camera=False
                    )
                    self._set_actor_pickable(an, self.gdb_pick_mode)
                    self.plotter.update()
                except Exception:
                    pass

        size_slider.valueChanged.connect(on_size_change)
        size_row.addWidget(size_lbl)
        size_row.addWidget(size_slider, 1)
        size_row.addWidget(size_val_lbl)
        row_layout.addLayout(size_row)

        # ── Label field row ─────────────────────────────────────────
        label_row = QHBoxLayout()
        label_row.setSpacing(6)

        label_field_lbl = QLabel("Label:")
        label_field_lbl.setStyleSheet("color: #bbbbbb; font-size: 10px;")
        label_field_lbl.setFixedWidth(35)

        # Build the combo with GDF column names (excluding geometry column)
        gdf = layer.get("gdf")
        label_combo = QComboBox()
        label_combo.setStyleSheet("QComboBox { font-size: 10px; padding: 2px; }")
        label_combo.addItem("None", None)
        if gdf is not None:
            try:
                geom_name = gdf.geometry.name
            except Exception:
                geom_name = "geometry"
            for col in gdf.columns:
                if col == geom_name:
                    continue
                label_combo.addItem(str(col), str(col))

        # Restore previous selection if any
        saved_field = layer.get("label_field")
        if saved_field:
            idx = label_combo.findData(saved_field)
            if idx >= 0:
                label_combo.setCurrentIndex(idx)

        # Label visibility toggle
        label_vis_cb = QCheckBox("Show")
        label_vis_cb.setChecked(layer.get("label_visible", False))
        label_vis_cb.setToolTip("Toggle point label visibility for this layer")
        label_vis_cb.setStyleSheet("QCheckBox { color: #bbbbbb; font-size: 10px; }")

        def on_label_field_change(idx, an=actor_name, combo=label_combo):
            field = combo.itemData(idx)
            layer = self.gdb_layers.get(an)
            if layer is None:
                return
            layer["label_field"] = field
            if field and layer.get("label_visible", False):
                self._refresh_gdb_labels(an)
            elif not field:
                # Remove labels when "None" selected
                if self.plotter:
                    try:
                        self.plotter.remove_actor(f"{an}_labels")
                        self.plotter.update()
                    except Exception:
                        pass

        def on_label_vis_change(state, an=actor_name):
            layer = self.gdb_layers.get(an)
            if layer is None:
                return
            layer["label_visible"] = (state == 2)
            if state == 2 and layer.get("label_field"):
                self._refresh_gdb_labels(an)
            else:
                if self.plotter:
                    try:
                        self.plotter.remove_actor(f"{an}_labels")
                        self.plotter.update()
                    except Exception:
                        pass

        label_combo.currentIndexChanged.connect(on_label_field_change)
        label_vis_cb.stateChanged.connect(on_label_vis_change)

        label_row.addWidget(label_field_lbl)
        label_row.addWidget(label_combo, 1)
        label_row.addWidget(label_vis_cb)
        row_layout.addLayout(label_row)

        def on_vis_change(checked, an=actor_name):
            self.gdb_layers[an]["visible"] = checked
            if not self.plotter:
                return
            if checked:
                try:
                    li = self.gdb_layers[an]
                    self.plotter.add_points(
                        pv.PolyData(li["coords"]),
                        color=li["color"],
                        point_size=li["point_size"],
                        render_points_as_spheres=li["render_spheres"],
                        name=an,
                        reset_camera=False
                    )
                    self._set_actor_pickable(an, self.gdb_pick_mode)
                    # Restore labels if they were enabled
                    if li.get("label_visible") and li.get("label_field"):
                        self._refresh_gdb_labels(an)
                    self.plotter.update()
                except Exception:
                    pass
            else:
                try:
                    self.plotter.remove_actor(an)
                    # Also remove labels when hiding
                    try:
                        self.plotter.remove_actor(f"{an}_labels")
                    except Exception:
                        pass
                    self.plotter.update()
                except Exception:
                    pass

        vis_cb.stateChanged.connect(lambda state, an=actor_name: on_vis_change(state == 2, an))

        count = self.gdb_layers_container_layout.count()
        self.gdb_layers_container_layout.insertWidget(count - 1, row)
        self.gdb_layer_group.setVisible(True)

    def _remove_gdb_layer(self, actor_name, row_widget):
        """Remove a GDB layer from the 3D view and the sidebar."""
        if self.plotter:
            try:
                self.plotter.remove_actor(actor_name)
                # Also remove any associated label actor
                label_actor = f"{actor_name}_labels"
                try:
                    self.plotter.remove_actor(label_actor)
                except Exception:
                    pass
                self.plotter.update()
            except Exception:
                pass
        self.gdb_layers.pop(actor_name, None)
        row_widget.setParent(None)
        row_widget.deleteLater()
        if not self.gdb_layers:
            self.gdb_layer_group.setVisible(False)

    def _on_gdb_color_pick(self, actor_name, color_dot_label=None, color_button=None):
        """Open a color dialog and update the GDB layer's point color."""
        from PyQt6.QtWidgets import QColorDialog
        layer = self.gdb_layers.get(actor_name)
        if layer is None:
            return
        current = QColor(layer["color"])
        new_color = QColorDialog.getColor(current, self, "Pick Point Color")
        if not new_color.isValid():
            return  # user cancelled

        hex_color = new_color.name()
        self._refresh_gdb_layer_color(actor_name, hex_color, color_dot_label)
        # Update the color button background too
        if color_button is not None:
            color_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    border: 1px solid #555555;
                    border-radius: 3px;
                    font-size: 10px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    border-color: #888888;
                }}
            """)

    def _refresh_gdb_layer_color(self, actor_name, new_color, color_dot_label=None):
        """Update a GDB layer's point color in both the data store and the 3D viewer."""
        layer = self.gdb_layers.get(actor_name)
        if layer is None:
            return
        layer["color"] = new_color
        layer["color_name"] = new_color  # store hex as name for simplicity

        if color_dot_label is not None:
            color_dot_label.setStyleSheet(f"color: {new_color}; font-size: 14px; font-weight: bold;")

        if self.plotter and layer.get("visible", True):
            try:
                self.plotter.add_points(
                    pv.PolyData(layer["coords"]),
                    color=new_color,
                    point_size=layer["point_size"],
                    render_points_as_spheres=layer["render_spheres"],
                    name=actor_name,
                    reset_camera=False,
                )
                self._set_actor_pickable(actor_name, self.gdb_pick_mode)
                # Re-apply labels with updated actor if they were visible
                if layer.get("label_visible") and layer.get("label_field"):
                    self._refresh_gdb_labels(actor_name)
                self.plotter.update()
            except Exception as e:
                self.log_to_console(f"⚠️ Failed to update GDB layer color: {e}")

    def _refresh_gdb_labels(self, actor_name):
        """Add or update point labels for a GDB layer based on the selected label field."""
        layer = self.gdb_layers.get(actor_name)
        if layer is None:
            return
        label_field = layer.get("label_field")
        gdf = layer.get("gdf")
        coords = layer.get("coords")
        label_actor = f"{actor_name}_labels"

        # Remove existing labels
        if self.plotter:
            try:
                self.plotter.remove_actor(label_actor)
            except Exception:
                pass

        if not label_field or gdf is None or coords is None:
            return
        if not layer.get("label_visible", False):
            return

        # Build label texts from the selected field
        try:
            if label_field not in gdf.columns:
                self.log_to_console(f"⚠️ Label field '{label_field}' not found in GDB layer attributes")
                return
            values = gdf[label_field].fillna("").astype(str).to_numpy()
            labels = [str(v) for v in values]

            if self.plotter:
                self.plotter.add_point_labels(
                    pv.PolyData(coords),
                    labels,
                    font_size=9,
                    text_color="white",
                    point_size=2,
                    always_visible=True,
                    name=label_actor,
                )
                self.plotter.update()
            self.log_to_console(f"🏷️  {len(labels)} labels applied to '{layer.get('layer_name')}' (field: {label_field})")
        except Exception as e:
            self.log_to_console(f"⚠️ Failed to add GDB labels: {e}")


    def update_tree_colors(self, color_field, preserve_camera=True):
        """Update the coloring of the currently visualized tree."""
        if self.current_tree_points is None or self.current_tree_id is None or not self.plotter or not self.las_data or self.current_mask is None:
            print("Warning: No tree data available for coloring")
            return

        # Save current camera state so recoloring preserves zoom & camera position
        camera_state = None
        if preserve_camera and self.plotter and hasattr(self.plotter, 'camera') and self.plotter.camera:
            try:
                camera_state = (
                    self.plotter.camera.position,
                    self.plotter.camera.focal_point,
                    self.plotter.camera.up,
                    self.plotter.camera.view_angle,
                    self.plotter.camera.clipping_range
                )
            except Exception:
                camera_state = None

        try:
            if color_field == "Default (green)":
                # Use default green color
                self.plotter.clear()
                self._restore_gdb_layers()
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, color='#4CAF50', point_size=2, render_points_as_spheres=False, reset_camera=False, name='tree_point_cloud')
            elif color_field == "RGB (red, green, blue)":
                # Color by RGB values
                print(f"Coloring by RGB values")
                self.plotter.clear()
                self._restore_gdb_layers()
                
                # Extract RGB values from the current tree points
                available_fields = list(self.las_data.point_format.dimension_names)
                if 'red' in available_fields and 'green' in available_fields and 'blue' in available_fields:
                    # Get RGB values for the current tree(s)
                    all_rgb_values = []
                    if self.all_masks is not None:
                        # Multiple trees selected - use all_masks.
                        # Convert the full RGB arrays once, then slice per mask.
                        red_full = np.asarray(self.las_data['red'])
                        green_full = np.asarray(self.las_data['green'])
                        blue_full = np.asarray(self.las_data['blue'])
                        for mask in self.all_masks:
                            red_vals = red_full[mask]
                            green_vals = green_full[mask]
                            blue_vals = blue_full[mask]
                            
                            # Normalize RGB to 0-1 range if they're in 0-65535 range (uint16)
                            if len(red_vals) > 0 and np.max(red_vals) > 1:
                                red_vals = red_vals / 65535.0
                                green_vals = green_vals / 65535.0
                                blue_vals = blue_vals / 65535.0
                            
                            rgb_colors = np.column_stack([red_vals, green_vals, blue_vals])
                            all_rgb_values.append(rgb_colors)
                        
                        rgb_colors = np.vstack(all_rgb_values)
                    else:
                        # Single tree - use current_mask
                        red_vals = np.array(self.las_data['red'])[self.current_mask]
                        green_vals = np.array(self.las_data['green'])[self.current_mask]
                        blue_vals = np.array(self.las_data['blue'])[self.current_mask]
                        
                        # Normalize RGB to 0-1 range if they're in 0-65535 range (uint16)
                        if np.max(red_vals) > 1:
                            red_vals = red_vals / 65535.0
                            green_vals = green_vals / 65535.0
                            blue_vals = blue_vals / 65535.0
                        
                        rgb_colors = np.column_stack([red_vals, green_vals, blue_vals])
                    
                    # Create point cloud and color by RGB
                    point_cloud = pv.PolyData(self.current_tree_points)
                    point_cloud['rgb'] = rgb_colors
                    
                    # Use direct RGB coloring (rgb=True uses the 'rgb' scalar field)
                    self.plotter.add_points(point_cloud, scalars='rgb', rgb=True, point_size=2, render_points_as_spheres=False, reset_camera=False, name='tree_point_cloud')
                    print(f"RGB coloring applied to {len(self.current_tree_points)} points")
                else:
                    print(f"Warning: RGB fields not found. Available fields: {available_fields}")
                    QMessageBox.warning(self, "Warning", "RGB fields (red, green, blue) not found in point cloud")
                    return
            else:
                # Color by the selected scalar field
                try:
                    # Check if we need to recalculate color values
                    if self.current_color_field != color_field or self.current_color_values is None:
                        if self.all_masks is not None:
                            color_full = np.asarray(self.las_data[color_field])
                            all_color_values = [color_full[mask] for mask in self.all_masks]
                            self.current_color_values = np.concatenate(all_color_values)
                            self.current_color_field = color_field
                        else:
                            # Fallback
                            self.current_color_values = np.array(self.las_data[color_field])[self.current_mask]

                    color_values = self.current_color_values
                    
                    # Special handling for ITC field - map to 9 cycling colors
                    if color_field == 'itc':
                        # Map ITC values to color indices 0-8 (9 colors total)
                        color_indices = (color_values - 1) % 9  # Subtract 1 since ITC starts from 1, then modulo 9
                        color_values = color_indices
                        print(f"Coloring by ITC with 9 cycling colors, {len(color_values)} values")
                    else:
                        print(f"Coloring by field '{color_field}' with {len(color_values)} values, range: {np.min(color_values):.3f} - {np.max(color_values):.3f}")

                    self.plotter.clear()
                    self._restore_gdb_layers()
                    point_cloud = pv.PolyData(self.current_tree_points)
                    
                    if color_field == 'itc':
                        # Use a colormap with 9 distinct colors for ITC
                        self.plotter.add_points(point_cloud, scalars=color_values, point_size=2, render_points_as_spheres=False, 
                                              cmap='tab10', n_colors=9, clim=[0, 8], reset_camera=False, name='tree_point_cloud')
                    else:
                        self.plotter.add_points(point_cloud, scalars=color_values, point_size=2, render_points_as_spheres=False, cmap='cividis', reset_camera=False, name='tree_point_cloud')
                        
                except Exception as e:
                    print(f"Error coloring by field '{color_field}': {str(e)}")
                    QMessageBox.warning(self, "Warning", f"Failed to color by field '{color_field}': {str(e)}")
                    return

            # Apply current pick mode (tree vs GDB) to the freshly added actors
            self._apply_pick_mode()

            # Restore camera position and zoom level if preserving view, otherwise reset to frame tree
            if preserve_camera and camera_state is not None:
                try:
                    self.plotter.camera.position = camera_state[0]
                    self.plotter.camera.focal_point = camera_state[1]
                    self.plotter.camera.up = camera_state[2]
                    self.plotter.camera.view_angle = camera_state[3]
                    self.plotter.camera.clipping_range = camera_state[4]
                except Exception:
                    self.plotter.reset_camera()
            else:
                self.plotter.reset_camera()

            num_points = len(self.current_tree_points)
            try:
                self.plotter.remove_actor('tree_info_text')
                self.plotter.remove_actor('itc_instruction_text')
            except Exception:
                pass

            self.plotter.add_text(
                f"Click on points to see ITC values\nTree ID: {self.current_tree_id} ({num_points:,} points) - Color: {color_field}",
                position='lower_left',
                font_size=11,
                color='#FFFFFF',
                name='tree_info_text'
            )
            # Print trunk/branch summary table to GUI console and python console
            try:
                # Prefer trunk_volume_summary if present
                if hasattr(self, 'trunk_volume_summary') and self.trunk_volume_summary:
                    overall_total = sum(t['total_volume'] for t in self.trunk_volume_summary.values())
                    total_trunks = len(self.trunk_volume_summary)
                    header = f"{'Trunk':<8} {'Volume_m3':>12} {'#Branches':>10} {'#Points':>10}"
                    self.log_to_console('\n' + header)
                    print(header)
                    self.log_to_console('-' * len(header))
                    print('-' * len(header))
                    for tid in sorted(self.trunk_volume_summary.keys()):
                        t = self.trunk_volume_summary[tid]
                        row = f"{tid:<8} {t['total_volume']:12.4f} {t['num_branches']:10d} {t['total_points']:10d}"
                        self.log_to_console(row)
                        print(row)
                    footer = f"Total trunks: {total_trunks} | Overall volume: {overall_total:.4f} m³"
                    self.log_to_console(footer)
                    print(footer)
                else:
                    # Aggregate from accumulated_volume_sections if trunk_summary missing
                    trunk_agg = {}
                    for sec in self.accumulated_volume_sections:
                        tid = sec.get('trunk_id', None)
                        if tid is None:
                            tid = -1
                        rec = trunk_agg.setdefault(tid, {'total_volume': 0.0, 'num_branches': 0, 'total_points': 0})
                        rec['total_volume'] += float(sec.get('volume', 0.0) or 0.0)
                        rec['num_branches'] += 1
                        rec['total_points'] += len(sec.get('points', []))

                    header = f"{'Trunk':<8} {'Volume_m3':>12} {'#Sections':>10} {'#Points':>10}"
                    self.log_to_console('\n' + header)
                    print(header)
                    self.log_to_console('-' * len(header))
                    print('-' * len(header))
                    for tid in sorted(trunk_agg.keys()):
                        rec = trunk_agg[tid]
                        row = f"{tid:<8} {rec['total_volume']:12.4f} {rec['num_branches']:10d} {rec['total_points']:10d}"
                        self.log_to_console(row)
                        print(row)
                    overall = sum(r['total_volume'] for r in trunk_agg.values())
                    footer = f"Total trunks (keys): {len(trunk_agg)} | Overall volume: {overall:.4f} m³"
                    self.log_to_console(footer)
                    print(footer)
            except Exception as e:
                self.log_to_console(f"⚠️ Error building trunk summary table: {e}")
                print(f"Error building trunk summary table: {e}")

            self.plotter.update()
        except Exception as e:
            print(f"Error in update_tree_colors: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to update tree colors: {str(e)}")

    def visualize_tree(self):
        """Visualize the selected trees using PyVista."""
        if self.las_data is None:
            print("Error: No LAS file loaded")
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if not self.plotter:
            print("Error: 3D viewer not initialized")
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        selected_tree_ids = self.get_selected_tree_ids()
        if not selected_tree_ids:
            print("Warning: No tree IDs selected")
            QMessageBox.warning(self, "Warning", "Please select one or more tree IDs from the list.")
            return

        try:
            # Validate selected tree IDs
            invalid_ids = [tid for tid in selected_tree_ids if tid not in self.unique_itc_values]
            if invalid_ids:
                print(f"Warning: Invalid tree IDs selected: {invalid_ids}")
                QMessageBox.warning(self, "Warning", f"Invalid tree IDs selected: {invalid_ids}")
                return

        except ValueError as e:
            print(f"Error validating tree IDs: {str(e)}")
            QMessageBox.warning(self, "Warning", "Invalid tree IDs selected.")
            return

        try:
            # Clear accumulated volume results when visualizing new trees
            self.clear_accumulated_volume()
            # Reset any prior selection/analysis state to avoid index mismatches
            try:
                self.selected_point_indices = None
            except Exception:
                pass
            try:
                self.radius_selection_active = False
                self.radius_selection_center = None
                if hasattr(self, 'radius_export_button'):
                    self.radius_export_button.setText("Pick & Export Radius")
            except Exception:
                pass
            try:
                self.branch_assignment = None
            except Exception:
                pass
            try:
                self.trunk_assignment = None
            except Exception:
                pass
            try:
                self.last_analyzed_points = None
            except Exception:
                pass

            # Extract and merge points for all selected trees
            # NOTE: Convert coordinate / attribute arrays ONCE up-front instead of
            # inside the per-tree loop.  laspy's scaled x/y/z properties return a
            # freshly computed array on every access, so converting them per-tree
            # made "Select All" O(num_trees * num_points) and very slow.
            all_points = []
            all_masks = []
            all_tree_ids = []  # tree id for each block appended to all_points
            itc_values = np.asarray(self.las_data['itc'])
            xs = np.asarray(self.las_data.x)
            ys = np.asarray(self.las_data.y)
            zs = np.asarray(self.las_data.z)

            use_treefilter = (
                self.filter_checkbox.isChecked()
                and 'treefilter' in self.las_data.point_format.dimension_names
            )
            treefilter_keep = (
                np.asarray(self.las_data['treefilter']) == 2
            ) if use_treefilter else None
            
            for tree_id in selected_tree_ids:
                mask = itc_values == tree_id

                # Apply treefilter if enabled
                if treefilter_keep is not None:
                    mask = mask & treefilter_keep

                if np.any(mask):
                    points = np.column_stack((xs[mask], ys[mask], zs[mask]))
                    all_points.append(points)
                    all_masks.append(mask)
                    all_tree_ids.append(tree_id)

            if not all_points:
                print(f"Warning: No points found for selected tree IDs: {selected_tree_ids}")
                QMessageBox.warning(self, "Warning", f"No points found for selected tree IDs: {selected_tree_ids}")
                return

            # Merge all points
            merged_points = np.vstack(all_points)
            merged_mask = np.concatenate(all_masks)

            print(f"Visualizing {len(selected_tree_ids)} trees with {len(merged_points)} total points")

            # Create tree ID mapping for each point in merged_points
            # (vectorized; also robust to selected trees that had no points)
            if all_points:
                self.current_tree_ids = np.concatenate([
                    np.full(len(points), tree_id, dtype=itc_values.dtype)
                    for tree_id, points in zip(all_tree_ids, all_points)
                ])
            else:
                self.current_tree_ids = np.array([], dtype=itc_values.dtype)

            # Calculate bounding box and log dimensions
            if len(merged_points) > 0:
                bounds = [
                    np.min(merged_points[:, 0]), np.max(merged_points[:, 0]),  # X bounds
                    np.min(merged_points[:, 1]), np.max(merged_points[:, 1]),  # Y bounds
                    np.min(merged_points[:, 2]), np.max(merged_points[:, 2])   # Z bounds
                ]
                bottom_z = bounds[4]  # Min Z (bottom)
                bounding_box_height = bounds[5] - bounds[4]  # Height of bounding box
                
                # Calculate tree height from ground level (using tree-specific ground detection)
                tree_z_values = merged_points[:, 2]
                ground_level = np.min(tree_z_values)
                tree_height = bounds[5] - ground_level  # Tree height from ground to top
                # Store the height for the currently visualized tree so it can be
                # exported with trunk metrics.
                self.current_tree_height = float(tree_height)
                self.current_tree_ground_z = float(ground_level)
                
                print(f"📦 Bounding Box - Bottom Z: {bottom_z:.2f}m, Bounding Box Height: {bounding_box_height:.2f}m")
                print(f"🌳 Tree Height (from ground): {tree_height:.2f}m (ground level: {ground_level:.2f}m)")
                print(f"📐 Dimensions: {bounds[1]-bounds[0]:.2f}m W × {bounds[3]-bounds[2]:.2f}m L × {bounding_box_height:.2f}m H")

            # Store current tree data for recoloring
            self.current_tree_points = merged_points
            # Store first tree ID for analysis (used when calling AI analysis)
            self.current_tree_id = selected_tree_ids[0] if selected_tree_ids else None
            self.current_mask = merged_mask
            self.all_masks = all_masks

            # Collect color values for current visualization
            color_field = self.color_combo.currentText()
            if color_field == "RGB (red, green, blue)":
                # Don't pre-load RGB values - handle in update_tree_colors
                self.current_color_values = None
                self.current_color_field = color_field
            elif color_field != "Default (green)":
                color_full = np.asarray(self.las_data[color_field])
                all_color_values = [color_full[mask] for mask in all_masks]
                self.current_color_values = np.concatenate(all_color_values)
                self.current_color_field = color_field
            else:
                self.current_color_values = None
                self.current_color_field = color_field

            # Collect ITC values for point picking (itc_values already loaded above)
            all_itc_values = [itc_values[mask] for mask in all_masks]
            self.current_itc_values = np.concatenate(all_itc_values)

            # Visualize with current color field (reset camera to frame tree)
            self.update_tree_colors(color_field, preserve_camera=False)

            # Add bounding box visualization
            if len(merged_points) > 0:
                bounds = [
                    np.min(merged_points[:, 0]), np.max(merged_points[:, 0]),
                    np.min(merged_points[:, 1]), np.max(merged_points[:, 1]),
                    np.min(merged_points[:, 2]), np.max(merged_points[:, 2])
                ]
                bounding_box = pv.Cube(bounds=bounds)
                self.plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                                    name='tree_bounding_box', label='Tree Bounding Box')
                self._set_actor_pickable('tree_bounding_box', False)
                # Display bounding box height as overlay text and a 3D label at the top center
                try:
                    bottom_z = bounds[4]
                    top_z = bounds[5]
                    bounding_box_height = top_z - bottom_z
                    # Add overlay text (upper right)
                    self.plotter.add_text(f"BBox H: {bounding_box_height:.2f} m", position='upper_right', font_size=12, color='#FFFFFF')
                    # Add a 3D label at the top-center of the bounding box
                    top_center = ((bounds[0] + bounds[1]) / 2.0, (bounds[2] + bounds[3]) / 2.0, top_z)
                    try:
                        self.plotter.add_point_labels(np.array([top_center]), [f"{bounding_box_height:.2f} m"], point_size=0, font_size=10, text_color='yellow', always_visible=True)
                    except Exception:
                        # Fallback: use add_point_labels without numpy array conversion if needed
                        self.plotter.add_point_labels([top_center], [f"{bounding_box_height:.2f} m"], point_size=0, font_size=10, text_color='yellow', always_visible=True)
                except Exception as e:
                    print(f"Warning: Failed to add bounding box height label: {e}")

                # Draw DBH marker: a horizontal dashed line at the configured reference height above ground across the bounding box
                try:
                    dbh_ref_h = getattr(self, 'dbh_reference_height', 1.3)
                    dbh_z = ground_level + dbh_ref_h
                    mid_y = (bounds[2] + bounds[3]) / 2.0  # Center Y of bounding box
                    # Horizontal line across the X extent of the bounding box at DBH height
                    dbh_line_start = (bounds[0], mid_y, dbh_z)
                    dbh_line_end = (bounds[1], mid_y, dbh_z)
                    dbh_line = pv.Line(dbh_line_start, dbh_line_end)
                    self.plotter.add_mesh(dbh_line, color='orange', line_width=3,
                                        name='dbh_marker_line', label=f'DBH @ {dbh_ref_h:.1f}m')
                    self._set_actor_pickable('dbh_marker_line', False)
                    # Label at the midpoint of the DBH line
                    dbh_mid = ((bounds[0] + bounds[1]) / 2.0, mid_y, dbh_z)
                    self.plotter.add_point_labels([dbh_mid], [f"DBH ({dbh_ref_h:.1f}m)"],
                                                point_size=0, font_size=9, text_color='orange',
                                                always_visible=True,
                                                name='dbh_marker_label')
                except Exception as e:
                    print(f"Warning: Failed to add DBH marker: {e}")

            # Enable analyze button for tree analysis
            self.analyze_button.setEnabled(True)

            # Enable polygon selection buttons
            self.draw_polygon_button.setEnabled(True)
            self.select_all_points_button.setEnabled(True)
            self.radius_export_button.setEnabled(True)

            # Check volume folder for existing volume data if enabled (after visualization is complete)
            if (hasattr(self, 'volume_folder_checkbox') and 
                hasattr(self, 'volume_folder_path') and
                self.volume_folder_checkbox.isChecked() and 
                self.volume_folder_path and 
                isinstance(self.volume_folder_path, str)):
                self._refresh_tree_list_colors()

        except Exception as e:
            print(f"Error in visualize_tree: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to visualize trees: {str(e)}")

    def visualize_trunk(self):
        """Visualize the trunks of the selected trees using PyVista (stemcls != 1)."""
        if self.las_data is None:
            print("Error: No LAS file loaded")
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if not self.plotter:
            print("Error: 3D viewer not initialized")
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        selected_tree_ids = self.get_selected_tree_ids()
        if not selected_tree_ids:
            print("Warning: No tree IDs selected")
            QMessageBox.warning(self, "Warning", "Please select one or more tree IDs from the list.")
            return

        try:
            # Validate selected tree IDs
            invalid_ids = [tid for tid in selected_tree_ids if tid not in self.unique_itc_values]
            if invalid_ids:
                print(f"Warning: Invalid tree IDs selected: {invalid_ids}")
                QMessageBox.warning(self, "Warning", f"Invalid tree IDs selected: {invalid_ids}")
                return

        except ValueError as e:
            print(f"Error validating tree IDs: {str(e)}")
            QMessageBox.warning(self, "Warning", "Invalid tree IDs selected.")
            return

        # Check if stemcls field exists
        if 'stemcls' not in self.las_data.point_format.dimension_names:
            print("Warning: No 'stemcls' scalar field found")
            QMessageBox.warning(self, "Warning", "No 'stemcls' scalar field found in the LAS file.")
            return

        try:
            # Extract and merge trunk points for all selected trees
            all_points = []
            all_masks = []
            itc_values = np.array(self.las_data['itc'])
            stemcls_values = np.array(self.las_data['stemcls'])
            
            for tree_id in selected_tree_ids:
                mask = (itc_values == tree_id) & (stemcls_values != 1)

                # Apply treefilter if enabled
                if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                    treefilter_values = np.array(self.las_data['treefilter'])
                    mask = mask & (treefilter_values == 2)

                if np.any(mask):
                    points = np.column_stack([
                        np.array(self.las_data.x)[mask],
                        np.array(self.las_data.y)[mask],
                        np.array(self.las_data.z)[mask]
                    ])
                    all_points.append(points)
                    all_masks.append(mask)

            if not all_points:
                print(f"Warning: No trunk points found for selected tree IDs: {selected_tree_ids}")
                QMessageBox.warning(self, "Warning", f"No trunk points found for selected tree IDs: {selected_tree_ids}")
                return

            # Merge all points
            merged_points = np.vstack(all_points)
            merged_mask = np.concatenate(all_masks)

            print(f"Visualizing trunks of {len(selected_tree_ids)} trees with {len(merged_points)} total points")

            # Calculate bounding box height and set max height input (use the tallest tree)
            z_coords = merged_points[:, 2]  # Z coordinates
            trunk_height = np.max(z_coords) - np.min(z_coords)
            self.max_height_input.setText(f"{trunk_height:.2f}")

            # Store current tree data for recoloring
            self.current_tree_points = merged_points
            self.current_tree_id = f"Multiple Trunks ({', '.join(map(str, selected_tree_ids))})"
            self.current_mask = merged_mask
            self.all_masks = all_masks

            # Reset any prior selection/analysis state to avoid using indices from previous visualizations
            try:
                self.selected_point_indices = None
            except Exception:
                pass
            try:
                self.radius_selection_active = False
                self.radius_selection_center = None
                if hasattr(self, 'radius_export_button'):
                    self.radius_export_button.setText("Pick & Export Radius")
            except Exception:
                pass
            try:
                self.branch_assignment = None
            except Exception:
                pass
            try:
                self.trunk_assignment = None
            except Exception:
                pass
            try:
                self.last_analyzed_points = None
            except Exception:
                pass

            # For trunk visualization, use default green
            self.current_color_values = None
            self.current_color_field = "Default (green)"

            # Collect ITC values for point picking
            all_itc_values = []
            for mask in all_masks:
                itc_vals = np.array(self.las_data['itc'])[mask]
                all_itc_values.append(itc_vals)
            self.current_itc_values = np.concatenate(all_itc_values)

            # Switch to default green for trunk visualization
            self.color_combo.setCurrentText("Default (green)")
            # Visualize with current color field (reset camera to frame tree)
            self.update_tree_colors(self.color_combo.currentText(), preserve_camera=False)

            # Enable split detection button for merged trunks
            self.analyze_button.setEnabled(True)
            self.detect_branches_button.setEnabled(True)
            self.detect_trunks_button.setEnabled(True)  # Enable trunk detection after trunk visualization

            # Enable polygon selection buttons
            self.draw_polygon_button.setEnabled(True)
            self.select_all_points_button.setEnabled(True)
            self.radius_export_button.setEnabled(True)

            # Reset any prior selection/analysis state to avoid index mismatches
            try:
                self.selected_point_indices = None
            except Exception:
                pass
            try:
                self.branch_assignment = None
            except Exception:
                pass
            try:
                self.trunk_assignment = None
            except Exception:
                pass
            try:
                self.last_analyzed_points = None
            except Exception:
                pass

        except Exception as e:
            print(f"Error in visualize_trunk: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to visualize trunks: {str(e)}")



    def create_tree_crown_polygon(self):
        """Create a 2D polygon from all tree points projected to XY plane."""
        if self.las_data is None:
            print("Error: No LAS file loaded")
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if not self.plotter:
            print("Error: 3D viewer not initialized")
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        selected_tree_ids = self.get_selected_tree_ids()
        if not selected_tree_ids:
            print("Warning: No tree IDs selected")
            QMessageBox.warning(self, "Warning", "Please select one or more tree IDs from the list.")
            return

        try:
            # Validate selected tree IDs
            invalid_ids = [tid for tid in selected_tree_ids if tid not in self.unique_itc_values]
            if invalid_ids:
                print(f"Warning: Invalid tree IDs selected: {invalid_ids}")
                QMessageBox.warning(self, "Warning", f"Invalid tree IDs selected: {invalid_ids}")
                return

            # Extract and merge ALL points for all selected trees (no height filtering)
            all_points = []
            all_masks = []
            itc_values = np.array(self.las_data['itc'])

            for tree_id in selected_tree_ids:
                mask = (itc_values == tree_id)

                # Apply treefilter if enabled
                if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                    treefilter_values = np.array(self.las_data['treefilter'])
                    mask = mask & (treefilter_values == 2)

                if np.any(mask):
                    points = np.column_stack([
                        np.array(self.las_data.x)[mask],
                        np.array(self.las_data.y)[mask],
                        np.array(self.las_data.z)[mask]
                    ])
                    all_points.append(points)
                    all_masks.append(mask)

            if not all_points:
                print(f"Warning: No points found for selected tree IDs: {selected_tree_ids}")
                QMessageBox.warning(self, "Warning", f"No points found for selected tree IDs: {selected_tree_ids}")
                return

            # Merge all points
            merged_points = np.vstack(all_points)
            merged_mask = np.concatenate(all_masks)

            print(f"Creating crown polygon from {len(merged_points)} total points for trees: {selected_tree_ids}")

            # Project points to 2D (XY plane) - remove Z coordinate
            points_2d = merged_points[:, :2]  # Keep only X, Y coordinates

            # Debug: Check for valid points
            print(f"2D points shape: {points_2d.shape}")
            print(f"2D points range X: {np.min(points_2d[:, 0]):.2f} to {np.max(points_2d[:, 0]):.2f}")
            print(f"2D points range Y: {np.min(points_2d[:, 1]):.2f} to {np.max(points_2d[:, 1]):.2f}")

            # Create convex hull polygon from 2D points
            if len(points_2d) < 3:
                QMessageBox.warning(self, "Warning", "Need at least 3 points to create a polygon.")
                return

            # Check if points span enough area (not collinear)
            if len(points_2d) >= 3:
                # Calculate the area of the convex hull to check if points are collinear
                try:
                    from scipy.spatial import ConvexHull
                    temp_hull = ConvexHull(points_2d)
                    hull_area = temp_hull.volume  # For 2D, volume is actually area
                    print(f"Hull area: {hull_area}")
                    if hull_area < 1e-10:  # Very small area indicates collinear points
                        QMessageBox.warning(self, "Warning", "Points appear to be collinear or nearly collinear. Cannot create a meaningful polygon.")
                        return
                except Exception as area_check_error:
                    print(f"Could not compute hull area: {area_check_error}")
                    # Continue anyway, might still work

            from scipy.spatial import ConvexHull
            try:
                hull = ConvexHull(points_2d)
                hull_points_2d = points_2d[hull.vertices]

                print(f"Hull computed successfully with {len(hull_points_2d)} vertices")

                # Create closed polygon (repeat first point at end)
                polygon_points = np.vstack([hull_points_2d, hull_points_2d[0]])

                # Create PyVista polygon mesh - need 3D points, so add Z=0 (or use min Z from original points)
                import pyvista as pv
                # Use minimum Z value from original points for the polygon plane
                z_value = np.min(merged_points[:, 2])
                hull_points_3d = np.column_stack([hull_points_2d, np.full(len(hull_points_2d), z_value)])
                
                # Create polygon from hull points
                polygon_mesh = pv.PolyData(hull_points_3d)
                # Add the polygon face (single face connecting all vertices)
                faces = np.array([len(hull_points_3d)] + list(range(len(hull_points_3d))))
                polygon_mesh.faces = faces

                # Clear current view and show the polygon
                self.plotter.clear()
                self._restore_gdb_layers()

                # Add the polygon as a filled mesh
                self.plotter.add_mesh(polygon_mesh, color='green', opacity=0.3, show_edges=True, edge_color='darkgreen', line_width=2)

                # Add the original 3D points as reference
                point_cloud = pv.PolyData(merged_points)
                self.plotter.add_points(point_cloud, color='blue', point_size=2, opacity=0.6)

                # Add text info
                info_text = f"Tree Crown Polygon\nTrees: {', '.join(map(str, selected_tree_ids))}\nPoints: {len(merged_points)}\nHull vertices: {len(hull_points_2d)}"
                self.plotter.add_text(info_text, position='upper_left', font_size=10, color='white')

                self.plotter.reset_camera()

                # Store data for potential export
                self.current_tree_points = merged_points
                self.current_tree_id = f"Crown Polygon ({', '.join(map(str, selected_tree_ids))})"
                self.current_mask = merged_mask
                self.current_hull_points_2d = hull_points_2d
                self.current_polygon_tree_ids = selected_tree_ids

                QMessageBox.information(self, "Success", f"Created crown polygon from {len(merged_points)} points with {len(hull_points_2d)} vertices.")

            except Exception as hull_error:
                print(f"Error creating convex hull: {hull_error}")
                QMessageBox.warning(self, "Warning", f"Could not create polygon from points: {hull_error}")

        except Exception as e:
            print(f"Error in create_tree_crown_polygon: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to create tree crown polygon: {str(e)}")

    def refresh_color_combo_box(self):
        """Refresh the color combo box to include newly added scalar fields like DBH points."""
        if self.las_data is None:
            return

        try:
            # Get current selection
            current_selection = self.color_combo.currentText()

            # Temporarily disconnect the signal to avoid triggering update_tree_colors with empty field
            self.color_combo.currentTextChanged.disconnect(self.update_tree_colors)

            # Populate color field combo box with updated fields
            available_fields = list(self.las_data.point_format.dimension_names)
            color_fields = [field for field in available_fields
                           if field not in ['x', 'y', 'z']]  # Include itc for multiple tree coloring

            self.color_combo.clear()
            self.color_combo.addItem("Default (green)")
            for field in sorted(color_fields):
                self.color_combo.addItem(field)

            # Restore previous selection if it still exists
            if current_selection and current_selection != "Default (green)":
                index = self.color_combo.findText(current_selection)
                if index >= 0:
                    self.color_combo.setCurrentIndex(index)
                else:
                    # If previous selection no longer exists, select DBH points if available
                    dbh_index = self.color_combo.findText("dbh_points")
                    if dbh_index >= 0:
                        self.color_combo.setCurrentIndex(dbh_index)
                        self.log_to_console("🎨 Switched to 'dbh_points' coloring")

            # Reconnect the signal
            self.color_combo.currentTextChanged.connect(self.update_tree_colors)

            self.log_to_console("✅ Color options updated - 'dbh_points' now available for coloring")

        except Exception as e:
            # Make sure to reconnect the signal even if there's an error
            try:
                self.color_combo.currentTextChanged.connect(self.update_tree_colors)
            except:
                pass
            self.log_to_console(f"⚠️ Could not refresh color combo box: {str(e)}")

    def view_neighbors(self):
        """Find and visualize neighboring trees within the specified radius."""
        if self.las_data is None:
            print("Error: No LAS file loaded")
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        selected_tree_ids = self.get_selected_tree_ids()
        if not selected_tree_ids:
            print("Warning: No trees selected for neighbor search")
            QMessageBox.warning(self, "Warning", "Please select one or more trees first.")
            return

        try:
            radius = float(self.neighbor_radius_input.text())
            if radius <= 0 or radius > 1000:
                raise ValueError("Radius must be between 0.1 and 1000 meters")
        except ValueError as e:
            print(f"Error: Invalid radius value: {str(e)}")
            QMessageBox.warning(self, "Invalid Radius", f"Please enter a valid radius.\nError: {e}")
            return

        try:
            # Ensure centroids are pre-computed (lazy loading)
            if not self.tree_centroids_cache:
                print("Pre-computing tree centroids for neighbor search...")
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)  # Indeterminate progress
                self.precompute_tree_centroids()
                self.progress_bar.setVisible(False)
                print("Centroid pre-computation completed")

            # Calculate centroid of selected trees
            reference_centroid = self.calculate_trees_centroid(selected_tree_ids)
            if reference_centroid is None:
                print("Error: Could not calculate centroid of selected trees")
                QMessageBox.warning(self, "Error", "Could not calculate centroid of selected trees.")
                return

            print(f"Reference centroid: ({reference_centroid[0]:.2f}, {reference_centroid[1]:.2f})")

            # Find neighboring trees using KDTree for fast spatial queries
            neighbor_tree_ids = list(selected_tree_ids)  # Start with selected trees
            
            # Get centroids for all trees (excluding selected ones)
            all_centroids = []
            candidate_tree_ids = []
            
            for tree_id in self.unique_itc_values:
                if tree_id not in selected_tree_ids and tree_id in self.tree_centroids_cache:
                    all_centroids.append(self.tree_centroids_cache[tree_id])
                    candidate_tree_ids.append(tree_id)
            
            if self.centroids_kdtree is not None and all_centroids:
                # Use KDTree for efficient radius search
                indices = self.centroids_kdtree.query_ball_point(reference_centroid, radius)
                # Map KDTree row indices back to tree IDs using the ordering the
                # KDTree was built from (NOT candidate_tree_ids — the KDTree is
                # built from the whole cache, so the two orders differ).
                kdtree_ids = getattr(self, 'centroids_kdtree_tree_ids', None) or list(self.tree_centroids_cache.keys())
                for _i in indices:
                    if 0 <= _i < len(kdtree_ids):
                        _tid = kdtree_ids[_i]
                        if _tid not in neighbor_tree_ids:
                            neighbor_tree_ids.append(_tid)
            elif all_centroids:
                # Fallback to vectorized distance calculation if KDTree not available
                centroids_array = np.array(all_centroids)
                reference_centroid_array = np.array([reference_centroid])
                
                # Calculate distances using scipy's cdist for efficiency
                distances = cdist(reference_centroid_array, centroids_array)[0]
                
                # Find trees within radius
                within_radius = distances <= radius
                neighbor_tree_ids.extend([candidate_tree_ids[i] for i in np.where(within_radius)[0]])
            
            # Fallback for any trees not in cache (shouldn't happen with precomputation)
            for tree_id in self.unique_itc_values:
                if tree_id in selected_tree_ids or tree_id in neighbor_tree_ids:
                    continue
                    
                # Calculate centroid (fallback)
                tree_centroid = self.calculate_tree_centroid(tree_id)
                if tree_centroid is None:
                    continue

                # Check distance
                distance = np.sqrt((tree_centroid[0] - reference_centroid[0])**2 + 
                                 (tree_centroid[1] - reference_centroid[1])**2)

                if distance <= radius:
                    neighbor_tree_ids.append(tree_id)

            if len(neighbor_tree_ids) == len(selected_tree_ids):
                print(f"Warning: No additional neighbors found within {radius}m radius")
                QMessageBox.information(self, "No Neighbors", f"No additional trees found within {radius}m radius.")
                return

            print(f"Found {len(neighbor_tree_ids)} trees within {radius}m radius (including {len(selected_tree_ids)} selected)")

            # Select the neighbor trees in the list
            self.tree_list.clearSelection()
            for i in range(self.tree_list.count()):
                item = self.tree_list.item(i)
                try:
                    tree_id = int(item.text())
                    if tree_id in neighbor_tree_ids:
                        item.setSelected(True)
                except ValueError:
                    continue

            # Trigger visualization
            self.visualize_tree()

        except Exception as e:
            print(f"Error in view_neighbors: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to find neighbors: {str(e)}")

    def calculate_trees_centroid(self, tree_ids):
        """Calculate the centroid of multiple trees combined."""
        all_points = []
        itc_values = np.array(self.las_data['itc'])

        for tree_id in tree_ids:
            mask = itc_values == tree_id

            # Apply treefilter if enabled
            if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                treefilter_values = np.array(self.las_data['treefilter'])
                mask = mask & (treefilter_values == 2)

            if np.any(mask):
                points = np.column_stack([
                    np.array(self.las_data.x)[mask],
                    np.array(self.las_data.y)[mask],
                    np.array(self.las_data.z)[mask]
                ])
                all_points.append(points)

        if not all_points:
            return None

        # Calculate centroid of all points combined
        merged_points = np.vstack(all_points)
        centroid = np.mean(merged_points, axis=0)
        return centroid[:2]  # Return only X, Y coordinates

    def calculate_tree_centroid(self, tree_id):
        """Calculate the centroid of a single tree."""
        itc_values = np.array(self.las_data['itc'])
        mask = itc_values == tree_id

        # Apply treefilter if enabled
        if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
            treefilter_values = np.array(self.las_data['treefilter'])
            mask = mask & (treefilter_values == 2)

        if not np.any(mask):
            return None

        points = np.column_stack([
            np.array(self.las_data.x)[mask],
            np.array(self.las_data.y)[mask],
            np.array(self.las_data.z)[mask]
        ])

        centroid = np.mean(points, axis=0)
        return centroid[:2]  # Return only X, Y coordinates

        print(f"Pre-computed centroids for {len(self.tree_centroids_cache)} trees")

    def compute_single_centroid(self, tree_id, itc_values, x_coords, y_coords, z_coords, filter_mask=None):
        """Compute centroid for a single tree (used for parallel processing)."""
        mask = itc_values == tree_id
        if filter_mask is not None:
            mask = mask & filter_mask
            
        if not np.any(mask):
            return tree_id, None
            
        points = np.column_stack([x_coords[mask], y_coords[mask], z_coords[mask]])
        centroid = np.mean(points, axis=0)
        return tree_id, centroid[:2]

    def precompute_tree_centroids(self):
        """Pre-compute centroids for all trees to speed up neighbor calculations."""
        if self.las_data is None or len(self.unique_itc_values) == 0:
            return
            
        self.tree_centroids_cache = {}
        itc_values = np.array(self.las_data['itc'])
        x_coords = np.array(self.las_data.x)
        y_coords = np.array(self.las_data.y)
        z_coords = np.array(self.las_data.z)
        
        # Apply treefilter if enabled
        filter_mask = None
        if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
            treefilter_values = np.array(self.las_data['treefilter'])
            filter_mask = treefilter_values == 2
        
        # Use parallel processing for centroid computation
        num_workers = min(multiprocessing.cpu_count(), len(self.unique_itc_values))
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all centroid computation tasks
            future_to_tree = {
                executor.submit(self.compute_single_centroid, tree_id, itc_values, x_coords, y_coords, z_coords, filter_mask): tree_id 
                for tree_id in self.unique_itc_values
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_tree):
                tree_id = future_to_tree[future]
                try:
                    tid, centroid = future.result()
                    if centroid is not None:
                        self.tree_centroids_cache[tid] = centroid
                except Exception as exc:
                    print(f'Tree {tree_id} generated an exception: {exc}')
        
        # Build KDTree for fast spatial queries
        if self.tree_centroids_cache:
            centroids_array = np.array(list(self.tree_centroids_cache.values()))
            self.centroids_kdtree = KDTree(centroids_array)
            # Record the tree IDs in the SAME row order the KDTree was built
            # from, so query indices can be mapped back to tree IDs correctly.
            self.centroids_kdtree_tree_ids = list(self.tree_centroids_cache.keys())
            print(f"Built KDTree with {len(centroids_array)} centroids")
        
        print(f"Pre-computed centroids for {len(self.tree_centroids_cache)} trees using {num_workers} parallel workers")

    def on_filter_changed(self):
        """Clear centroids cache when filter checkbox changes (will be recomputed lazily)."""
        if self.las_data is not None and len(self.unique_itc_values) > 0:
            self.tree_centroids_cache = {}
            self.centroids_kdtree = None
            self.centroids_kdtree_tree_ids = None
            print("Cleared centroids cache due to filter change (will be recomputed on next neighbor search)")

    def calculate_tree_centroid(self, tree_id):
        """Calculate the centroid of a single tree (now uses cache if available)."""
        # Check cache first
        if tree_id in self.tree_centroids_cache:
            return self.tree_centroids_cache[tree_id]
            
        # Fallback to original calculation
        itc_values = np.array(self.las_data['itc'])
        mask = itc_values == tree_id

        # Apply treefilter if enabled
        if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
            treefilter_values = np.array(self.las_data['treefilter'])
            mask = mask & (treefilter_values == 2)

        if not np.any(mask):
            return None

        points = np.column_stack([
            np.array(self.las_data.x)[mask],
            np.array(self.las_data.y)[mask],
            np.array(self.las_data.z)[mask]
        ])

        centroid = np.mean(points, axis=0)
        return centroid[:2]  # Return only X, Y coordinates

    def select_all_trees(self):
        """Select all trees in the list."""
        for i in range(self.tree_list.count()):
            self.tree_list.item(i).setSelected(True)

    def clear_tree_selection(self):
        """Clear all tree selections."""
        self.tree_list.clearSelection()

    def get_selected_tree_ids(self):
        """Get list of selected tree IDs."""
        selected_items = self.tree_list.selectedItems()
        tree_ids = []
        for item in selected_items:
            try:
                tree_ids.append(int(item.text()))
            except ValueError:
                continue
        return tree_ids

    def on_draw_polygon_button_clicked(self):
        """Handle draw polygon button click - toggles between start and cancel."""
        if self.polygon_selection_active:
            self.cancel_polygon_selection()
        else:
            self.start_polygon_selection()

    def on_radius_export_button_clicked(self):
        """Toggle radius-based point picking and export mode."""
        if self.radius_selection_active:
            self.cancel_radius_selection()
        else:
            self.start_radius_selection()

    def start_radius_selection(self):
        """Start radius-based point selection mode."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            QMessageBox.warning(self, "Warning", "No tree points available for selection.")
            return

        if not self.plotter:
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        self.radius_selection_active = True
        self.radius_selection_center = None
        self.radius_export_button.setText("Cancel Radius")
        radius_value = float(self.radius_value_input.value())
        self.log_to_console(
            f"Radius export mode enabled. Click a point in the 3D view to select points within {radius_value:.2f} m and export them."
        )

    def cancel_radius_selection(self, log_message=True):
        """Cancel radius-based point selection mode."""
        self.radius_selection_active = False
        self.radius_selection_center = None
        if hasattr(self, 'radius_export_button'):
            self.radius_export_button.setText("Pick & Export Radius")
        if log_message:
            self.log_to_console("Radius export mode cancelled.")

    def _resolve_picked_point(self, picked_info):
        """Resolve the picked point index and coordinates from a PyVista pick callback payload.
        
        Uses the 3D pick position and finds the closest point in the current tree points.
        This is more reliable than VTK's point_index, which can return a non-closest point
        due to ray-casting through dense point clouds.
        """
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            return None, None

        # Extract the 3D pick position from the pick callback payload
        picked_point = None
        if hasattr(picked_info, 'picked_point'):
            picked_point = np.asarray(picked_info.picked_point, dtype=float)
        elif isinstance(picked_info, dict) and 'picked_point' in picked_info:
            picked_point = np.asarray(picked_info['picked_point'], dtype=float)
        elif hasattr(picked_info, 'points') and picked_info.points is not None:
            picked_point = np.asarray(picked_info.points[0], dtype=float)
        elif isinstance(picked_info, np.ndarray):
            picked_point = picked_info.ravel()
        else:
            # Last resort: try to use point_index with distance check
            point_index = None
            if hasattr(picked_info, 'point_index'):
                point_index = picked_info.point_index
            elif isinstance(picked_info, dict) and 'point_index' in picked_info:
                point_index = picked_info['point_index']
            if point_index is not None:
                try:
                    point_index = int(point_index)
                    if 0 <= point_index < len(self.current_tree_points):
                        return point_index, self.current_tree_points[point_index]
                except (TypeError, ValueError):
                    pass
            return None, None

        if picked_point is None or picked_point.shape[0] < 3:
            return None, None

        # Find the closest point in the current tree to the pick position
        # This is more accurate than VTK's point_index for dense point clouds
        squared_distances = np.sum((self.current_tree_points[:, :3] - picked_point[:3]) ** 2, axis=1)
        point_index = int(np.argmin(squared_distances))

        if point_index < 0 or point_index >= len(self.current_tree_points):
            return None, None

        return point_index, self.current_tree_points[point_index]

    def _resolve_current_visualization_global_indices(self):
        """Map the current visualization back to original LAS indices."""
        if self.las_data is None:
            return None

        if self.all_masks is not None and len(self.all_masks) > 0:
            try:
                per_mask_indices = [np.where(mask)[0] for mask in self.all_masks]
                if per_mask_indices:
                    return np.concatenate(per_mask_indices)
            except Exception:
                pass

        if self.current_mask is not None:
            try:
                return np.where(self.current_mask)[0]
            except Exception:
                return None

        return None

    def _sanitize_filename_part(self, value):
        """Convert a tree identifier into a filesystem-friendly filename fragment."""
        import re

        text = str(value) if value is not None else "tree"
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
        return text or "tree"

    def _select_points_with_radius(self, picked_point_coords):
        """Select points within the configured radius around the picked point."""
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            raise ValueError("No tree points available for radius selection")

        radius_value = float(self.radius_value_input.value())
        center_point = np.asarray(picked_point_coords, dtype=float)
        if center_point.shape[0] < 2:
            raise ValueError("Invalid picked point coordinates")

        self.radius_selection_center = center_point[:3]
        xy_offsets = self.current_tree_points[:, :2] - center_point[:2]
        distances = np.sqrt(np.sum(xy_offsets ** 2, axis=1))
        selected_indices = np.where(distances <= radius_value)[0]

        if len(selected_indices) == 0:
            raise ValueError(f"No points found within {radius_value:.2f} m of the picked point")

        self.selected_point_indices = selected_indices
        self.selected_polygon = None
        self.visualize_selected_points()
        self.log_to_console(
            f"Selected {len(selected_indices)} points within {radius_value:.2f} m of ({center_point[0]:.2f}, {center_point[1]:.2f}, {center_point[2]:.2f})."
        )

        self._export_selected_radius_points(radius_value)

    def _export_selected_radius_points(self, radius_value):
        """Export the currently selected radius points to a tree-specific LAS file."""
        if self.las_data is None:
            raise ValueError("No LAS data available for export")

        if self.selected_point_indices is None or len(self.selected_point_indices) == 0:
            raise ValueError("No radius-selected points available for export")

        global_indices = self._resolve_current_visualization_global_indices()
        if global_indices is None or len(global_indices) == 0:
            raise ValueError("Could not determine original LAS indices for the current visualization")

        if np.max(self.selected_point_indices) >= len(global_indices):
            raise ValueError("Selection indices exceed the available LAS index mapping")

        original_indices = global_indices[self.selected_point_indices]
        if len(original_indices) == 0:
            raise ValueError("No original LAS indices resolved for export")

        import copy

        if getattr(self, 'current_las_path', None):
            las_dir = os.path.dirname(self.current_las_path)
            las_basename = os.path.splitext(os.path.basename(self.current_las_path))[0]
        else:
            las_dir = os.getcwd()
            las_basename = "tree_export"

        safe_tree_id = self._sanitize_filename_part(self.current_tree_id if self.current_tree_id is not None else "tree")
        radius_token = f"{radius_value:.2f}".replace('.', 'p')

        export_dir = os.path.join(las_dir, "tree", las_basename, f"tree_{safe_tree_id}")
        os.makedirs(export_dir, exist_ok=True)

        output_path = os.path.join(export_dir, f"tree_{safe_tree_id}_radius_{radius_token}m.las")

        subset_points = self.las_data.points[original_indices].copy()
        header = copy.deepcopy(self.las_data.header)
        export_las = laspy.LasData(header)
        export_las.points = subset_points
        export_las.write(output_path)

        self.log_to_console(
            f"💾 Exported {len(original_indices)} points to {output_path}"
        )
        self.log_to_console(
            f"📁 Tree folder: {export_dir}"
        )

    def on_point_picked(self, picked_info):
        """Callback for point picking - shows ITC value and trunk ID of picked point."""
        if getattr(self, 'gdb_pick_mode', False):
            self._handle_gdb_pick(picked_info)
            return

        if self.current_tree_points is None or self.current_itc_values is None:
            self.log_to_console("Warning: No tree data available for point picking")
            return

        try:
            point_index, point_coords = self._resolve_picked_point(picked_info)
            if point_index is None or point_coords is None:
                self.log_to_console("Warning: Could not resolve picked point")
                return

            if self.radius_selection_active:
                try:
                    self._select_points_with_radius(point_coords)
                except Exception as radius_error:
                    self.log_to_console(f"Error in radius export selection: {str(radius_error)}")
                    QMessageBox.warning(self, "Radius Selection Error", str(radius_error))
                finally:
                    self.cancel_radius_selection(log_message=False)
                return

            if point_index < len(self.current_itc_values):
                itc_value = self.current_itc_values[point_index]
                message = f"Point picked - ITC: {itc_value}, Coordinates: ({point_coords[0]:.2f}, {point_coords[1]:.2f}, {point_coords[2]:.2f})"

                if hasattr(self, 'trunk_assignment') and self.trunk_assignment is not None:
                    if point_index < len(self.trunk_assignment):
                        trunk_id = self.trunk_assignment[point_index]
                        if trunk_id >= 0:
                            message += f" | Trunk: {trunk_id}"
                        else:
                            message += " | Trunk: NOISE"

                self.log_to_console(message)
            else:
                self.log_to_console("Warning: Point index out of range")

        except Exception as e:
            self.log_to_console(f"Error in point picking: {str(e)}")

    def start_polygon_selection(self):
        """Start polygon selection mode for manual point cloud segmentation."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            QMessageBox.warning(self, "Warning", "No tree points available for selection.")
            return

        try:
            # Get corresponding ITC values
            if self.current_itc_values is None or len(self.current_itc_values) != len(self.current_tree_points):
                self.log_to_console("Warning: ITC values not available for current visualization")
                QMessageBox.warning(self, "Warning", "ITC values not available for current visualization.")
                return
            
            # Create and show 2D polygon selection dialog
            self.polygon_dialog = PolygonSelectionDialog(self.current_tree_points, self.current_itc_values, self)
            self.polygon_dialog.polygon_completed.connect(self.on_polygon_completed)
            
            # Update button states
            self.draw_polygon_button.setText("Cancel Selection")
            self.draw_polygon_button.clicked.disconnect()
            self.draw_polygon_button.clicked.connect(self.cancel_polygon_selection)
            
            self.polygon_dialog.exec()
            
        except Exception as e:
            self.log_to_console(f"Error starting polygon selection: {str(e)}")

    def on_polygon_completed(self, polygon_2d):
        """Handle completion of 2D polygon selection."""
        try:
            self.selected_polygon = polygon_2d
            self.log_to_console(f"Polygon completed with {len(polygon_2d)} points.")
            
            # Find points inside polygon
            self.find_points_in_polygon()
            
            # Enable assign button
            self.assign_itc_button.setEnabled(True)
            
            # Enable volume calculation button
            self.volume_calc_button.setEnabled(True)
            
            # Visualize selected points
            self.visualize_selected_points()
            
            # Reset button
            self.draw_polygon_button.setText("Draw Selection")
            self.draw_polygon_button.clicked.disconnect()
            self.draw_polygon_button.clicked.connect(self.start_polygon_selection)
            
        except Exception as e:
            self.log_to_console(f"Error processing completed polygon: {str(e)}")

    def _refresh_tree_list_colors(self):
        """Refresh the colors of tree list items based on whether they have volume data."""
        for i in range(self.tree_list.count()):
            item = self.tree_list.item(i)
            tree_id = item.text()
            if tree_id in self.trees_with_volume_data:
                item.setForeground(QColor('red'))
            else:
                item.setForeground(QColor('black'))  # Default color

    def _on_dbh_height_changed(self, value):
        """Called when the user changes the DBH reference height via the spinbox."""
        self.dbh_reference_height = float(value)
        self.log_to_console(f"📏 DBH reference height set to: {self.dbh_reference_height:.2f}m (re-visualize tree to update marker)")

    def select_all_points(self):
        """Select all points in the current visualization without drawing."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            QMessageBox.warning(self, "Warning", "No tree points available for selection.")
            return

        try:
            # Select all points in the current visualization
            self.selected_point_indices = np.arange(len(self.current_tree_points))
            self.selected_polygon = None  # No polygon for "select all"
            
            self.log_to_console(f"Selected all {len(self.selected_point_indices)} points in current visualization.")
            
            # Enable assign button
            self.assign_itc_button.setEnabled(True)
            
            # Enable volume calculation button
            self.volume_calc_button.setEnabled(True)
            
            # Visualize selected points (all points will be highlighted)
            self.visualize_selected_points()
            
        except Exception as e:
            self.log_to_console(f"Error selecting all points: {str(e)}")

    def cancel_polygon_selection(self):
        """Cancel polygon selection mode."""
        self.polygon_selection_mode = False
        self.polygon_points = []
        self.selected_polygon = None
        self.selected_point_indices = None
        
        # Close dialog if open
        if hasattr(self, 'polygon_dialog') and self.polygon_dialog.isVisible():
            self.polygon_dialog.reject()
        
        # Clear any polygon visualization
        try:
            self.plotter.remove_actor('selected_points')
            self.plotter.remove_actor('selection_polygon')
            self.plotter.update()
        except:
            pass
        
        # Reset button
        self.draw_polygon_button.setText("Draw Selection")
        self.draw_polygon_button.clicked.disconnect()
        self.draw_polygon_button.clicked.connect(self.start_polygon_selection)
        
        self.assign_itc_button.setEnabled(False)
        self.volume_calc_button.setEnabled(False)
        self.clear_volume_button.setEnabled(False)
        self.log_to_console("Polygon selection cancelled.")

    def on_left_click(self, obj, event):
        """VTK callback for left-click to add polygon point."""
        if not self.polygon_selection_mode:
            return
            
        try:
            # Project click position to Z-plane
            point_3d = self.project_click_to_plane()
            if point_3d is not None:
                self.polygon_points.append(point_3d)
                
                # Visualize the point
                self.visualize_polygon_progress()
                
                self.log_to_console(f"Added point {len(self.polygon_points)}: ({point_3d[0]:.2f}, {point_3d[1]:.2f}, {point_3d[2]:.2f})")
            
        except Exception as e:
            self.log_to_console(f"Error adding polygon point: {str(e)}")

    def on_right_click(self, obj, event):
        """VTK callback for right-click to finish polygon."""
        if not self.polygon_selection_mode or len(self.polygon_points) < 3:
            if len(self.polygon_points) < 3:
                self.log_to_console("Warning: Need at least 3 points to create a polygon.")
            return
            
        try:
            self.selected_polygon = np.array(self.polygon_points)
            self.log_to_console(f"Polygon completed with {len(self.polygon_points)} points.")
            
            # Find points inside polygon
            self.find_points_in_polygon()
            
            # Enable assign button
            self.assign_itc_button.setEnabled(True)
            
            # Visualize selected points
            self.visualize_selected_points()
            
            # Exit polygon drawing mode
            self.polygon_selection_mode = False
            self.plotter.iren.remove_observers('LeftButtonPressEvent')
            self.plotter.iren.remove_observers('RightButtonPressEvent')
            
        except Exception as e:
            self.log_to_console(f"Error finishing polygon: {str(e)}")

    def project_click_to_plane(self):
        """Project the current mouse click position to the polygon Z-plane."""
        try:
            # Get mouse position in display coordinates
            click_pos = self.plotter.iren.get_event_position()
            
            # Use PyVista's built-in click position picking
            world_pos = self.plotter.pick_click_position()
            
            if world_pos is not None and not np.allclose(world_pos, [0, 0, 0]):
                # If we got a valid pick from existing geometry, use it
                return np.array(world_pos)
            else:
                # Project to Z-plane using camera ray casting
                camera = self.plotter.camera
                renderer = self.plotter.renderer
                
                # Get display coordinates
                display_point = [click_pos[0], click_pos[1], 0.0]
                
                # Convert display coordinates to world coordinates
                renderer.set_display_point(display_point[0], display_point[1], 0.0)
                renderer.display_to_world()
                world_near = np.array(renderer.get_world_point())
                
                renderer.set_display_point(display_point[0], display_point[1], 1.0)
                renderer.display_to_world()
                world_far = np.array(renderer.get_world_point())
                
                # Calculate ray direction
                ray_direction = world_far - world_near
                ray_direction = ray_direction / np.linalg.norm(ray_direction)
                
                # Find intersection with Z-plane
                if abs(ray_direction[2]) > 1e-6:
                    t = (self.polygon_z_plane - world_near[2]) / ray_direction[2]
                    if t >= 0:  # Only forward intersections
                        intersection = world_near + t * ray_direction
                        return intersection
                
                # Fallback: use camera focal point projected to Z-plane
                focal_point = np.array(camera.focal_point)
                return np.array([focal_point[0], focal_point[1], self.polygon_z_plane])
                
        except Exception as e:
            self.log_to_console(f"Error projecting click to plane: {str(e)}")
            return None

    def visualize_polygon_progress(self):
        """Visualize the polygon as it's being drawn."""
        try:
            if len(self.polygon_points) > 0:
                # Show current points
                points_array = np.array(self.polygon_points)
                points_cloud = pv.PolyData(points_array)
                self.plotter.add_points(points_cloud, color='cyan', point_size=8, 
                                      render_points_as_spheres=True, name='polygon_points')
                
                # Show lines connecting points
                if len(self.polygon_points) > 1:
                    lines = []
                    for i in range(len(self.polygon_points) - 1):
                        lines.extend([self.polygon_points[i], self.polygon_points[i+1]])
                    if len(lines) > 0:
                        lines_array = np.array(lines)
                        self.plotter.add_lines(lines_array, color='cyan', width=2, name='polygon_lines')
                
                self.plotter.update()
                
        except Exception as e:
            self.log_to_console(f"Error visualizing polygon progress: {str(e)}")

    def find_points_in_polygon(self):
        """Find all points within the drawn polygon."""
        if self.selected_polygon is None or self.current_tree_points is None:
            return
            
        try:
            # Get polygon bounds
            min_x, max_x = np.min(self.selected_polygon[:, 0]), np.max(self.selected_polygon[:, 0])
            min_y, max_y = np.min(self.selected_polygon[:, 1]), np.max(self.selected_polygon[:, 1])
            
            # Get coordinates based on current view mode
            if self.polygon_dialog.view_mode == 'top' or self.polygon_dialog.view_mode == 'bottom':
                # XY coordinates
                points_2d = self.current_tree_points[:, :2]
            elif self.polygon_dialog.view_mode == 'front' or self.polygon_dialog.view_mode == 'back':
                # XZ coordinates
                points_2d = self.current_tree_points[:, [0, 2]]
            elif self.polygon_dialog.view_mode == 'left' or self.polygon_dialog.view_mode == 'right':
                # YZ coordinates
                points_2d = self.current_tree_points[:, [1, 2]]
            else:
                # Default to XY
                points_2d = self.current_tree_points[:, :2]
            
            # Find points within bounding box
            bbox_mask = (
                (points_2d[:, 0] >= min_x) & 
                (points_2d[:, 0] <= max_x) &
                (points_2d[:, 1] >= min_y) & 
                (points_2d[:, 1] <= max_y)
            )
            
            # Get candidate points
            candidate_points = points_2d[bbox_mask]
            
            if len(candidate_points) == 0:
                self.selected_point_indices = np.array([], dtype=int)
                self.log_to_console("No points found within polygon bounding box.")
                return
                
            # Point-in-polygon test using ray casting algorithm
            def point_in_polygon(point, polygon):
                x, y = point[0], point[1]
                n = len(polygon)
                inside = False
                
                p1x, p1y = polygon[0]
                for i in range(1, n + 1):
                    p2x, p2y = polygon[i % n]
                    if y > min(p1y, p2y):
                        if y <= max(p1y, p2y):
                            if x <= max(p1x, p2x):
                                if p1y != p2y:
                                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                                if p1x == p2x or x <= xinters:
                                    inside = not inside
                    p1x, p1y = p2x, p2y
                    
                return inside
            
            # Test each candidate point
            inside_mask = np.array([point_in_polygon(pt, self.selected_polygon) for pt in candidate_points])
            selected_candidates = np.where(bbox_mask)[0][inside_mask]
            
            self.selected_point_indices = selected_candidates
            self.log_to_console(f"Selected {len(self.selected_point_indices)} points within polygon.")
            
        except Exception as e:
            self.log_to_console(f"Error finding points in polygon: {str(e)}")
            self.selected_point_indices = None

    def visualize_selected_points(self):
        """Visualize the selected points in the polygon."""
        if self.selected_point_indices is None or len(self.selected_point_indices) == 0:
            return
            
        try:
            selected_points = self.current_tree_points[self.selected_point_indices]
            
            # Get ITC values for selected points and apply 9-color cycling
            if self.current_itc_values is not None and len(self.current_itc_values) > 0:
                selected_itc_values = self.current_itc_values[self.selected_point_indices]
                # Map ITC values to color indices 0-8 (9 colors total)
                color_indices = (selected_itc_values - 1) % 9
                
                # Add selected points with ITC-based colors
                selected_cloud = pv.PolyData(selected_points)
                self.plotter.add_points(selected_cloud, scalars=color_indices, point_size=5, 
                                      render_points_as_spheres=True, name='selected_points',
                                      cmap='tab10', n_colors=9, clim=[0, 8])
            else:
                # Fallback to red if no ITC values available
                selected_cloud = pv.PolyData(selected_points)
                self.plotter.add_points(selected_cloud, color='red', point_size=5, 
                                      render_points_as_spheres=True, name='selected_points')
            
            # Add polygon outline (convert 2D polygon to 3D by adding Z coordinate)
            if self.selected_polygon is not None:
                # Use average Z height for the polygon plane
                avg_z = np.mean(self.current_tree_points[:, 2]) if len(self.current_tree_points) > 0 else 0.0
                
                # Convert 2D polygon to 3D
                polygon_3d = np.column_stack([
                    self.selected_polygon[:, 0],
                    self.selected_polygon[:, 1],
                    np.full(len(self.selected_polygon), avg_z)
                ])
                
                # Close the polygon
                closed_polygon = np.vstack([polygon_3d, polygon_3d[0]])
                self.plotter.add_lines(closed_polygon, color='yellow', width=3, name='selection_polygon')
            
            self.plotter.update()
            self.log_to_console("Selected points highlighted with ITC-based colors.")
            
        except Exception as e:
            self.log_to_console(f"Error visualizing selected points: {str(e)}")

    def convert_to_noise_class(self, noise_itc_value=9999, analyzed_points=None):
        """Convert the currently analyzed points to noise class with specified ITC value."""
        print(f"DEBUG: convert_to_noise_class called with analyzed_points={analyzed_points}")
        print(f"DEBUG: type(analyzed_points)={type(analyzed_points)}")
        if analyzed_points is not None:
            print(f"DEBUG: len(analyzed_points)={len(analyzed_points) if hasattr(analyzed_points, '__len__') else 'no len'}")
        print(f"DEBUG: self.current_tree_points={self.current_tree_points}")
        print(f"DEBUG: type(self.current_tree_points)={type(self.current_tree_points)}")
        if self.current_tree_points is not None:
            print(f"DEBUG: len(self.current_tree_points)={len(self.current_tree_points) if hasattr(self.current_tree_points, '__len__') else 'no len'}")
        print(f"DEBUG: hasattr(self, 'last_analyzed_points')={hasattr(self, 'last_analyzed_points')}")
        if hasattr(self, 'last_analyzed_points'):
            print(f"DEBUG: self.last_analyzed_points={self.last_analyzed_points}")
            print(f"DEBUG: type(self.last_analyzed_points)={type(self.last_analyzed_points)}")
            if self.last_analyzed_points is not None:
                print(f"DEBUG: len(self.last_analyzed_points)={len(self.last_analyzed_points) if hasattr(self.last_analyzed_points, '__len__') else 'no len'}")
        
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        # Check if we have analyzed points provided, otherwise try current/last points
        points_to_convert = analyzed_points
        print(f"DEBUG: initial points_to_convert={points_to_convert}")
        if points_to_convert is None or len(points_to_convert) == 0:
            print("DEBUG: points_to_convert is None or empty, using self.current_tree_points")
            points_to_convert = self.current_tree_points
        print(f"DEBUG: after first check, points_to_convert={points_to_convert}")
        if points_to_convert is None or len(points_to_convert) == 0:
            print("DEBUG: still None or empty, checking last_analyzed_points")
            # If no current points, check if we have any points from the last analysis
            if hasattr(self, 'last_analyzed_points') and self.last_analyzed_points is not None:
                points_to_convert = self.last_analyzed_points
                print(f"DEBUG: set points_to_convert to last_analyzed_points: {points_to_convert}")
            else:
                print("DEBUG: no points available, returning")
                QMessageBox.warning(self, "Warning", "No points available for conversion.")
                return

        print(f"DEBUG: final points_to_convert={points_to_convert}, type={type(points_to_convert)}")
        if points_to_convert is not None:
            print(f"DEBUG: len(points_to_convert)={len(points_to_convert)}")

        try:
            # Store the points we're converting for reference
            self.last_analyzed_points = points_to_convert
            
            # Use all available points for noise conversion
            self.selected_point_indices = np.arange(len(points_to_convert))
            self.selected_polygon = None  # No polygon for "convert all to noise"
            
            # Assign the noise ITC value
            self.assign_itc_to_selection(noise_itc_value)
            
            self.log_to_console(f"Converted {len(self.selected_point_indices)} points to noise class (ITC {noise_itc_value})")
            
            # Show success message
            QMessageBox.information(self, "Success", 
                                  f"Successfully converted {len(self.selected_point_indices)} points to noise class with ITC value {noise_itc_value}.")
            
        except Exception as e:
            self.log_to_console(f"Error converting to noise class: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to convert to noise class: {str(e)}")

    def assign_itc_to_selection(self, new_itc=None):
        """Assign new ITC value to selected points."""
        # Basic validation
        if self.selected_point_indices is None:
            QMessageBox.warning(self, "Warning", "No points selected (selection is None).")
            return

        if len(self.selected_point_indices) == 0:
            QMessageBox.warning(self, "Warning", "No points selected (selection is empty).")
            return

        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS data available.")
            return

        # Get new ITC value from user (if not provided)
        if new_itc is None:
            # Get unique ITC values from selected points
            selected_itc_values = set()
            itc_array = np.array(self.las_data['itc'])
            
            # Map merged visualization indices back to original LAS indices
            if self.all_masks is not None and len(self.all_masks) > 0:
                try:
                    per_mask_indices = [np.where(mask)[0] for mask in self.all_masks]
                    global_indices = np.concatenate(per_mask_indices)
                except Exception:
                    QMessageBox.warning(self, "Warning", "Could not determine original indices for selection.")
                    return
            elif self.current_mask is not None and len(self.current_mask) == len(self.las_data.points):
                # Single-tree case: use the boolean mask for mapping
                global_indices = np.where(self.current_mask)[0]
            else:
                QMessageBox.warning(self, "Warning", "Could not determine original LAS indices for the selection.")
                return
            
            if len(global_indices) == 0:
                QMessageBox.warning(self, "Warning", "No corresponding LAS indices found for the selection.")
                return
            
            # Ensure selected_point_indices are within range
            if np.max(self.selected_point_indices) >= len(global_indices):
                QMessageBox.warning(self, "Warning", "Internal index mapping error: selection out of range.")
                return
            
            # Map to original LAS indices
            original_indices = global_indices[self.selected_point_indices]
            
            # Get ITC values from selected points
            for idx in original_indices:
                if idx < len(itc_array):
                    selected_itc_values.add(int(itc_array[idx]))

            # Show ITC assignment dialog
            dialog = ITCAssignmentDialog(list(selected_itc_values), self)
            result = dialog.exec()

            if result == QDialog.DialogCode.Accepted and dialog.selected_itc is not None:
                new_itc = dialog.selected_itc
            else:
                return
        else:
            # Validate provided ITC value
            if not isinstance(new_itc, int) or new_itc < 1 or new_itc > 999999:
                QMessageBox.warning(self, "Warning", "Invalid ITC value provided.")
                return

        try:
            # Map merged visualization indices back to original LAS indices
            # The merged points order corresponds to concatenating mask_indices for each mask in self.all_masks
            if self.all_masks is not None and len(self.all_masks) > 0:
                try:
                    per_mask_indices = [np.where(mask)[0] for mask in self.all_masks]
                    global_indices = np.concatenate(per_mask_indices)
                except Exception:
                    # Fallback: build iteratively to avoid odd shapes
                    global_list = []
                    for mask in self.all_masks:
                        idxs = np.where(mask)[0]
                        global_list.append(idxs)
                    if len(global_list) > 0:
                        global_indices = np.concatenate(global_list)
                    else:
                        global_indices = np.array([], dtype=int)
            elif self.current_mask is not None and len(self.current_mask) == len(self.las_data.points):
                # Single-tree case: use the boolean mask for mapping
                global_indices = np.where(self.current_mask)[0]
            else:
                self.log_to_console("Warning: Could not determine original indices for selection.")
                QMessageBox.warning(self, "Warning", "Could not determine original LAS indices for the selected points.")
                return

            if len(global_indices) == 0:
                self.log_to_console("Warning: No global indices found for selection.")
                QMessageBox.warning(self, "Warning", "No corresponding LAS indices found for the selection.")
                return

            # Ensure selected_point_indices are within range
            if np.max(self.selected_point_indices) >= len(global_indices):
                self.log_to_console("Error: Selection indices exceed mapped global indices range.")
                QMessageBox.critical(self, "Error", "Internal index mapping error: selection out of range.")
                return

            # Map to original LAS indices and perform update in-memory
            original_indices = global_indices[self.selected_point_indices]
            self.las_data['itc'][original_indices] = new_itc

            # Record the change for session tracking
            from datetime import datetime
            change_record = {
                'timestamp': datetime.now(),
                'original_indices': original_indices,
                'new_itc': new_itc,
                'num_points': len(original_indices)
            }
            self.itc_changes.append(change_record)

            # Also update current visualization ITC values so the view can refresh
            if self.current_itc_values is not None and len(self.current_itc_values) == len(global_indices):
                self.current_itc_values[self.selected_point_indices] = new_itc

            self.log_to_console(f"Assigned ITC value {new_itc} to {len(original_indices)} points (in-memory).")

            # Refresh visualization to reflect changes
            try:
                self.update_tree_colors(self.color_combo.currentText())
            except Exception:
                # If recoloring fails, at least clear selection markers
                pass

            # Clear selection visualization and state
            try:
                if self.plotter:
                    if 'selected_points' in self.plotter.actors:
                        self.plotter.remove_actor('selected_points')
                    if 'selection_polygon' in self.plotter.actors:
                        self.plotter.remove_actor('selection_polygon')
                    self.plotter.update()
            except Exception:
                pass

            self.cancel_polygon_selection()

            QMessageBox.information(self, "Success",
                                    f"Assigned ITC value {new_itc} to {len(original_indices)} points.\n"
                                    "Note: Changes are in memory only. Save LAS to persist changes.")

        except Exception as e:
            self.log_to_console(f"Error assigning ITC value: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to assign ITC value: {str(e)}")

    def clear_plot(self):
        """Clear the 3D visualization and reset camera."""
        if self.plotter:
            self.plotter.clear()
            self._restore_gdb_layers()
            self.plotter.reset_camera()
            self.plotter.update()
        
        # Reset cluster highlighting state
        self.current_cluster_index = -1
        
        # Reset trunk and branch detection state
        self.trunk_assignment = None
        self.branch_assignment = None
        
        # Disable buttons when clearing
        self.detect_branches_button.setEnabled(False)
        self.detect_trunks_button.setEnabled(False)
    # extract buttons removed
        self.draw_polygon_button.setEnabled(False)
        self.select_all_points_button.setEnabled(False)
        self.assign_itc_button.setEnabled(False)
        self.volume_calc_button.setEnabled(False)
        self.clear_volume_button.setEnabled(False)
        
        # Cancel any active polygon selection
        if self.polygon_selection_mode:
            self.cancel_polygon_selection()

    def save_las_file(self):
        """Save the modified LAS file with a summary of changes."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS data available.")
            return

        if not self.itc_changes:
            QMessageBox.information(self, "No Changes", "No ITC assignments have been made in this session.")
            return

        # Create summary text
        summary_text = "ITC Assignment Summary\n"
        summary_text += "=" * 50 + "\n\n"
        summary_text += f"Total assignments: {len(self.itc_changes)}\n"
        summary_text += f"Total points modified: {sum(change['num_points'] for change in self.itc_changes)}\n\n"

        summary_text += "Assignment Details:\n"
        summary_text += "-" * 40 + "\n"
        for i, change in enumerate(self.itc_changes, 1):
            timestamp = change['timestamp'].strftime("%H:%M:%S")
            summary_text += f"{i}. {timestamp} - ITC {change['new_itc']} assigned to {change['num_points']} points\n"

        # Show summary dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Save LAS File - Change Summary")
        msg_box.setText(summary_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)

        # Add export summary button
        export_button = msg_box.addButton("Export Summary", QMessageBox.ButtonRole.ActionRole)

        result = msg_box.exec()

        if result == QMessageBox.StandardButton.Save:
            # Save LAS file
            self._save_las_file()
        elif msg_box.clickedButton() == export_button:
            # Export summary
            self._export_summary(summary_text)
            # Then ask if they want to save
            reply = QMessageBox.question(self, "Save LAS File",
                                       "Summary exported. Do you also want to save the LAS file?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._save_las_file()

    def _save_las_file(self):
        """Internal method to save the LAS file."""
        try:
            # Get save file path
            file_dialog = QFileDialog()
            file_dialog.setNameFilter("LAS files (*.las)")
            file_dialog.setDefaultSuffix("las")
            file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

            if file_dialog.exec():
                save_path = file_dialog.selectedFiles()[0]

                # Save the LAS file
                self.las_data.write(save_path)

                QMessageBox.information(self, "Success",
                                      f"LAS file saved successfully to:\n{save_path}\n\n"
                                      f"All {len(self.itc_changes)} ITC assignments have been persisted.")

                # Clear changes after successful save
                self.itc_changes = []
                self.log_to_console(f"LAS file saved to {save_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save LAS file:\n{str(e)}")

    def analyze_tree_with_ai(self):
        """Analyze the currently visualized tree using AI for structure evaluation."""
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            QMessageBox.warning(self, "Warning", "No tree currently visualized for analysis.")
            return

        try:
            self.log_to_console("Starting AI analysis of tree structure...")

            # Store the points being analyzed for potential noise conversion
            self.last_analyzed_points = self.current_tree_points.copy() if self.current_tree_points is not None else None

            # Generate unique analysis ID
            analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create analysis log directory
            analysis_log_dir = os.path.join(os.path.dirname(__file__), 'analysis_log')
            os.makedirs(analysis_log_dir, exist_ok=True)

            # Create subdirectory for this analysis
            analysis_dir = os.path.join(analysis_log_dir, f"analysis_{analysis_id}")
            os.makedirs(analysis_dir, exist_ok=True)

            self.log_to_console(f"Analysis log will be saved to: {analysis_dir}")

            # Take screenshots from 4 different views
            screenshot_paths = self.take_tree_screenshots()

            if not screenshot_paths:
                QMessageBox.warning(self, "Error", "Failed to capture tree screenshots.")
                return

            # Save screenshots to analysis directory
            saved_screenshot_paths = self.save_analysis_screenshots(screenshot_paths, analysis_dir, analysis_id)

            # Run AI analysis
            ai_result = self.run_ai_analysis(screenshot_paths)

            # Save analysis results
            self.save_analysis_results(analysis_dir, analysis_id, ai_result, saved_screenshot_paths)

            # Display results
            self.display_ai_results(ai_result)
            


            # Clean up temporary screenshots
            self.cleanup_screenshots(screenshot_paths)

        except Exception as e:
            self.log_to_console(f"Error in AI analysis: {str(e)}")
            QMessageBox.critical(self, "Error", f"AI analysis failed: {str(e)}")

    def batch_analyze_trunk_volumes(self):
        """
        Automated batch processing across all checked LAS files in the Layer Manager.
        For each checked LAS file, iterates through all tree IDs with trunk points,
        visualizes trunk, detects trunk/branches, calculates volume, and exports metrics.
        """
        # Determine target LAS files from layer manager (or active file fallback)
        checked_layers = [l for l in self.las_layers if l.get('checked', True)]
        if not checked_layers and self.current_las_path:
            norm_c = os.path.normpath(self.current_las_path)
            checked_layers = [{
                'path': norm_c,
                'name': os.path.basename(norm_c)
            }]

        if not checked_layers:
            QMessageBox.warning(self, "Warning", "No LAS files checked or loaded for batch analysis.")
            return

        try:
            import time

            batch_start_perf = time.perf_counter()
            batch_start_dt = datetime.now()
            self.log_to_console(f"⏱️ Multi-LAS Batch analysis started for {len(checked_layers)} file(s) at {batch_start_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            # --- Ask user for batch configuration dialogs (apply once for the entire batch run) ---
            skip_dialog = BatchSkipOptionsDialog(self, default_threshold=50)
            if skip_dialog.exec() != QDialog.Accepted:
                self.log_to_console("ℹ️ Batch cancelled by user (skip options)")
                return
            skip_opts = skip_dialog.get_options()
            self.log_to_console(f"🔧 Batch skip options: {skip_opts}")

            _batch_trunk_defaults = dict(getattr(self, 'trunk_detection_params', {}))
            _batch_trunk_defaults['dbh_reference_height'] = float(getattr(self, 'dbh_reference_height', 1.3))
            trunk_dialog = BatchTrunkParamsDialog(self, defaults=_batch_trunk_defaults)
            if trunk_dialog.exec() == QDialog.Accepted:
                new_trunk_params = trunk_dialog.get_params()
                try:
                    self.trunk_slice_height_input.setValue(int(new_trunk_params.get('slice_height_cm', 25)))
                    self.trunk_base_zone_input.setValue(float(new_trunk_params.get('base_zone_height_m', 0.0)))
                    self.trunk_eps_input.setValue(float(new_trunk_params.get('eps_m', 0.18)))
                    self.trunk_min_samples_input.setValue(int(new_trunk_params.get('min_samples', 8)))
                    self.trunk_merge_dist_input.setValue(float(new_trunk_params.get('merge_dist_m', 0.25)))
                    self.trunk_min_points_input.setValue(int(new_trunk_params.get('min_trunk_points', 120)))
                    self.trunk_min_span_input.setValue(float(new_trunk_params.get('min_vertical_span_m', 1.0)))
                    self.trunk_full_assign_input.setValue(float(new_trunk_params.get('full_height_assign_dist_m', 0.45)))
                    _batch_dbh_h = new_trunk_params.get('dbh_reference_height')
                    if _batch_dbh_h is not None:
                        if hasattr(self, 'dbh_height_input'):
                            self.dbh_height_input.setValue(float(_batch_dbh_h))
                        else:
                            self.dbh_reference_height = float(_batch_dbh_h)
                        self.log_to_console(
                            f"📏 Batch DBH reference height set to: {float(_batch_dbh_h):.2f}m"
                        )
                    self.trunk_detection_params.update(new_trunk_params)
                    self.log_to_console("🔧 Trunk detection parameters updated for batch run")
                except Exception:
                    pass
            else:
                self.log_to_console("ℹ️ Batch cancelled by user (trunk parameters)")
                return

            branch_dialog = BatchBranchParamsDialog(self, defaults={
                'slice_height_cm': getattr(self, 'slice_height_input', None) and int(self.slice_height_input.value()) or 25,
                'branch_eps': getattr(self, 'branch_eps_input', None) and float(self.branch_eps_input.value()) or 0.12,
                'branch_min_samples': getattr(self, 'branch_min_samples_input', None) and int(self.branch_min_samples_input.value()) or 6,
                'branch_merge_dist': getattr(self, 'branch_merge_dist_input', None) and float(self.branch_merge_dist_input.value()) or 0.25,
            })
            if branch_dialog.exec() == QDialog.Accepted:
                new_branch_params = branch_dialog.get_params()
                try:
                    self.slice_height_input.setValue(int(new_branch_params.get('slice_height_cm', 25)))
                    self.branch_eps_input.setValue(float(new_branch_params.get('branch_eps', 0.12)))
                    self.branch_min_samples_input.setValue(int(new_branch_params.get('branch_min_samples', 6)))
                    self.branch_merge_dist_input.setValue(float(new_branch_params.get('branch_merge_dist', 0.25)))
                    self.log_to_console("🔧 Branch detection parameters updated for batch run")
                except Exception:
                    pass
            else:
                self.log_to_console("ℹ️ Batch cancelled by user (branch parameters)")
                return

            total_trees_processed = 0
            total_trees_found = 0
            all_skipped_trees = []
            exported_csv_files = []

            for file_idx, layer in enumerate(checked_layers, 1):
                file_path = layer['path']
                file_name = layer['name']

                self.log_to_console(f"\n{'='*60}")
                self.log_to_console(f"🚀 [File {file_idx}/{len(checked_layers)}] Starting batch analysis for: {file_name}")
                self.log_to_console(f"{'='*60}")

                # Load/activate the LAS file
                try:
                    self.activate_las_layer(file_path, silent=True)
                except Exception as load_err:
                    self.log_to_console(f"❌ Failed to load file {file_name}: {load_err}")
                    continue

                if self.las_data is None or 'stemcls' not in self.las_data.point_format.dimension_names:
                    self.log_to_console(f"⚠️ Skipping file {file_name}: no valid LAS data or 'stemcls' field missing.")
                    continue

                all_forest_ids = sorted(self.unique_itc_values.tolist())
                itc_values = np.array(self.las_data['itc'])
                stemcls_values = np.array(self.las_data['stemcls'])
                
                valid_tree_ids = []
                for tree_id in all_forest_ids:
                    mask = (itc_values == tree_id) & (stemcls_values != 1)
                    if np.any(mask):
                        valid_tree_ids.append(tree_id)

                self.log_to_console(f"🌳 [{file_name}] Trees with trunk points: {len(valid_tree_ids)} / {len(all_forest_ids)}")
                total_trees_found += len(valid_tree_ids)

                if not valid_tree_ids:
                    self.log_to_console(f"ℹ️ [{file_name}] No trees with trunk points found.")
                    continue

                self.accumulated_volume_sections = []
                folder = os.path.join(os.path.dirname(file_path), 'volume', os.path.splitext(file_name)[0])
                os.makedirs(folder, exist_ok=True)
                self.volume_folder_path = folder
                if hasattr(self, 'volume_folder_label'):
                    self.volume_folder_label.setText(f"Volume Folder: {os.path.basename(folder)}")

                file_processed_count = 0
                skipped_trees = []

                for idx, tree_id in enumerate(valid_tree_ids, 1):
                    self.log_to_console(f"\n📍 [{file_name} | {idx}/{len(valid_tree_ids)}] Processing tree ID={tree_id}")

                    try:
                        self._visualize_trunk_single_tree(tree_id)
                        QApplication.processEvents()

                        try:
                            self.detect_trunks_in_slices()
                            QApplication.processEvents()
                        except Exception as dt_e:
                            self.log_to_console(f"⚠️ Trunk detection failed for tree {tree_id}: {dt_e}")

                        num_trunks = 0
                        if hasattr(self, 'trunk_assignment') and self.trunk_assignment is not None:
                            unique_trunks = np.unique(self.trunk_assignment)
                            unique_trunks = unique_trunks[unique_trunks >= 0]
                            num_trunks = len(unique_trunks)

                        if num_trunks == 0 and skip_opts.get('skip_no_trunk', True):
                            self.log_to_console(f"⏭️ Skipping tree {tree_id}: no trunks detected")
                            skipped_trees.append((tree_id, 'no_trunks'))
                            continue

                        if skip_opts.get('skip_small_trunk', True) and num_trunks > 0:
                            trunk_sizes = [int(np.sum(self.trunk_assignment == t)) for t in unique_trunks]
                            max_size = max(trunk_sizes) if trunk_sizes else 0
                            if max_size < int(skip_opts.get('small_trunk_threshold', 50)):
                                self.log_to_console(f"⏭️ Skipping tree {tree_id}: largest trunk {max_size} pts < threshold")
                                skipped_trees.append((tree_id, 'small_trunk'))
                                continue

                        try:
                            if num_trunks > 0:
                                self.detect_branch_clusters_in_slices()
                                QApplication.processEvents()
                        except Exception as db_e:
                            self.log_to_console(f"⚠️ Branch detection failed for tree {tree_id}: {db_e}")

                        self._select_all_points_silent()
                        QApplication.processEvents()
                        self._calculate_volume_silent()
                        QApplication.processEvents()

                        self._save_volume_data_silent()
                        QApplication.processEvents()

                        try:
                            self.export_trunk_metrics()
                        except Exception as export_e:
                            self.log_to_console(f"⚠️ Export failed for tree {tree_id}: {export_e}")
                            raise

                        self.clear_accumulated_volume()

                        file_processed_count += 1
                        total_trees_processed += 1
                        self.log_to_console(f"✅ [{file_name}] Successfully processed tree {tree_id}")

                    except Exception as e:
                        self.log_to_console(f"⚠️ [{file_name}] Skipped tree {tree_id}: {str(e)}")
                        skipped_trees.append((tree_id, str(e)))

                all_skipped_trees.extend([(file_name, tid, reason) for tid, reason in skipped_trees])

                # Save export file path for master merge
                export_file = os.path.join(os.path.dirname(file_path), 'export', f"{os.path.splitext(file_name)[0]}_trunk_metrics.csv")
                if os.path.exists(export_file):
                    exported_csv_files.append(export_file)

            # Master Multi-LAS Export Merger
            if len(exported_csv_files) > 1:
                try:
                    self._create_combined_multi_las_export(exported_csv_files)
                except Exception as merge_err:
                    self.log_to_console(f"⚠️ Failed to generate combined multi-LAS export CSV: {merge_err}")

            # Final summary
            batch_end_dt = datetime.now()
            elapsed_seconds = max(time.perf_counter() - batch_start_perf, 1e-9)
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))
            self.log_to_console(
                f"\n🎉 Multi-LAS Batch analysis completed! Total files: {len(checked_layers)} | Total trees processed: {total_trees_processed} | Duration: {elapsed_str}"
            )

            self._display_batch_completion_summary(
                total_trees_processed,
                total_trees_found,
                [(tid, reason) for _, tid, reason in all_skipped_trees],
                batch_start_dt,
                batch_end_dt,
                elapsed_seconds,
            )

        except Exception as e:
            self.log_to_console(f"❌ Batch analysis error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Batch analysis failed: {str(e)}")

    def _create_combined_multi_las_export(self, csv_files):
        """Combine metrics from multiple LAS export CSV files into a master CSV."""
        import csv
        combined_rows = []
        fieldnames = None

        for csv_path in csv_files:
            if not os.path.exists(csv_path):
                continue
            with open(csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                if fieldnames is None:
                    raw_fields = list(reader.fieldnames or [])
                    if 'las_file' not in raw_fields:
                        fieldnames = ['las_file'] + raw_fields
                    else:
                        fieldnames = raw_fields
                
                las_name = os.path.basename(csv_path).replace('_trunk_metrics.csv', '')
                for row in reader:
                    row['las_file'] = las_name
                    combined_rows.append(row)

        if combined_rows and fieldnames:
            first_file_dir = os.path.dirname(csv_files[0])
            master_csv = os.path.join(first_file_dir, "combined_multi_las_trunk_metrics.csv")
            with open(master_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(combined_rows)
            self.log_to_console(f"📊 Generated combined multi-LAS export: {master_csv}")


    def _visualize_trunk_single_tree(self, tree_id):
        """Visualize trunk for a single tree ID in batch mode."""
        if self.las_data is None:
            raise RuntimeError("No LAS data available")

        if not self.plotter:
            raise RuntimeError("3D viewer not initialized")

        # Clear previous visualization
        self.plotter.clear()
        self._restore_gdb_layers()

        try:
            itc_values = np.array(self.las_data['itc'])
            stemcls_values = np.array(self.las_data['stemcls'])
            
            # Get trunk points for this single tree
            mask = (itc_values == tree_id) & (stemcls_values != 1)

            # Apply treefilter if enabled
            if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                treefilter_values = np.array(self.las_data['treefilter'])
                mask = mask & (treefilter_values == 2)

            if not np.any(mask):
                raise ValueError(f"No trunk points for tree {tree_id}")

            points = np.column_stack([
                np.array(self.las_data.x)[mask],
                np.array(self.las_data.y)[mask],
                np.array(self.las_data.z)[mask]
            ])

            # Store for later use
            self.current_tree_points = points
            self.current_tree_id = tree_id
            self.current_mask = mask
            self.current_tree_ids = np.full(len(points), tree_id)
            self.current_color_values = None
            self.current_color_field = "Default (green)"

            # Compute full tree height (using all points for this tree ID, including canopy) for export.
            full_mask = (itc_values == tree_id)
            if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                treefilter_values = np.array(self.las_data['treefilter'])
                full_mask = full_mask & (treefilter_values == 2)

            if np.any(full_mask):
                full_zs = np.array(self.las_data.z)[full_mask]
                self.current_tree_height = float(np.max(full_zs) - np.min(full_zs))
                self.current_tree_ground_z = float(np.min(full_zs))
            else:
                self.current_tree_height = float(np.max(points[:, 2]) - np.min(points[:, 2]))
                self.current_tree_ground_z = float(np.min(points[:, 2]))

            # Visualize with green color
            self.plotter.add_points(points, color='green', point_size=3, name=f'trunk_tree_{tree_id}')
            self.plotter.reset_camera()

        except Exception as e:
            raise RuntimeError(f"Failed to visualize trunk for tree {tree_id}: {str(e)}")

    def _select_all_points_silent(self):
        """Select all points without UI messages (batch mode)."""
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            raise ValueError("No tree points available for selection")

        self.selected_point_indices = np.arange(len(self.current_tree_points))
        self.selected_polygon = None
        self.visualize_selected_points()  # Update visualization with highlighted selection

    def _calculate_volume_silent(self):
        """Calculate volume without user dialogs (batch mode)."""
        if self.selected_point_indices is None or len(self.selected_point_indices) == 0:
            raise ValueError("No points selected for volume calculation")

        if not hasattr(self, 'current_tree_points') or self.current_tree_points is None:
            raise ValueError("No tree points available")

        volume_groups, is_branch_mode = self._get_volume_groups_from_selection()
        if not volume_groups:
            raise ValueError("No valid point groups found for volume calculation")
        
        # Determine tree_id
        if hasattr(self, 'current_tree_ids') and self.current_tree_ids is not None:
            selected_tree_ids = self.current_tree_ids[self.selected_point_indices]
            unique_ids, counts = np.unique(selected_tree_ids, return_counts=True)
            section_tree_id = unique_ids[np.argmax(counts)]
        else:
            section_tree_id = self.current_tree_id
        
        # Find next section ID
        existing_section_ids = [int(s['section_id']) for s in self.accumulated_volume_sections 
                               if s['tree_id'] == section_tree_id and str(s['section_id']).isdigit()]
        section_id = max(existing_section_ids) + 1 if existing_section_ids else 1
        
        # Define colors
        section_colors = ['cyan', 'magenta', 'yellow', 'lime', 'orange', 'pink', 'purple', 'brown']
        point_color = section_colors[(section_id - 1) % len(section_colors)]
        circle_color = section_colors[(section_id - 1) % len(section_colors)]
        avg_color = 'red'

        # Support trunk-scoped processing when available
        if hasattr(self, 'volume_groups_by_trunk') and self.volume_groups_by_trunk:
            # Initialize trunk summary container
            self.trunk_volume_summary = {}

            # Suppress rendering during batch additions for performance
            if self.plotter is not None:
                self.plotter.suppress_rendering = True

            for trunk_id, branch_list in sorted(self.volume_groups_by_trunk.items(), key=lambda x: x[0]):
                trunk_total_vol = 0.0
                trunk_point_count = 0
                trunk_branch_details = []

                for branch_info in branch_list:
                    group_branch_id, _, group_points = branch_info
                    point_color = section_colors[(section_id - 1) % len(section_colors)]
                    circle_color = section_colors[(section_id - 1) % len(section_colors)]
                    branch_suffix = f" | B{group_branch_id}" if group_branch_id is not None else ""

                    # Add selected points
                    selected_cloud = pv.PolyData(group_points)
                    self.plotter.add_points(
                        selected_cloud,
                        color=point_color,
                        point_size=4,
                        opacity=0.6,
                        name=f'volume_section_{section_id}_points',
                        label=f'Section {section_id}{branch_suffix} Points ({len(group_points)} pts)',
                        pickable=False
                    )

                    # Add circle fitting
                    measurement_label = "Diameter" if is_branch_mode else "DBH"
                    section_data = self._add_dbh_circle_fitting_for_section(
                        group_points,
                        section_id,
                        circle_color,
                        avg_color,
                        measurement_label=measurement_label
                    )

                    # Calculate volume
                    section_volume = self._calculate_section_volume(section_data)

                    # Store section (annotate with trunk_id)
                    section_record = {
                        'tree_id': section_tree_id,
                        'section_id': section_id,
                        'trunk_id': int(trunk_id),
                        'branch_id': int(group_branch_id) if group_branch_id is not None else None,
                        'points': group_points.copy(),
                        'point_color': point_color,
                        'circle_color': circle_color,
                        'volume': section_volume,
                        'circle_data': section_data
                    }
                    self.accumulated_volume_sections.append(section_record)

                    # Update trunk totals and details
                    trunk_total_vol += float(section_volume)
                    trunk_point_count += int(len(group_points))
                    trunk_branch_details.append({
                        'branch_id': int(group_branch_id) if group_branch_id is not None else None,
                        'volume': float(section_volume),
                        'num_points': int(len(group_points)),
                        'min_z': float(section_data.get('min_z', 0.0)),
                        'max_z': float(section_data.get('max_z', 0.0))
                    })

                    self.log_to_console(
                        f"📏 Calculated volume for tree {section_tree_id}, trunk T{trunk_id} branch B{group_branch_id}: {section_volume:.4f} m³ (height: {section_data.get('height_range', 0.0):.2f}m, Z {section_data.get('min_z', 0.0):.2f}-{section_data.get('max_z', 0.0):.2f}m)"
                    )

                    section_id += 1

                # Save trunk summary
                self.trunk_volume_summary[int(trunk_id)] = {
                    'tree_id': section_tree_id,
                    'trunk_id': int(trunk_id),
                    'total_volume': float(trunk_total_vol),
                    'num_branches': len(trunk_branch_details),
                    'total_points': int(trunk_point_count),
                    'branches': trunk_branch_details
                }

                self.log_to_console(f"🧾 Trunk T{trunk_id} total volume: {trunk_total_vol:.4f} m³ ({len(trunk_branch_details)} branches, {trunk_point_count} pts)")

            # Re-enable rendering after batch additions
            if self.plotter is not None:
                self.plotter.suppress_rendering = False
                self.plotter.render()

            # Add section info labels showing trunk/branch/section for each section
            self._add_section_info_labels()
            self._log_section_diameter_breakdown()

            # Also log overall totals
            overall_total = sum(t['total_volume'] for t in self.trunk_volume_summary.values())
            self.log_to_console(f"📊 Overall tree total (sum of trunks): {overall_total:.4f} m³")

        else:
            # Fallback to original behavior (global/grouped branches)
            # Suppress rendering during batch additions for performance
            if self.plotter is not None:
                self.plotter.suppress_rendering = True

            for group_branch_id, _, group_points in volume_groups:
                point_color = section_colors[(section_id - 1) % len(section_colors)]
                circle_color = section_colors[(section_id - 1) % len(section_colors)]
                branch_suffix = f" | B{group_branch_id}" if group_branch_id is not None else ""

                # Add selected points
                selected_cloud = pv.PolyData(group_points)
                self.plotter.add_points(
                    selected_cloud,
                    color=point_color,
                    point_size=4,
                    opacity=0.6,
                    name=f'volume_section_{section_id}_points',
                    label=f'Section {section_id}{branch_suffix} Points ({len(group_points)} pts)',
                    pickable=False
                )

                # Add circle fitting
                measurement_label = "Diameter" if is_branch_mode else "DBH"
                section_data = self._add_dbh_circle_fitting_for_section(
                    group_points,
                    section_id,
                    circle_color,
                    avg_color,
                    measurement_label=measurement_label
                )

                # Calculate volume
                section_volume = self._calculate_section_volume(section_data)

                # Store section
                section_info = {
                    'tree_id': section_tree_id,
                    'section_id': section_id,
                    'branch_id': int(group_branch_id) if group_branch_id is not None else None,
                    'points': group_points.copy(),
                    'point_color': point_color,
                    'circle_color': circle_color,
                    'volume': section_volume,
                    'circle_data': section_data
                }
                self.accumulated_volume_sections.append(section_info)

                if group_branch_id is not None:
                    self.log_to_console(
                        f"📏 Calculated volume for tree {section_tree_id}, branch B{group_branch_id}: {section_volume:.4f} m³ (height: {section_data.get('height_range', 0.0):.2f}m, Z {section_data.get('min_z', 0.0):.2f}-{section_data.get('max_z', 0.0):.2f}m)"
                    )
                else:
                    self.log_to_console(f"📏 Calculated volume for tree {section_tree_id}: {section_volume:.4f} m³ (height: {section_data.get('height_range', 0.0):.2f}m, Z {section_data.get('min_z', 0.0):.2f}-{section_data.get('max_z', 0.0):.2f}m)")

                section_id += 1

            # Re-enable rendering after batch additions
            if self.plotter is not None:
                self.plotter.suppress_rendering = False
                self.plotter.render()

            # Add section info labels showing trunk/branch/section for each section
            self._add_section_info_labels()
            self._log_section_diameter_breakdown()

            # Perform global ground proximity check (allow in branch mode too)
            # This enables using globally fitted/extrapolated circles as DBH references
            try:
                self._check_global_ground_proximity_and_extrapolate()
            except Exception as e:
                self.log_to_console(f"⚠️ Error during global extrapolation: {e}")

            # Log extrapolation notification for any sections that were extrapolated
            for sec in self.accumulated_volume_sections:
                if sec.get('extrapolated') and sec.get('section_id') != "global_extrapolated":
                    sec_id = sec['section_id']
                    orig_hr = sec.get('original_height_range', 0.0)
                    extr_hr = sec.get('extrapolated_height_range', 0.0)
                    orig_min = sec.get('original_min_z', 0.0)
                    extr_min = sec.get('extrapolated_min_z', 0.0)
                    n_ext = sec.get('num_extrapolated_circles', 0)
                    ground = sec.get('ground_level_used', 0.0)
                    self.log_to_console(
                        f"⚠️ Section {sec_id}: EXTRAPOLATED to ground — original height: {orig_hr:.2f}m (Z {orig_min:.2f}m), "
                        f"extrapolated height: {extr_hr:.2f}m (Z {extr_min:.2f}m), "
                        f"{n_ext} circles added, ground level: {ground:.2f}m"
                    )
                elif sec.get('extrapolated') and sec.get('section_id') == "global_extrapolated":
                    extr_hr = sec.get('extrapolated_height_range', 0.0)
                    extr_min = sec.get('extrapolated_min_z', 0.0)
                    n_ext = sec.get('num_extrapolated_circles', 0)
                    ground = sec.get('ground_level_used', 0.0)
                    self.log_to_console(
                        f"⚠️ Global extrapolation section: height {extr_hr:.2f}m (Z {extr_min:.2f}m), "
                        f"{n_ext} circles added, ground level: {ground:.2f}m"
                    )

            self.plotter.update()

    def _save_volume_data_silent(self):
        """Save volume data without prompts (batch mode - reuses pre-set folder)."""
        if not self.accumulated_volume_sections:
            self.log_to_console("⚠️ No volume data to save")
            return

        if not self.volume_folder_path:
            raise RuntimeError("Volume folder path not set")

        try:
            import json
            
            # Group sections by tree_id
            trees_data = {}
            for section in self.accumulated_volume_sections:
                section_id = section['section_id']
                if section_id != "global_extrapolated":
                    try:
                        int(section_id)
                    except (ValueError, TypeError):
                        continue
                
                tree_id = section['tree_id']
                if tree_id not in trees_data:
                    trees_data[tree_id] = {
                        'timestamp': str(pd.Timestamp.now()) if 'pd' in globals() else str(datetime.now()),
                        'sections': []
                    }

                # Record the tree base Z used for DBH (derived from the saved
                # DBH target Z minus the reference height) so reloaded data can
                # reproduce the original DBH reference height without needing
                # the tree visualized again.
                _cd = section.get('circle_data') or {}
                _dbh_target_z = _cd.get('dbh_target_z')
                try:
                    _base_z = float(_dbh_target_z) - float(getattr(self, 'dbh_reference_height', 1.3)) if _dbh_target_z is not None else None
                except (ValueError, TypeError):
                    _base_z = None
                if _base_z is None:
                    try:
                        _base_z = float(_cd.get('min_z')) if _cd.get('min_z') is not None else None
                    except (ValueError, TypeError):
                        _base_z = None

                section_data = {
                    'section_id': section['section_id'],
                    'trunk_id': section.get('trunk_id'),
                    'branch_id': section.get('branch_id'),
                    'volume': section['volume'],
                    'point_color': section['point_color'],
                    'circle_color': section['circle_color'],
                    'num_points': len(section['points']),
                    'circle_data': section['circle_data'],
                    'tree_base_z': _base_z,
                    'extrapolated': section.get('extrapolated', False),
                    'original_height_range': section.get('original_height_range'),
                    'extrapolated_height_range': section.get('extrapolated_height_range'),
                    'original_min_z': section.get('original_min_z'),
                    'extrapolated_min_z': section.get('extrapolated_min_z'),
                    'num_extrapolated_circles': section.get('num_extrapolated_circles'),
                    'ground_level_used': section.get('ground_level_used')
                }
                trees_data[tree_id]['sections'].append(section_data)

            # Calculate totals
            for tree_id, tree_data in trees_data.items():
                tree_data['total_sections'] = len(tree_data['sections'])
                tree_data['total_volume'] = sum(s['volume'] for s in tree_data['sections'])
                tree_data['total_points'] = sum(s['num_points'] for s in tree_data['sections'])

            # Save files
            saved_count = 0
            for tree_id, tree_data in trees_data.items():
                filename = os.path.join(self.volume_folder_path, f"tree_{tree_id}.json")
                
                # Check for existing file and merge
                existing_data = None
                if os.path.exists(filename):
                    try:
                        with open(filename, 'r') as f:
                            existing_data = json.load(f)
                    except:
                        pass
                
                if existing_data and 'sections' in existing_data:
                    existing_data['sections'].extend(tree_data['sections'])
                    existing_data['total_sections'] = len(existing_data['sections'])
                    existing_data['total_volume'] = sum(s['volume'] for s in existing_data['sections'])
                    existing_data['total_points'] = sum(s['num_points'] for s in existing_data['sections'])
                    save_data = existing_data
                else:
                    save_data = tree_data
                
                with open(filename, 'w') as f:
                    json.dump(save_data, f, indent=2)
                
                saved_count += 1
                self.log_to_console(f"💾 Saved tree {tree_id}: {save_data['total_volume']:.4f} m³ → {filename}")

                # Also write branch and trunk CSV summaries for this tree
                try:
                    import csv

                    branch_csv = os.path.join(self.volume_folder_path, f"tree_{tree_id}_branchVolumes.csv")
                    trunk_csv = os.path.join(self.volume_folder_path, f"tree_{tree_id}_trunkVolumes.csv")

                    # Prepare branch rows
                    branch_rows = []
                    for sec in save_data.get('sections', []):
                        circ = sec.get('circle_data', {}) or {}
                        branch_rows.append({
                            'tree_id': tree_id,
                            'section_id': sec.get('section_id'),
                            'trunk_id': sec.get('trunk_id', None) if 'trunk_id' in sec else None,
                            'branch_id': sec.get('branch_id'),
                            'volume_m3': sec.get('volume', 0.0),
                            'num_points': sec.get('num_points', 0),
                            'min_z': circ.get('min_z', sec.get('original_min_z')),
                            'max_z': circ.get('max_z', sec.get('extrapolated_min_z')),
                            'height_m': circ.get('height_range', None)
                        })

                    # Write branch CSV
                    if branch_rows:
                        with open(branch_csv, 'w', newline='') as bf:
                            writer = csv.DictWriter(bf, fieldnames=list(branch_rows[0].keys()))
                            writer.writeheader()
                            for r in branch_rows:
                                writer.writerow(r)
                        self.log_to_console(f"💾 Branch CSV saved: {branch_csv}")

                    # Prepare trunk aggregation
                    trunk_totals = {}
                    for r in branch_rows:
                        trunk_key = r.get('trunk_id', None)
                        if trunk_key is None:
                            trunk_key = -1
                        trunk = trunk_totals.setdefault(trunk_key, {'total_volume': 0.0, 'num_branches': 0, 'total_points': 0})
                        trunk['total_volume'] += float(r.get('volume_m3', 0.0) or 0.0)
                        trunk['num_branches'] += 1
                        trunk['total_points'] += int(r.get('num_points', 0) or 0)

                    # Write trunk CSV
                    trunk_rows = []
                    for t_id, vals in trunk_totals.items():
                        trunk_rows.append({
                            'tree_id': tree_id,
                            'trunk_id': t_id,
                            'total_volume_m3': vals['total_volume'],
                            'num_branches': vals['num_branches'],
                            'total_points': vals['total_points']
                        })

                    if trunk_rows:
                        with open(trunk_csv, 'w', newline='') as tf:
                            writer = csv.DictWriter(tf, fieldnames=list(trunk_rows[0].keys()))
                            writer.writeheader()
                            for r in trunk_rows:
                                writer.writerow(r)
                        self.log_to_console(f"💾 Trunk CSV saved: {trunk_csv}")

                    # Add multi_trunk flag to saved JSON
                    multi_trunk = len([t for t in trunk_totals.keys() if t is not None and t != -1]) > 1
                    save_data['multi_trunk'] = multi_trunk
                    # Rewrite JSON with the flag
                    with open(filename, 'w') as f:
                        json.dump(save_data, f, indent=2)

                except Exception as csv_e:
                    self.log_to_console(f"⚠️ Failed to write branch/trunk CSVs for tree {tree_id}: {csv_e}")

            self.log_to_console(f"✅ All volume data saved to {self.volume_folder_path}")

        except Exception as e:
            self.log_to_console(f"❌ Error saving volume data: {str(e)}")
            raise


    def _save_batch_results(self, export_folder, volume_folder, batch_meta=None):
        """Save accumulated batch results as a single JSON and aggregated CSVs.

        export_folder: path to write CSVs (export/batch/<las_basename>)
        volume_folder: path to write JSON (volume/batch/<las_basename>)
        batch_meta: optional dict with metadata about the batch run
        """
        if not self.accumulated_volume_sections:
            self.log_to_console("⚠️ No accumulated volume sections to save for batch")
            return

        try:
            import json
            import csv
            import tempfile

            # Determine base name for files
            if hasattr(self, 'current_las_path') and self.current_las_path:
                las_basename = os.path.splitext(os.path.basename(self.current_las_path))[0]
            else:
                las_basename = 'batch'

            ts = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Build trees_data dictionary (exclude raw point arrays)
            trees_data = {}
            for sec in self.accumulated_volume_sections:
                section_id = sec.get('section_id')
                if section_id != 'global_extrapolated':
                    try:
                        int(section_id)
                    except (ValueError, TypeError):
                        continue

                tree_id = sec.get('tree_id')
                if tree_id not in trees_data:
                    trees_data[tree_id] = {'sections': [], 'timestamp': str(pd.Timestamp.now()) if 'pd' in globals() else str(datetime.now())}

                circ = sec.get('circle_data') or {}
                sec_entry = {
                    'section_id': sec.get('section_id'),
                    'trunk_id': sec.get('trunk_id', None),
                    'branch_id': sec.get('branch_id', None),
                    'volume': float(sec.get('volume', 0.0) or 0.0),
                    'num_points': int(len(sec.get('points') or [])),
                    'point_color': sec.get('point_color'),
                    'circle_color': sec.get('circle_color'),
                    'circle_data': circ,
                    'extrapolated': sec.get('extrapolated', False),
                    'original_height_range': sec.get('original_height_range'),
                    'extrapolated_height_range': sec.get('extrapolated_height_range'),
                    'original_min_z': sec.get('original_min_z'),
                    'extrapolated_min_z': sec.get('extrapolated_min_z'),
                    'num_extrapolated_circles': sec.get('num_extrapolated_circles'),
                    'ground_level_used': sec.get('ground_level_used')
                }
                trees_data[tree_id]['sections'].append(sec_entry)

            # Compute per-tree totals
            total_sections = 0
            total_volume = 0.0
            for tree_id, td in trees_data.items():
                td['total_sections'] = len(td['sections'])
                td['total_volume'] = sum(s['volume'] for s in td['sections'])
                td['total_points'] = sum(s['num_points'] for s in td['sections'])
                total_sections += td['total_sections']
                total_volume += td['total_volume']

            # Build batch JSON
            batch_id = ts
            batch_obj = {
                'batch_id': batch_id,
                'timestamp': datetime.now().isoformat(),
                'source_las': getattr(self, 'current_las_path', None),
                'batch_meta': batch_meta or {},
                'total_sections': total_sections,
                'total_volume': total_volume,
                'trees': trees_data
            }

            # Atomic write JSON
            json_name = os.path.join(volume_folder, f"{las_basename}_batch_{ts}.json")
            fd, tmp_json = tempfile.mkstemp(suffix='.json', prefix=f"{las_basename}_batch_{ts}_", dir=volume_folder)
            try:
                with os.fdopen(fd, 'w') as tf:
                    json.dump(batch_obj, tf, indent=2)
                os.replace(tmp_json, json_name)
            finally:
                if os.path.exists(tmp_json):
                    try:
                        os.remove(tmp_json)
                    except Exception:
                        pass

            # Prepare aggregated CSV rows
            branch_rows = []
            for tree_id, td in trees_data.items():
                for s in td['sections']:
                    circ = s.get('circle_data') or {}
                    branch_rows.append({
                        'tree_id': tree_id,
                        'section_id': s.get('section_id'),
                        'trunk_id': s.get('trunk_id'),
                        'branch_id': s.get('branch_id'),
                        'volume_m3': s.get('volume', 0.0),
                        'num_points': s.get('num_points', 0),
                        'min_z': circ.get('min_z', s.get('original_min_z')),
                        'max_z': circ.get('max_z', s.get('extrapolated_min_z')),
                        'height_m': circ.get('height_range', None)
                    })

            # Write branch CSV
            branch_csv = os.path.join(export_folder, f"{las_basename}_batch_{ts}_branches.csv")
            if branch_rows:
                tmp_branch = branch_csv + '.tmp'
                with open(tmp_branch, 'w', newline='') as bf:
                    writer = csv.DictWriter(bf, fieldnames=list(branch_rows[0].keys()))
                    writer.writeheader()
                    for r in branch_rows:
                        writer.writerow(r)
                os.replace(tmp_branch, branch_csv)

            # Aggregate trunk rows
            trunk_totals = {}
            for r in branch_rows:
                trunk_key = (r.get('tree_id'), r.get('trunk_id'))
                if trunk_key not in trunk_totals:
                    trunk_totals[trunk_key] = {'total_volume': 0.0, 'num_branches': 0, 'total_points': 0}
                trunk_totals[trunk_key]['total_volume'] += float(r.get('volume_m3') or 0.0)
                trunk_totals[trunk_key]['num_branches'] += 1
                trunk_totals[trunk_key]['total_points'] += int(r.get('num_points') or 0)

            trunk_rows = []
            for (tree_id, trunk_id), vals in trunk_totals.items():
                trunk_rows.append({
                    'tree_id': tree_id,
                    'trunk_id': trunk_id,
                    'total_volume_m3': vals['total_volume'],
                    'num_branches': vals['num_branches'],
                    'total_points': vals['total_points']
                })

            trunk_csv = os.path.join(export_folder, f"{las_basename}_batch_{ts}_trunks.csv")
            if trunk_rows:
                tmp_trunk = trunk_csv + '.tmp'
                with open(tmp_trunk, 'w', newline='') as tf:
                    writer = csv.DictWriter(tf, fieldnames=list(trunk_rows[0].keys()))
                    writer.writeheader()
                    for r in trunk_rows:
                        writer.writerow(r)
                os.replace(tmp_trunk, trunk_csv)

            self.log_to_console(f"💾 Batch JSON saved: {json_name}")
            if branch_rows:
                self.log_to_console(f"💾 Batch branch CSV saved: {branch_csv}")
            if trunk_rows:
                self.log_to_console(f"💾 Batch trunk CSV saved: {trunk_csv}")

            self.log_to_console(f"✅ Batch results saved to {export_folder} and {volume_folder}")

        except Exception as e:
            self.log_to_console(f"❌ Error saving batch results: {e}")
            raise

    def export_trunk_metrics(self):
        """Export one CSV row per trunk with location, total volume, and DBH to export folder."""
        if not self.accumulated_volume_sections:
            self.log_to_console("⚠️ No volume calculation data to export.")
            return

        try:
            trunk_summary, _, _ = self._build_trunk_volume_summary_table()
            trunk_dbh_summary, _, trunk_dbh_details = self._build_trunk_dbh_summary_table()

            if not trunk_summary:
                QMessageBox.warning(
                    self,
                    "No Trunk Data",
                    "No trunk-level data found. Run trunk/branch detection and volume calculation first."
                )
                return

            # Determine export directory and filename based on loaded point cloud
            if hasattr(self, 'current_las_path') and self.current_las_path:
                las_dir = os.path.dirname(self.current_las_path)
                las_basename = os.path.splitext(os.path.basename(self.current_las_path))[0]
                export_dir = os.path.join(las_dir, 'export')
            else:
                export_dir = os.path.join(os.getcwd(), 'export')
                las_basename = 'trunk_metrics'

            # Create export directory if it doesn't exist
            os.makedirs(export_dir, exist_ok=True)

            save_path = os.path.join(export_dir, f"{las_basename}_trunk_metrics.csv")

            rows = []
            # Build a lookup of DBH records by (tree_id, trunk_id) composite key.
            # These records are exactly what the blue trunk-DBH circles are drawn from,
            # so the export stays consistent with the visualized blue circles.
            dbh_by_key = {}
            for composite_key, dbh_rec in (trunk_dbh_details or {}).items():
                try:
                    key_parts = str(composite_key).rsplit('_', 1)
                    dbh_by_key[(key_parts[0], int(key_parts[1]))] = dbh_rec
                except (ValueError, TypeError, IndexError):
                    continue

            dbh_ref_height = float(getattr(self, 'dbh_reference_height', 1.3))

            for trunk_id in sorted(trunk_summary.keys(), key=lambda x: (isinstance(x, str), x)):
                # Skip non-numeric trunk IDs (e.g., 'Multiple Trunks (26)')
                try:
                    trunk_id_int = int(trunk_id)
                except (ValueError, TypeError):
                    self.log_to_console(f"⚠️ Skipping non-numeric trunk ID: {trunk_id}")
                    continue

                summary_rec = trunk_summary[trunk_id]

                # Collect associated tree IDs from accumulated sections for this trunk
                tree_ids = []
                import re
                for sec in self.accumulated_volume_sections:
                    if sec.get('trunk_id', None) == trunk_id and sec.get('tree_id', None) is not None:
                        try:
                            sec_tree_id = str(sec.get('tree_id'))
                            found_ids = [int(x) for x in re.findall(r'\d+', sec_tree_id)]
                            if found_ids:
                                tree_ids.extend(found_ids)
                            else:
                                tree_ids.append(int(sec_tree_id))
                        except (ValueError, TypeError):
                            pass
                tree_ids = sorted(set(tree_ids))

                # Fallbacks: if no tree_ids found in sections, use the tree_id stored in trunk_volume_summary
                if not tree_ids:
                    try:
                        tinfo = getattr(self, 'trunk_volume_summary', {}).get(int(trunk_id))
                        if tinfo is not None:
                            tid = tinfo.get('tree_id')
                            if tid is not None:
                                found_ids = [int(x) for x in re.findall(r'\d+', str(tid))]
                                if found_ids:
                                    tree_ids = found_ids
                                else:
                                    tree_ids = [int(tid)]
                    except Exception:
                        pass

                # Final fallback: use current_tree_id if available
                if not tree_ids and getattr(self, 'current_tree_id', None) is not None:
                    try:
                        curr_id_str = str(self.current_tree_id)
                        found_ids = [int(x) for x in re.findall(r'\d+', curr_id_str)]
                        if found_ids:
                            tree_ids = found_ids
                        else:
                            tree_ids = [int(self.current_tree_id)]
                    except Exception:
                        pass

                # Absolute fallback: store trunk_volume_summary tree_id or current_tree_id directly in the row if still empty
                resolved_tree_ids = ';'.join(str(t) for t in tree_ids) if tree_ids else ''
                if not resolved_tree_ids:
                    try:
                        tinfo = getattr(self, 'trunk_volume_summary', {}).get(int(trunk_id))
                        if tinfo is not None and tinfo.get('tree_id') is not None:
                            tid = tinfo.get('tree_id')
                            found_ids = [int(x) for x in re.findall(r'\d+', str(tid))]
                            if found_ids:
                                resolved_tree_ids = ';'.join(str(t) for t in found_ids)
                            else:
                                resolved_tree_ids = str(int(tid))
                    except Exception:
                        pass
                if not resolved_tree_ids and getattr(self, 'current_tree_id', None) is not None:
                    try:
                        curr_id_str = str(self.current_tree_id)
                        found_ids = [int(x) for x in re.findall(r'\d+', curr_id_str)]
                        if found_ids:
                            resolved_tree_ids = ';'.join(str(t) for t in found_ids)
                        else:
                            resolved_tree_ids = str(int(self.current_tree_id))
                    except Exception:
                        pass

                # Find the DBH record (blue circle) for this trunk. Trunk IDs can
                # repeat across trees, so prefer matching by (tree_id, trunk_id).
                dbh_rec = None
                primary_tree = tree_ids[0] if tree_ids else None
                if primary_tree is not None:
                    dbh_rec = dbh_by_key.get((str(primary_tree), trunk_id_int))
                if dbh_rec is None:
                    for (_tree_key, _trunk_key), _rec in dbh_by_key.items():
                        if _trunk_key == trunk_id_int:
                            dbh_rec = _rec
                            if primary_tree is None:
                                primary_tree = _tree_key
                            break

                dbh_cm = dbh_rec.get('dbh_cm') if dbh_rec else None
                dbh_section = dbh_rec.get('section_id', '') if dbh_rec else ''
                dbh_branch = dbh_rec.get('branch_id') if dbh_rec else None
                # DBH method: 'dbh_height' when a section contains the DBH
                # reference height; 'closest_section_fallback' when no trunk
                # points existed at that height and the closest section was used.
                if dbh_rec is None:
                    dbh_method = 'no_dbh_circle'
                elif dbh_rec.get('priority', 1) == 0:
                    dbh_method = 'dbh_height'
                else:
                    dbh_method = 'closest_section_fallback'

                # Location = centroid of the blue DBH circle when available.
                center_xyz = dbh_rec.get('center_xyz') if dbh_rec else None
                location_source = 'dbh_circle' if center_xyz is not None else 'section_avg_center'

                if center_xyz is None:
                    # Fallback location from section average centers for this trunk.
                    centers = []
                    z_refs = []
                    for sec in self.accumulated_volume_sections:
                        if sec.get('trunk_id', None) != trunk_id:
                            continue
                        circle_data = sec.get('circle_data') or {}
                        avg_center = circle_data.get('avg_center')
                        if avg_center is not None and len(avg_center) >= 2:
                            centers.append([float(avg_center[0]), float(avg_center[1])])
                            z_refs.append(float(circle_data.get('min_z', 0.0)))

                    if centers:
                        centers_arr = np.array(centers, dtype=float)
                        center_xyz = [
                            float(np.mean(centers_arr[:, 0])),
                            float(np.mean(centers_arr[:, 1])),
                            float(np.mean(z_refs)) if z_refs else 0.0,
                        ]
                    else:
                        center_xyz = [None, None, None]

                # Tree height from the currently visualized tree (ground to top).
                tree_height = getattr(self, 'current_tree_height', None)

                try:
                    rows.append({
                        'tree_ids': resolved_tree_ids,
                        'trunk_id': trunk_id_int,
                        'branch_id': dbh_branch,
                        'section': dbh_section,
                        'dbh_method': dbh_method,
                        'dbh_ref_height_m': dbh_ref_height,
                        'tree_height_m': float(tree_height) if tree_height is not None else None,
                        'location_x_m': center_xyz[0],
                        'location_y_m': center_xyz[1],
                        'location_z_m': center_xyz[2],
                        'location_source': location_source,
                        'total_volume_m3': float(summary_rec.get('total_volume', 0.0)),
                        'dbh_cm': float(dbh_cm) if dbh_cm is not None else None,
                        'num_branches': int(summary_rec.get('num_branches', 0)),
                        'total_points': int(summary_rec.get('total_points', 0)),
                    })
                except (ValueError, TypeError) as row_err:
                    self.log_to_console(f"⚠️ Skipping trunk {trunk_id} due to conversion error: {row_err}")
                    continue

            # Also include any trunk that has a blue DBH circle but no volume
            # summary row, so the report is complete relative to the circles shown.
            for (dbh_tree_key, dbh_trunk_key), dbh_rec in dbh_by_key.items():
                if dbh_trunk_key in trunk_summary:
                    continue
                dbh_cm = dbh_rec.get('dbh_cm')
                center_xyz = dbh_rec.get('center_xyz')
                dbh_branch = dbh_rec.get('branch_id')
                dbh_method = 'dbh_height' if dbh_rec.get('priority', 1) == 0 else 'closest_section_fallback'
                tree_height = getattr(self, 'current_tree_height', None)
                try:
                    rows.append({
                        'tree_ids': dbh_tree_key,
                        'trunk_id': dbh_trunk_key,
                        'branch_id': dbh_branch,
                        'section': dbh_section,
                        'dbh_method': dbh_method,
                        'dbh_ref_height_m': dbh_ref_height,
                        'tree_height_m': float(tree_height) if tree_height is not None else None,
                        'location_x_m': float(center_xyz[0]) if center_xyz and len(center_xyz) >= 2 else None,
                        'location_y_m': float(center_xyz[1]) if center_xyz and len(center_xyz) >= 2 else None,
                        'location_z_m': float(center_xyz[2]) if center_xyz and len(center_xyz) >= 3 else None,
                        'location_source': 'dbh_circle',
                        'total_volume_m3': 0.0,
                        'dbh_cm': float(dbh_cm) if dbh_cm is not None else None,
                        'num_branches': 0,
                        'total_points': 0,
                    })
                except (ValueError, TypeError) as row_err:
                    self.log_to_console(f"⚠️ Skipping DBH-only trunk {dbh_trunk_key} due to conversion error: {row_err}")
                    continue

            import csv

            # If file exists, read existing rows so we can preserve prior exports and backfill blank tree IDs.
            existing_rows = []
            if os.path.exists(save_path):
                try:
                    with open(save_path, 'r', newline='') as rf:
                        reader = csv.DictReader(rf)
                        for r in reader:
                            existing_rows.append(r)
                    self.log_to_console(f"ℹ️ Found existing export file; {len(existing_rows)} existing row(s) loaded for merge/dedup.")
                except Exception as e:
                    self.log_to_console(f"⚠️ Could not read existing export file: {e}")

            # Merge by (trunk_id, tree_id) composite key to keep trunks from different trees separate.
            merged_by_trunk = {}

            def _split_tree_ids(value):
                return [s.strip() for s in str(value or '').split(';') if s.strip()]

            def _get_merge_key(trunk_id, tree_ids_str):
                """Get a unique merge key based on trunk_id and primary tree_id."""
                tree_ids = _split_tree_ids(tree_ids_str)
                primary_tree_id = tree_ids[0] if tree_ids else None
                return (trunk_id, primary_tree_id)

            for r in existing_rows:
                try:
                    trunk_int = int(r.get('trunk_id'))
                    tree_ids_str = r.get('tree_ids', '')
                    key = _get_merge_key(trunk_int, tree_ids_str)
                except Exception:
                    continue
                merged_by_trunk[key] = dict(r)

            for r in rows:
                try:
                    trunk_int = int(r.get('trunk_id'))
                    tree_ids_str = r.get('tree_ids', '')
                    key = _get_merge_key(trunk_int, tree_ids_str)
                except Exception:
                    continue

                new_tree_ids = _split_tree_ids(tree_ids_str)
                existing = merged_by_trunk.get(key)
                if existing is None:
                    merged_by_trunk[key] = dict(r)
                    continue

                # Row already exists for this trunk+tree combo; update with new data
                old_tree_ids = _split_tree_ids(existing.get('tree_ids', ''))
                combined_tree_ids = sorted(set(old_tree_ids + new_tree_ids), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
                existing['tree_ids'] = ';'.join(combined_tree_ids)

                for key_name, value in r.items():
                    if key_name == 'tree_ids':
                        continue
                    if value not in (None, ''):
                        existing[key_name] = value

            rows_to_write = [merged_by_trunk[k] for k in sorted(merged_by_trunk.keys(), key=lambda x: (x[0], int(x[1]) if x[1] and str(x[1]).isdigit() else x[1]))]

            with open(save_path, 'w', newline='') as f:
                fieldnames = [ 'tree_height_m',
                    'tree_ids', 'trunk_id', 'branch_id',
                    'section', 'dbh_method', 'dbh_ref_height_m',
                    'location_x_m', 'location_y_m', 'location_z_m', 'location_source',
                    'total_volume_m3', 'dbh_cm',
                    'num_branches', 'total_points'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows_to_write:
                    writer.writerow(row)

            self.log_to_console(f"💾 Wrote {len(rows_to_write)} merged trunk row(s) to: {save_path}")

        except Exception as e:
            self.log_to_console(f"❌ Error exporting trunk metrics: {str(e)}")
            QMessageBox.critical(self, "Export Error", f"Failed to export trunk metrics:\n{str(e)}")

    def _display_batch_completion_summary(self, processed_count, total_count, skipped_trees, batch_start_dt, batch_end_dt, elapsed_seconds):
        """Display completion summary in console."""
        import time

        elapsed_seconds = max(elapsed_seconds, 1e-9)
        elapsed_minutes = elapsed_seconds / 60.0
        average_trees_per_min = processed_count / elapsed_minutes if elapsed_minutes > 0 else 0.0
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))

        summary = f"\n\n{'='*60}\n📊 BATCH ANALYSIS COMPLETE\n{'='*60}\n"
        summary += f"Successfully processed: {processed_count}/{total_count} trees\n"
        summary += f"Skipped: {len(skipped_trees)} trees\n"
        summary += f"Time elapsed: {elapsed_str}\n"
        summary += f"Average: {average_trees_per_min:.1f} trees/min\n"
        summary += f"{'='*60}\n"
        
        self.log_to_console(summary)

    # ======================== PHASE 1: TRUNK DETECTION ========================

    def _build_z_slices(self, points, slice_height_m):
        """Build z-slice boundaries for a given slice height.
        
        Returns:
            z_coords, min_z, max_z, slice_boundaries, num_slices
        """
        z_coords = points[:, 2]
        min_z = np.min(z_coords)
        max_z = np.max(z_coords)
        slice_boundaries = np.arange(min_z, max_z + slice_height_m, slice_height_m)
        num_slices = len(slice_boundaries) - 1
        return z_coords, min_z, max_z, slice_boundaries, num_slices

    def _cluster_xy_in_slice(self, slice_points_xy, eps_m, min_samples):
        """Run DBSCAN on 2D XY coordinates in a horizontal slice.
        
        Returns:
            labels, num_clusters, num_noise
        """
        dbscan = DBSCAN(eps=eps_m, min_samples=min_samples)
        labels = dbscan.fit_predict(slice_points_xy)
        num_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        num_noise = np.sum(labels == -1)
        return labels, num_clusters, num_noise

    class SliceDBSCANViewer(QDialog):
        """Dialog to step through per-slice DBSCAN results."""
        def __init__(self, parent, slices):
            super().__init__(parent)
            self.slices = slices
            self.idx = 0
            self.setWindowTitle("Slice DBSCAN Viewer")
            self.resize(600, 520)

            layout = QVBoxLayout(self)
            control = QHBoxLayout()
            self.prev_btn = QPushButton("Prev")
            self.next_btn = QPushButton("Next")
            self.info_label = QLabel("")
            control.addWidget(self.prev_btn)
            control.addWidget(self.next_btn)
            control.addWidget(self.info_label)
            control.addStretch()
            layout.addLayout(control)

            self.fig = Figure(figsize=(5, 4))
            self.canvas = FigureCanvas(self.fig)
            layout.addWidget(self.canvas)

            self.prev_btn.clicked.connect(self.prev)
            self.next_btn.clicked.connect(self.next)

            self.update_plot()

        def update_plot(self):
            self.fig.clf()
            ax = self.fig.add_subplot(111)
            s = self.slices[self.idx]
            pts = s['points']
            labs = s['labels']
            if pts is None or len(pts) == 0:
                ax.text(0.5, 0.5, 'No points in this slice', ha='center', va='center')
            else:
                try:
                    import matplotlib.cm as cm
                    unique = np.unique(labs)
                    colors = plt.get_cmap('tab20')(np.linspace(0, 1, max(2, len(unique))))
                    for i, uid in enumerate(unique):
                        mask = labs == uid
                        if uid == -1:
                            ax.scatter(pts[mask, 0], pts[mask, 1], c='k', s=6, label='noise')
                        else:
                            c = colors[i % len(colors)]
                            ax.scatter(pts[mask, 0], pts[mask, 1], color=[c], s=8, label=f'c{uid}')
                except Exception:
                    ax.scatter(pts[:, 0], pts[:, 1], s=8)

                ax.set_xlabel('X')
                ax.set_ylabel('Y')
                ax.set_aspect('equal', adjustable='datalim')
                ax.legend(loc='upper right', fontsize='small')

            ax.set_title(f"Slice {s['slice_idx']}: Z {s['z_start']:.2f}-{s['z_end']:.2f} | clusters {s['num_clusters']} noise {s['num_noise']}")
            self.canvas.draw()
            self.info_label.setText(f"{self.idx+1}/{len(self.slices)}")

        def prev(self):
            if self.idx > 0:
                self.idx -= 1
                self.update_plot()

        def next(self):
            if self.idx < len(self.slices) - 1:
                self.idx += 1
                self.update_plot()

    def detect_trunks_in_slices(self):
        """Detect individual trunks in the base zone using horizontal slicing + DBSCAN + vertical tracking.
        
        Populates self.trunk_assignment with trunk IDs in the base zone.
        """
        if self.current_tree_points is None:
            QMessageBox.warning(self, "Warning", "No trunk visualized. Please visualize a trunk first.")
            return

        try:
            self.log_to_console(f"\n{'='*60}")
            self.log_to_console(f"🌳 PHASE 1: Detecting individual trunks in base zone...")
            self.log_to_console(f"{'='*60}")

            params = self.trunk_detection_params
            params['slice_height_cm'] = self.trunk_slice_height_input.value()
            params['base_zone_height_m'] = float(self.trunk_base_zone_input.value())
            params['eps_m'] = float(self.trunk_eps_input.value())
            params['min_samples'] = int(self.trunk_min_samples_input.value())
            params['merge_dist_m'] = float(self.trunk_merge_dist_input.value())
            params['min_trunk_points'] = int(self.trunk_min_points_input.value())
            params['min_vertical_span_m'] = float(self.trunk_min_span_input.value())
            params['full_height_assign_dist_m'] = float(self.trunk_full_assign_input.value())

            # Record the parameter set used for this detection run and compare to last run.
            try:
                current_trunk_params = {
                    'slice_height_cm': int(params.get('slice_height_cm', 0)),
                    'base_zone_height_m': float(params.get('base_zone_height_m', 0.0)),
                    'eps_m': float(params.get('eps_m', 0.0)),
                    'min_samples': int(params.get('min_samples', 0)),
                    'merge_dist_m': float(params.get('merge_dist_m', 0.0)),
                    'min_trunk_points': int(params.get('min_trunk_points', 0)),
                    'min_vertical_span_m': float(params.get('min_vertical_span_m', 0.0)),
                    'full_height_assign_dist_m': float(params.get('full_height_assign_dist_m', 0.0))
                }
            except Exception:
                current_trunk_params = None

            slice_height_m = params['slice_height_cm'] / 100.0
            base_zone_height_m = params['base_zone_height_m']
            eps_m = params['eps_m']
            min_samples = params['min_samples']
            merge_dist_m = params['merge_dist_m']
            min_trunk_points = params['min_trunk_points']
            min_vertical_span_m = params['min_vertical_span_m']

            points = self.current_tree_points
            z_coords = points[:, 2]
            min_z = np.min(z_coords)
            max_z = np.max(z_coords)
            trunk_height = max_z - min_z

            self.log_to_console(f"📏 Trunk height: {trunk_height:.2f}m | Base zone: {base_zone_height_m:.2f}m")
            self.log_to_console(f"🔍 Slice height: {params['slice_height_cm']}cm | DBSCAN eps: {eps_m:.2f}m, min_samples: {min_samples}")

            # Use full height when base zone is set to 0.0, otherwise cap by the requested value.
            zone_height = trunk_height if base_zone_height_m <= 0 else min(base_zone_height_m, trunk_height)
            zone_max_z = min_z + zone_height
            self.log_to_console(f"🎯 Base zone Z range: {min_z:.2f}m to {zone_max_z:.2f}m")

            # Build slices in base zone only
            z_coords_zone, _, _, slice_boundaries, num_slices = self._build_z_slices(
                points[z_coords <= zone_max_z], slice_height_m
            )
            
            self.log_to_console(f"📊 Total base slices: {num_slices}")

            # Initialize trunk assignment for base zone
            base_zone_mask = z_coords <= zone_max_z
            base_zone_indices = np.where(base_zone_mask)[0]
            base_zone_points = points[base_zone_indices]
            
            point_to_trunk_base = np.full(len(base_zone_indices), -1, dtype=int)
            next_trunk_id = 0
            prev_slice_clusters = {}  # Maps trunk_id to centroid
            self.log_to_console(f"\n🔄 Running DBSCAN per base slice with vertical tracking...")

            # Collect per-slice debug data for viewer
            slices_debug = []

            # Process each base zone slice
            for slice_idx in range(num_slices):
                z_start = slice_boundaries[slice_idx]
                z_end = slice_boundaries[slice_idx + 1]

                # Get points in this slice from base zone
                slice_mask = (z_coords_zone >= z_start) & (z_coords_zone < z_end)
                if slice_idx == num_slices - 1:
                    slice_mask = (z_coords_zone >= z_start) & (z_coords_zone <= z_end)

                slice_indices_local = np.where(slice_mask)[0]
                slice_indices_global = base_zone_indices[slice_indices_local]
                slice_points = base_zone_points[slice_indices_local]

                if len(slice_points) < min_samples:
                    self.log_to_console(f"  Slice {slice_idx}: < {min_samples} points, skipping")
                    # Save empty debug entry
                    slices_debug.append({
                        'slice_idx': slice_idx,
                        'z_start': z_start,
                        'z_end': z_end,
                        'points': np.empty((0, 2)),
                        'labels': np.array([], dtype=int),
                        'num_clusters': 0,
                        'num_noise': 0
                    })
                    continue

                # Compute radial coordinates from slice center
                center_x = np.mean(slice_points[:, 0])
                center_y = np.mean(slice_points[:, 1])
                radial_coords = np.column_stack([
                    slice_points[:, 0] - center_x,
                    slice_points[:, 1] - center_y
                ])

                # Run DBSCAN
                local_labels, num_clusters, num_noise = self._cluster_xy_in_slice(radial_coords, eps_m, min_samples)
                self.log_to_console(f"  Slice {slice_idx}: {num_clusters} clusters, {num_noise} noise")

                # Save debug data (use absolute XY for display)
                slices_debug.append({
                    'slice_idx': slice_idx,
                    'z_start': z_start,
                    'z_end': z_end,
                    'points': slice_points[:, :2].copy(),
                    'labels': local_labels.copy(),
                    'num_clusters': num_clusters,
                    'num_noise': num_noise
                })

                # Assign trunk IDs with vertical tracking
                current_slice_clusters = {}
                for local_id in set(local_labels):
                    if local_id == -1:
                        continue

                    cluster_mask = local_labels == local_id
                    cluster_indices_local = slice_indices_local[cluster_mask]
                    cluster_indices_global = slice_indices_global[cluster_mask]
                    cluster_points = slice_points[cluster_mask]

                    centroid = np.mean(cluster_points[:, :2], axis=0)

                    # Match to previous slice cluster
                    trunk_id = None
                    if prev_slice_clusters:
                        min_dist = float('inf')
                        closest_prev_id = None
                        for prev_id, prev_centroid in prev_slice_clusters.items():
                            dist = np.linalg.norm(centroid - prev_centroid)
                            if dist < min_dist:
                                min_dist = dist
                                closest_prev_id = prev_id

                        if closest_prev_id is not None and min_dist < merge_dist_m:
                            trunk_id = closest_prev_id
                            self.log_to_console(f"    Cluster {local_id}: Merged with trunk {trunk_id} (dist={min_dist:.3f}m)")

                    if trunk_id is None:
                        trunk_id = next_trunk_id
                        next_trunk_id += 1
                        self.log_to_console(f"    Cluster {local_id}: New trunk {trunk_id}")

                    # Assign trunk ID to points in base zone
                    point_to_trunk_base[cluster_indices_local] = trunk_id
                    current_slice_clusters[trunk_id] = centroid

                prev_slice_clusters = current_slice_clusters

            # Only show the per-slice viewer in Raw mode so it does not interrupt normal detection.
            try:
                show_raw_view = bool(getattr(self, 'raw_trunk_view_checkbox', None) and self.raw_trunk_view_checkbox.isChecked())
                if show_raw_view and slices_debug:
                    viewer = self.SliceDBSCANViewer(self, slices_debug)
                    viewer.exec()
            except Exception:
                # If viewer fails, continue silently but log
                self.log_to_console("⚠️ Failed to open slice DBSCAN viewer")

            # Save raw base-zone assignment (before filtering) for QA visualization
            try:
                self.raw_trunk_base_assignment = point_to_trunk_base.copy()
                self.raw_base_zone_indices = base_zone_indices.copy()
                self.raw_slices_debug = slices_debug
            except Exception:
                pass

            # Filter trunks by quality criteria
            unique_trunks = np.unique(point_to_trunk_base)
            valid_trunks = []

            self.log_to_console(f"\n✅ Base zone clustering complete. Filtering by quality criteria...")
            self.log_to_console(f"   Min points: {min_trunk_points} | Min vertical span: {min_vertical_span_m:.2f}m")

            for trunk_id in unique_trunks:
                if trunk_id == -1:
                    continue

                mask = point_to_trunk_base == trunk_id
                trunk_points = base_zone_points[mask]
                trunk_size = len(trunk_points)
                z_span = np.max(trunk_points[:, 2]) - np.min(trunk_points[:, 2])

                if trunk_size >= min_trunk_points and z_span >= min_vertical_span_m:
                    valid_trunks.append(trunk_id)
                    self.log_to_console(f"  Trunk {trunk_id}: {trunk_size} points, z_span={z_span:.2f}m ✓")
                else:
                    self.log_to_console(f"  Trunk {trunk_id}: {trunk_size} points, z_span={z_span:.2f}m ✗ (rejected)")

            # Re-index valid trunks to 0..N-1
            trunk_remap = {old_id: new_id for new_id, old_id in enumerate(valid_trunks)}
            remapped_base = np.full(len(point_to_trunk_base), -1, dtype=int)
            for old_id, new_id in trunk_remap.items():
                remapped_base[point_to_trunk_base == old_id] = new_id

            point_to_trunk_base = remapped_base

            # Store base zone assignment and prepare for full height extension
            self.trunk_assignment = np.full(len(points), -1, dtype=int)
            self.trunk_assignment[base_zone_indices] = point_to_trunk_base

            self.log_to_console(f"\n📌 Base zone assignment complete: {len(valid_trunks)} valid trunks detected")
            self.log_to_console(f"   Noise points in base: {np.sum(point_to_trunk_base == -1)}")

            # Extend assignment to full height
            self._assign_points_to_trunks_full_height()

            # Auto-visualize detected trunks immediately after detection
            self.log_to_console(f"\n✅ Trunk detection complete. Auto-visualizing trunks...")
            self.visualize_trunks_from_assignment()
            # Compare current params with last used params; only bump version when parameters changed
            try:
                if current_trunk_params is not None and current_trunk_params != getattr(self, '_last_trunk_detection_params', None):
                    self._last_trunk_detection_params = current_trunk_params
                    try:
                        self._trunk_detection_version = int(getattr(self, '_trunk_detection_version', 0)) + 1
                    except Exception:
                        self._trunk_detection_version = getattr(self, '_trunk_detection_version', 0) + 1
                    self.log_to_console(f"🔁 Trunk detection parameters changed; version updated: {self._trunk_detection_version}")
                else:
                    self.log_to_console("ℹ️ Trunk detection run used same parameters as last run; detection version unchanged.")
            except Exception:
                # On any error, conservatively bump version
                try:
                    self._trunk_detection_version = int(getattr(self, '_trunk_detection_version', 0)) + 1
                except Exception:
                    self._trunk_detection_version = getattr(self, '_trunk_detection_version', 0) + 1
                self.log_to_console(f"🔁 Trunk detection version updated (fallback): {self._trunk_detection_version}")

        except Exception as e:
            self.log_to_console(f"❌ Error detecting trunks in base zone: {str(e)}")
            import traceback
            self.log_to_console(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Failed to detect trunks:\n{str(e)}")

    def _assign_points_to_trunks_full_height(self):
        """Extend trunk assignment from base zone to full tree height using nearest neighbor.
        
        Uses self.trunk_assignment (populated in base zone by detect_trunks_in_slices).
        Assigns remaining points (-1) to nearest trunk trajectory.
        """
        if self.trunk_assignment is None or self.current_tree_points is None:
            self.log_to_console("⚠️ Cannot extend trunk assignment: base zone assignment not ready")
            return

        points = self.current_tree_points
        unassigned_mask = self.trunk_assignment == -1

        if not np.any(unassigned_mask):
            self.log_to_console("ℹ️ All points assigned in base zone. No extension needed.")
            return

        self.log_to_console(f"\n🔗 Extending trunk assignment to full height...")
        max_assign_dist = self.trunk_detection_params['full_height_assign_dist_m']

        # Build KDTree of assigned points per trunk
        assigned_mask = self.trunk_assignment >= 0
        assigned_points = points[assigned_mask]
        assigned_trunk_ids = self.trunk_assignment[assigned_mask]
        assigned_tree = KDTree(assigned_points[:, :2])  # XY only

        unassigned_indices = np.where(unassigned_mask)[0]
        unassigned_points = points[unassigned_indices]

        # For each unassigned point, find nearest assigned point and use its trunk ID
        distances, indices = assigned_tree.query(unassigned_points[:, :2], k=1)

        extended_count = 0
        for i, (dist, idx) in enumerate(zip(distances, indices)):
            if dist <= max_assign_dist:
                nearest_trunk = assigned_trunk_ids[idx]
                self.trunk_assignment[unassigned_indices[i]] = nearest_trunk
                extended_count += 1

        self.log_to_console(f"   Extended {extended_count}/{len(unassigned_indices)} unassigned points")
        self.log_to_console(f"   Points still unassigned (noise): {np.sum(self.trunk_assignment == -1)}")

    def visualize_trunks_from_assignment(self):
        """Visualize trunks using colors from self.trunk_assignment (Phase 2 QA visualization).
        
        Each trunk gets a distinct color.
        """
        if self.trunk_assignment is None:
            self.log_to_console("⚠️ No trunk assignment available for visualization")
            return

        try:
            self.log_to_console(f"\n🎨 Visualizing trunks...")
            show_raw = bool(getattr(self, 'raw_trunk_view_checkbox', None) and self.raw_trunk_view_checkbox.isChecked())

            # Clear current visualization
            self.plotter.clear()
            self._restore_gdb_layers()

            # Show raw detections when requested, otherwise show filtered trunks.
            if show_raw and hasattr(self, 'raw_trunk_base_assignment'):
                self.log_to_console("   Raw view enabled: showing raw base-zone detections")

                raw_assign = self.raw_trunk_base_assignment
                raw_indices = self.raw_base_zone_indices
                raw_unique = np.unique(raw_assign)
                raw_unique = raw_unique[raw_unique >= 0]
                num_raw = len(raw_unique)

                # Create colors
                import matplotlib.cm as cm
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    if num_raw <= 10:
                        cmap = plt.get_cmap('tab10')
                    elif num_raw <= 20:
                        cmap = plt.get_cmap('tab20')
                    else:
                        cmap = plt.get_cmap('hsv')

                colors = cmap(np.linspace(0, 1, max(1, num_raw)))

                # Render each raw detected trunk (base zone only)
                for i, raw_id in enumerate(raw_unique):
                    mask = raw_assign == raw_id
                    global_inds = raw_indices[mask]
                    trunk_points = self.current_tree_points[global_inds]

                    if len(trunk_points) > 0:
                        color = colors[i % len(colors)]
                        rgb_color = [float(color[0]), float(color[1]), float(color[2])]
                        self.plotter.add_points(
                            trunk_points,
                            color=rgb_color,
                            point_size=5,
                            name=f'RawTrunk_{raw_id}'
                        )
                        self.log_to_console(f"RAW {raw_id:<8} {len(trunk_points):<8} (base-zone)")

                # Add raw noise in base zone
                noise_mask = raw_assign == -1
                if np.any(noise_mask):
                    noise_global = raw_indices[noise_mask]
                    noise_points = self.current_tree_points[noise_global]
                    self.plotter.add_points(
                        noise_points,
                        color=[0.5, 0.5, 0.5],
                        point_size=3,
                        name='RawNoise'
                    )
                    self.log_to_console(f"{'RAW_NOISE':<10} {len(noise_points):<8} (base-zone)")

                # Update viewer
                self.plotter.reset_camera()
                self.plotter.update()
                self.log_to_console("\n✅ Raw base-zone trunk visualization complete (unfiltered results).")
                return

            # Get unique trunk IDs
            unique_trunks = np.unique(self.trunk_assignment)
            unique_trunks = unique_trunks[unique_trunks >= 0]

            num_trunks = len(unique_trunks)
            self.log_to_console(f"   Rendering {num_trunks} trunks...")

            # If no filtered trunks found, but raw base-zone detections exist, show them for QA
            if num_trunks == 0 and hasattr(self, 'raw_trunk_base_assignment'):
                self.log_to_console("   No filtered trunks — falling back to raw base-zone clusters for QA visualization")

                raw_assign = self.raw_trunk_base_assignment
                raw_indices = self.raw_base_zone_indices
                raw_unique = np.unique(raw_assign)
                raw_unique = raw_unique[raw_unique >= 0]
                num_raw = len(raw_unique)

                # Create colors
                import matplotlib.cm as cm
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    if num_raw <= 10:
                        cmap = plt.get_cmap('tab10')
                    elif num_raw <= 20:
                        cmap = plt.get_cmap('tab20')
                    else:
                        cmap = plt.get_cmap('hsv')

                colors = cmap(np.linspace(0, 1, max(1, num_raw)))

                # Render each raw detected trunk (base zone only)
                for i, raw_id in enumerate(raw_unique):
                    mask = raw_assign == raw_id
                    global_inds = raw_indices[mask]
                    trunk_points = self.current_tree_points[global_inds]

                    if len(trunk_points) > 0:
                        color = colors[i % len(colors)]
                        rgb_color = [float(color[0]), float(color[1]), float(color[2])]
                        self.plotter.add_points(
                            trunk_points,
                            color=rgb_color,
                            point_size=5,
                            name=f'RawTrunk_{raw_id}'
                        )
                        self.log_to_console(f"RAW {raw_id:<8} {len(trunk_points):<8} (base-zone)")

                # Add raw noise in base zone
                noise_mask = raw_assign == -1
                if np.any(noise_mask):
                    noise_global = raw_indices[noise_mask]
                    noise_points = self.current_tree_points[noise_global]
                    self.plotter.add_points(
                        noise_points,
                        color=[0.5, 0.5, 0.5],
                        point_size=3,
                        name='RawNoise'
                    )
                    self.log_to_console(f"{'RAW_NOISE':<10} {len(noise_points):<8} (base-zone)")

                # Update viewer
                self.plotter.reset_camera()
                self.plotter.update()
                self.log_to_console("\n✅ Raw base-zone trunk visualization complete (unfiltered results).")
                return

            # Create color palette
            import matplotlib.cm as cm
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                if num_trunks <= 10:
                    cmap = plt.get_cmap('tab10')
                elif num_trunks <= 20:
                    cmap = plt.get_cmap('tab20')
                else:
                    cmap = plt.get_cmap('hsv')

            colors = cmap(np.linspace(0, 1, num_trunks))

            # Log trunk statistics
            self.log_to_console(f"\n📋 TRUNK DETAILS:")
            self.log_to_console(f"{'Trunk ID':<10} {'Size':<8} {'Min Z':<8} {'Max Z':<8} {'Height':<8}")
            self.log_to_console(f"-" * 50)

            # Render each trunk
            for i, trunk_id in enumerate(unique_trunks):
                mask = self.trunk_assignment == trunk_id
                trunk_points = self.current_tree_points[mask]

                if len(trunk_points) > 0:
                    size = len(trunk_points)
                    min_z = np.min(trunk_points[:, 2])
                    max_z = np.max(trunk_points[:, 2])
                    height = max_z - min_z

                    color = colors[i % len(colors)]
                    rgb_color = [float(color[0]), float(color[1]), float(color[2])]

                    self.plotter.add_points(
                        trunk_points,
                        color=rgb_color,
                        point_size=5,
                        name=f'Trunk_{trunk_id}'
                    )

                    # Add trunk ID label at the centroid of the trunk
                    centroid = np.mean(trunk_points, axis=0)
                    try:
                        self.plotter.add_point_labels(
                            np.array([centroid]),
                            [f'T{trunk_id}'],
                            font_size=14,
                            text_color='white',
                            always_visible=True,
                            name=f'Label_Trunk_{trunk_id}'
                        )
                    except Exception:
                        pass  # Label failed; skip silently

                    self.log_to_console(f"{trunk_id:<10} {size:<8} {min_z:<8.2f} {max_z:<8.2f} {height:<8.2f}")

            # Add legend
            try:
                self.plotter.add_legend()
            except:
                pass

            self.plotter.reset_camera()
            self.plotter.update()
            
            # Noise points
            noise_mask = self.trunk_assignment == -1
            if np.any(noise_mask):
                self.log_to_console(f"{'NOISE':<10} {np.sum(noise_mask):<8}")

            self.log_to_console(f"\n✅ Trunk visualization complete!")

        except Exception as e:
            self.log_to_console(f"❌ Error visualizing trunks: {str(e)}")
            import traceback
            self.log_to_console(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Failed to visualize trunks:\n{str(e)}")

    # ======================== EXISTING BRANCH DETECTION (to be refactored in Phase 3) ========================

    def detect_branch_clusters_in_slices(self):
        """Detect individual branches using DBSCAN on radial coordinates within each height slice."""
        if self.current_tree_points is None:
            QMessageBox.warning(self, "Warning", "No trunk visualized. Please visualize a trunk first.")
            return
        if self.trunk_assignment is None or len(self.trunk_assignment) != len(self.current_tree_points):
            QMessageBox.warning(self, "Warning", "No trunk assignment available. Please run trunk detection first.")
            return
        
        try:
            self.log_to_console(f"\n{'='*60}")
            self.log_to_console(f"🌳 Detecting branches using radial DBSCAN clustering per trunk...")
            self.log_to_console(f"{'='*60}")
            
            # Get slice height parameters (same as visualization)
            slice_height_cm = self.slice_height_input.value()
            slice_height_m = slice_height_cm / 100.0
            branch_eps = float(self.branch_eps_input.value())
            branch_min_samples = int(self.branch_min_samples_input.value())
            branch_merge_dist = float(self.branch_merge_dist_input.value())

            # Capture current branch detection params and compare to last run
            try:
                current_branch_params = {
                    'slice_height_cm': int(slice_height_cm),
                    'branch_eps': float(branch_eps),
                    'branch_min_samples': int(branch_min_samples),
                    'branch_merge_dist': float(branch_merge_dist)
                }
            except Exception:
                current_branch_params = None
            
            # Extract coordinates
            points = self.current_tree_points
            trunk_ids = np.unique(self.trunk_assignment)
            trunk_ids = trunk_ids[trunk_ids >= 0]

            if len(trunk_ids) == 0:
                QMessageBox.warning(self, "Warning", "No trunk IDs found. Please run trunk detection first.")
                return
            
            # Initialize branch assignment array (-1 = noise, >=0 = branch_id)
            point_to_branch = np.full(len(points), -1, dtype=int)
            self.branch_meta = {}
            next_branch_id = 0

            total_branches_detected = 0
            total_classified_points = 0

            self.log_to_console(f"📏 Slice height: {slice_height_cm}cm | Branch DBSCAN eps={branch_eps:.2f}m | min_samples={branch_min_samples}")
            self.log_to_console(f"🔎 Processing {len(trunk_ids)} trunk(s) independently...")

            # Process each trunk independently so branch IDs belong to a specific trunk.
            for trunk_id in trunk_ids:
                trunk_mask = self.trunk_assignment == trunk_id
                trunk_indices = np.where(trunk_mask)[0]
                trunk_points = points[trunk_indices]

                if len(trunk_points) < branch_min_samples:
                    self.log_to_console(f"  Trunk {trunk_id}: < {branch_min_samples} points, skipping")
                    continue

                trunk_z = trunk_points[:, 2]
                min_z = np.min(trunk_z)
                max_z = np.max(trunk_z)
                slice_boundaries = np.arange(min_z, max_z + slice_height_m, slice_height_m)
                if len(slice_boundaries) < 2:
                    slice_boundaries = np.array([min_z, max_z + slice_height_m], dtype=float)
                num_slices = len(slice_boundaries) - 1

                self.log_to_console(f"  Trunk {trunk_id}: slice height {slice_height_cm}cm | slices {num_slices} | z=[{min_z:.2f}, {max_z:.2f}]")

                # Track clusters from previous slice for vertical connectivity within this trunk only.
                prev_slice_clusters = {}
                trunk_local_branch_id = 0

                for slice_idx in range(num_slices):
                    z_start = slice_boundaries[slice_idx]
                    z_end = slice_boundaries[slice_idx + 1]

                    slice_mask = (trunk_z >= z_start) & (trunk_z < z_end)
                    if slice_idx == num_slices - 1:
                        slice_mask = (trunk_z >= z_start) & (trunk_z <= z_end)

                    slice_local_indices = np.where(slice_mask)[0]
                    slice_points = trunk_points[slice_local_indices]

                    if len(slice_points) < branch_min_samples:
                        self.log_to_console(f"    Slice {slice_idx}: < {branch_min_samples} points, skipping")
                        continue

                    center_x = np.mean(slice_points[:, 0])
                    center_y = np.mean(slice_points[:, 1])

                    radial_coords = np.column_stack([
                        slice_points[:, 0] - center_x,
                        slice_points[:, 1] - center_y
                    ])

                    dbscan = DBSCAN(eps=branch_eps, min_samples=branch_min_samples)
                    local_clusters = dbscan.fit_predict(radial_coords)

                    num_clusters = len(set(local_clusters)) - (1 if -1 in local_clusters else 0)
                    num_noise = np.sum(local_clusters == -1)
                    self.log_to_console(f"    Slice {slice_idx}: {num_clusters} clusters, {num_noise} noise points")

                    current_slice_clusters = {}
                    for local_id in np.unique(local_clusters):
                        if local_id == -1:
                            continue

                        cluster_mask = local_clusters == local_id
                        cluster_local_indices = slice_local_indices[cluster_mask]
                        cluster_indices = trunk_indices[cluster_local_indices]
                        cluster_points = slice_points[cluster_mask]

                        centroid = np.mean(cluster_points[:, :2], axis=0)
                        cluster_z_min = float(np.min(cluster_points[:, 2]))
                        cluster_z_max = float(np.max(cluster_points[:, 2]))

                        branch_id = None
                        if prev_slice_clusters:
                            min_dist = float('inf')
                            closest_prev_id = None
                            for prev_id, prev_centroid in prev_slice_clusters.items():
                                dist = np.linalg.norm(centroid - prev_centroid)
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_prev_id = prev_id

                            if closest_prev_id is not None and min_dist < branch_merge_dist:
                                branch_id = closest_prev_id
                                meta = self.branch_meta.get(branch_id, {})
                                local_branch_id = meta.get('local_id', branch_id)
                                self.log_to_console(
                                    f"      Cluster {local_id}: Merged with trunk {trunk_id} branch B{local_branch_id} "
                                    f"(global {branch_id}, dist={min_dist:.3f}m)"
                                )

                        if branch_id is None:
                            branch_id = next_branch_id
                            next_branch_id += 1
                            local_branch_id = trunk_local_branch_id
                            trunk_local_branch_id += 1
                            self.branch_meta[branch_id] = {
                                'trunk_id': int(trunk_id),
                                'local_id': int(local_branch_id),
                                'point_count': 0,
                                'z_span': (cluster_z_min, cluster_z_max)
                            }
                            self.log_to_console(
                                f"      Cluster {local_id}: New branch T{trunk_id}.B{local_branch_id} (global {branch_id})"
                            )

                        point_to_branch[cluster_indices] = branch_id
                        current_slice_clusters[branch_id] = centroid

                        meta = self.branch_meta.setdefault(branch_id, {
                            'trunk_id': int(trunk_id),
                            'local_id': int(branch_id),
                            'point_count': 0,
                            'z_span': (cluster_z_min, cluster_z_max)
                        })
                        meta['trunk_id'] = int(trunk_id)
                        meta.setdefault('local_id', int(branch_id))
                        meta['point_count'] = int(meta.get('point_count', 0) + len(cluster_indices))
                        old_min_z, old_max_z = meta.get('z_span', (cluster_z_min, cluster_z_max))
                        meta['z_span'] = (min(float(old_min_z), cluster_z_min), max(float(old_max_z), cluster_z_max))

                    prev_slice_clusters = current_slice_clusters

                trunk_branch_ids = sorted(int(branch_id) for branch_id in np.unique(point_to_branch[trunk_indices]) if int(branch_id) >= 0)
                trunk_classified = int(np.sum(point_to_branch[trunk_indices] >= 0))
                total_classified_points += trunk_classified
                total_branches_detected += len(trunk_branch_ids)
                self.log_to_console(
                    f"  Trunk {trunk_id}: {len(trunk_branch_ids)} branch(es), {trunk_classified} classified point(s)"
                )
            
            # Store branch assignment
            self.branch_assignment = point_to_branch
            
            self.log_to_console(f"\n✅ Branch detection complete!")
            self.log_to_console(f"   Total unique branches: {len([b for b in np.unique(point_to_branch) if b >= 0])}")
            self.log_to_console(f"   Total trunk-scoped branches: {total_branches_detected}")
            self.log_to_console(f"   Classified branch points: {total_classified_points}")
            self.log_to_console(f"   Noise points: {np.sum(point_to_branch == -1)}")
            
            # Store branch assignment in memory for visualization and export
            # (LAS field modification may be handled during save operation)
            self.log_to_console(f"✅ Branch assignment stored in memory for visualization")

            # ── Merge overlapping branches within each trunk ──
            point_to_branch, merge_report = self._merge_overlapping_branches(point_to_branch)
            self.branch_assignment = point_to_branch  # update with merged branch IDs
            self.log_to_console(merge_report)
            
            # Enable selection and volume tools now that branch detection exists
            try:
                if hasattr(self, 'select_all_points_button'):
                    self.select_all_points_button.setEnabled(True)
                if hasattr(self, 'volume_calc_button'):
                    self.volume_calc_button.setEnabled(True)
            except Exception:
                pass
            
            # Visualize branches with different colors
            self.visualize_branches_from_assignment()
            # Only bump branch detection version if parameters changed since last run
            try:
                if current_branch_params is not None and current_branch_params != getattr(self, '_last_branch_detection_params', None):
                    self._last_branch_detection_params = current_branch_params
                    try:
                        self._branch_detection_version = int(getattr(self, '_branch_detection_version', 0)) + 1
                    except Exception:
                        self._branch_detection_version = getattr(self, '_branch_detection_version', 0) + 1
                    self.log_to_console(f"🔁 Branch detection parameters changed; version updated: {self._branch_detection_version}")
                else:
                    self.log_to_console("ℹ️ Branch detection run used same parameters as last run; detection version unchanged.")
            except Exception:
                try:
                    self._branch_detection_version = int(getattr(self, '_branch_detection_version', 0)) + 1
                except Exception:
                    self._branch_detection_version = getattr(self, '_branch_detection_version', 0) + 1
                self.log_to_console(f"🔁 Branch detection version updated (fallback): {self._branch_detection_version}")
            
        except Exception as e:
            self.log_to_console(f"❌ Error detecting branch clusters: {str(e)}")
            import traceback
            self.log_to_console(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Failed to detect branches:\n{str(e)}")

    def visualize_branches_from_assignment(self):
        """Visualize the branch assignment using colors from branch_cls."""
        if not hasattr(self, 'branch_assignment'):
            self.log_to_console("⚠️ No branch assignment available")
            return
        
        try:
            self.log_to_console(f"\n🎨 Visualizing branches...")
            
            # Clear current visualization
            self.plotter.clear()
            self._restore_gdb_layers()
            
            # Get unique branch IDs
            unique_branches = np.unique(self.branch_assignment)
            unique_branches = unique_branches[unique_branches >= 0]  # Exclude noise (-1)
            
            num_branches = len(unique_branches)
            self.log_to_console(f"   Rendering {num_branches} branches...")
            
            # Create color palette for branches
            import matplotlib.cm as cm
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                if num_branches <= 10:
                    cmap = plt.get_cmap('tab10')
                elif num_branches <= 20:
                    cmap = plt.get_cmap('tab20')
                else:
                    cmap = plt.get_cmap('hsv')

            colors = cmap(np.linspace(0, 1, num_branches))

            # Calculate branch statistics for console output
            self.log_to_console(f"\n📋 BRANCH DETAILS:")
            self.log_to_console(f"{'Branch ID':<12} {'Trunk':<8} {'Local':<8} {'Size':<8} {'Min Z':<8} {'Max Z':<8} {'Height':<8}")
            self.log_to_console(f"-" * 74)
            
            branch_info = {}
            
            # Add each branch with unique color and information
            for i, branch_id in enumerate(unique_branches):
                mask = self.branch_assignment == branch_id
                branch_points = self.current_tree_points[mask]
                
                if len(branch_points) > 0:
                    # Calculate statistics
                    size = len(branch_points)
                    min_z = np.min(branch_points[:, 2])
                    max_z = np.max(branch_points[:, 2])
                    height = max_z - min_z
                    centroid = np.mean(branch_points, axis=0)
                    branch_meta = self.branch_meta.get(int(branch_id), {}) if hasattr(self, 'branch_meta') else {}
                    trunk_id = branch_meta.get('trunk_id', '?')
                    local_id = branch_meta.get('local_id', branch_id)
                    
                    # Store for labeling
                    branch_info[branch_id] = {
                        'size': size,
                        'min_z': min_z,
                        'max_z': max_z,
                        'height': height,
                        'centroid': centroid
                    }
                    
                    # Log statistics
                    self.log_to_console(
                        f"{branch_id:<12} {trunk_id:<8} {local_id:<8} {size:<8} {min_z:<8.2f} {max_z:<8.2f} {height:<8.2f}"
                    )
                    
                    # Add points with color
                    color = colors[i % len(colors)]
                    rgb_color = [float(color[0]), float(color[1]), float(color[2])]
                    
                    self.plotter.add_points(
                        branch_points,
                        color=rgb_color,
                        point_size=5,
                        name=f'Branch_{branch_id}'
                    )
                    
                    # Add label at branch centroid
                    try:
                        if trunk_id == '?':
                            label_text = f'B{branch_id}'
                        else:
                            label_text = f'T{trunk_id}.B{local_id}'
                        self.plotter.add_point_labels(
                            np.array([centroid]),
                            [label_text],
                            font_size=12,
                            text_color='white',
                            always_visible=True,
                            name=f'Label_Branch_{branch_id}'
                        )
                    except Exception as label_error:
                        self.log_to_console(f"  (Label for branch {branch_id} skipped: {str(label_error)})")
            
            # Add statistics line
            self.log_to_console(f"-" * 66)
            
            # Add noise points in gray if any
            noise_mask = self.branch_assignment == -1
            if np.any(noise_mask):
                noise_points = self.current_tree_points[noise_mask]
                self.plotter.add_points(
                    noise_points,
                    color=[0.5, 0.5, 0.5],
                    point_size=3,
                    name='Noise'
                )
                self.log_to_console(f"{'Noise':<12} {len(noise_points):<8} (filtered points)")
            
            # Summary statistics
            self.log_to_console(f"\n📊 SUMMARY:")
            total_classified = np.sum(self.branch_assignment >= 0)
            total_noise = np.sum(self.branch_assignment == -1)
            total_points = len(self.branch_assignment)
            
            self.log_to_console(f"  Total points classified: {total_classified} ({100*total_classified/total_points:.1f}%)")
            self.log_to_console(f"  Noise points: {total_noise} ({100*total_noise/total_points:.1f}%)")
            self.log_to_console(f"  Unique branches: {num_branches}")
            
            if branch_info:
                sizes = [b['size'] for b in branch_info.values()]
                self.log_to_console(f"  Branch size range: {min(sizes)}-{max(sizes)} points")
                self.log_to_console(f"  Average branch size: {np.mean(sizes):.1f} points")

            # ── Vertical proximity analysis per trunk ──
            self._analyze_branch_vertical_proximity()

            # Update and display
            self.plotter.reset_camera()
            self.plotter.update()
            
            self.log_to_console(f"\n✅ Branch visualization complete!")
            self.log_to_console(f"   (Branch labels shown as 'B#' in 3D view)\n")
            
        except Exception as e:
            self.log_to_console(f"❌ Error visualizing branches: {str(e)}")
            import traceback
            self.log_to_console(traceback.format_exc())

    def _merge_overlapping_branches(self, point_to_branch: np.ndarray) -> Tuple[np.ndarray, str]:
        """
        Merge branches within each trunk that have overlapping Z ranges.
        Two branches overlap if: next.Z_min < current.Z_max (negative vertical gap).
        
        Returns:
            (updated_point_to_branch, merge_report_string)
        """
        if not hasattr(self, 'branch_meta') or not self.branch_meta:
            return point_to_branch, ""

        # Group branches by trunk with their Z spans
        trunk_branches: Dict[int, List[Dict[str, Any]]] = {}
        for branch_id, meta in self.branch_meta.items():
            trunk_id = meta.get('trunk_id', '?')
            if trunk_id == '?':
                continue
            trunk_id = int(trunk_id)
            z_min, z_max = meta.get('z_span', (0.0, 0.0))
            trunk_branches.setdefault(trunk_id, []).append({
                'branch_id': int(branch_id),
                'z_min': float(z_min),
                'z_max': float(z_max),
            })

        # Build remapping: old_branch_id -> merged_into_branch_id
        remap: Dict[int, int] = {}
        total_merged = 0
        merge_details: List[str] = []

        for trunk_id in sorted(trunk_branches.keys()):
            branches = trunk_branches[trunk_id]
            if len(branches) < 2:
                continue

            # Sort by Z_min
            branches.sort(key=lambda b: b['z_min'])

            # Walk through and find overlapping groups
            i = 0
            while i < len(branches):
                group = [branches[i]]
                j = i + 1
                while j < len(branches):
                    # Check if branch[j] overlaps with the combined group's Z_max
                    group_z_max = max(b['z_max'] for b in group)
                    if branches[j]['z_min'] < group_z_max:  # Overlap
                        group.append(branches[j])
                        j += 1
                    else:
                        break

                if len(group) >= 2:
                    # Merge group: keep the first branch_id, remap others
                    keeper_id = group[0]['branch_id']
                    merged_ids = []
                    for br in group[1:]:
                        remap[br['branch_id']] = keeper_id
                        merged_ids.append(br['branch_id'])

                    # Update meta: merge point counts and Z spans
                    if keeper_id in self.branch_meta:
                        keeper_meta = self.branch_meta[keeper_id]
                        for br in group[1:]:
                            if br['branch_id'] in self.branch_meta:
                                old_meta = self.branch_meta[br['branch_id']]
                                keeper_meta['point_count'] += old_meta.get('point_count', 0)
                                old_zmin, old_zmax = keeper_meta.get('z_span', (float('inf'), float('-inf')))
                                new_zmin = min(old_zmin, old_meta.get('z_span', (float('inf'), float('-inf')))[0])
                                new_zmax = max(old_zmax, old_meta.get('z_span', (float('-inf'), float('inf')))[1])
                                keeper_meta['z_span'] = (new_zmin, new_zmax)
                                # Delete the merged branch's meta
                                del self.branch_meta[br['branch_id']]

                    total_merged += len(merged_ids)
                    z_range = f"{group[0]['z_min']:.2f}–{group_z_max:.2f}m"
                    merged_str = ", ".join(f"B{b}" for b in merged_ids)
                    merge_details.append(f"     T{trunk_id}: B{keeper_id} ← merged {merged_str} | Z range: {z_range}")

                i = j  # Move to next unprocessed branch

        # Apply remapping to point_to_branch
        if remap:
            remap_array = np.full(point_to_branch.max() + 1, -1, dtype=int)
            for old_id, new_id in remap.items():
                remap_array[old_id] = new_id
            # Fill self-references
            unique_ids = np.unique(point_to_branch)
            for bid in unique_ids:
                if bid >= 0 and bid < len(remap_array) and remap_array[bid] == -1:
                    remap_array[bid] = bid

            valid_mask = point_to_branch >= 0
            point_to_branch[valid_mask] = remap_array[point_to_branch[valid_mask]]

        # Build report
        if total_merged == 0:
            return point_to_branch, ""

        report_lines = [""]
        report_lines.append(f"🔄 MERGED OVERLAPPING BRANCHES: {total_merged} branch(es) merged into existing branches")
        report_lines.extend(merge_details)
        report_lines.append(f"   Remaining unique branches after merge: {len([b for b in np.unique(point_to_branch) if b >= 0])}")
        return point_to_branch, "\n".join(report_lines)

    def _analyze_branch_vertical_proximity(self):
        """Analyze vertical gaps between branches within each trunk and print a proximity table."""
        if not hasattr(self, 'branch_meta') or not self.branch_meta:
            self.log_to_console("⚠️ No branch metadata available for vertical proximity analysis.")
            return

        # Group branches by trunk_id
        trunk_branches: Dict[int, List[Dict[str, Any]]] = {}
        for branch_id, meta in self.branch_meta.items():
            trunk_id = meta.get('trunk_id', '?')
            if trunk_id == '?':
                continue
            trunk_id = int(trunk_id)
            z_min, z_max = meta.get('z_span', (0.0, 0.0))
            trunk_branches.setdefault(trunk_id, []).append({
                'branch_id': int(branch_id),
                'local_id': meta.get('local_id', branch_id),
                'z_min': float(z_min),
                'z_max': float(z_max),
                'height': float(z_max) - float(z_min),
                'point_count': meta.get('point_count', 0),
            })

        if not trunk_branches:
            self.log_to_console("⚠️ No trunk-scoped branches found for vertical proximity analysis.")
            return

        self.log_to_console(f"\n{'='*90}")
        self.log_to_console(f"📐 BRANCH VERTICAL PROXIMITY ANALYSIS")
        self.log_to_console(f"{'='*90}")

        for trunk_id in sorted(trunk_branches.keys()):
            branches = trunk_branches[trunk_id]
            if len(branches) < 2:
                self.log_to_console(f"\n  Trunk T{trunk_id}: only 1 branch — no gaps to compare.")
                continue

            # Sort by min Z (bottom of branch)
            branches.sort(key=lambda b: b['z_min'])

            self.log_to_console(f"\n  ┌─ Trunk T{trunk_id} ({len(branches)} branches) ───────────────────────────────┐")
            header = f"  │ {'Branch':<10} {'Z Min (m)':>10} {'Z Max (m)':>10} {'Height (m)':>10} {'Gap Below (m)':>14} {'Status':<16} │"
            self.log_to_console(header)
            self.log_to_console(f"  │{'-' * 86}│")

            for i, br in enumerate(branches):
                if i == 0:
                    # First (lowest) branch — gap to ground
                    gap_below = br['z_min']  # Distance from ground (min Z of branch) - we'd need tree base
                    # Get tree base from current_tree_points if available
                    tree_base = None
                    if hasattr(self, 'current_tree_points') and self.current_tree_points is not None:
                        tree_base = float(np.min(self.current_tree_points[:, 2]))
                    if tree_base is not None:
                        gap_below = br['z_min'] - tree_base
                        status = "↳ from tree base"
                    else:
                        status = "↳ lowest branch"
                else:
                    # Gap between this branch's bottom and previous branch's top
                    gap_below = br['z_min'] - branches[i - 1]['z_max']
                    if gap_below <= 0.05:
                        status = "⚠ overlapping"
                    elif gap_below < 0.15:
                        status = "● very close"
                    elif gap_below < 0.30:
                        status = "● close"
                    elif gap_below < 0.50:
                        status = "◐ moderate"
                    else:
                        status = "○ far apart"

                branch_label = f"T{trunk_id}.B{br['local_id']}"
                self.log_to_console(
                    f"  │ {branch_label:<10} {br['z_min']:>10.2f} {br['z_max']:>10.2f} "
                    f"{br['height']:>10.2f} {gap_below:>14.2f} {status:<16} │"
                )

            # Summary stats for this trunk
            gaps = []
            for i in range(1, len(branches)):
                gaps.append(branches[i]['z_min'] - branches[i - 1]['z_max'])
            if gaps:
                min_gap = min(gaps)
                max_gap = max(gaps)
                avg_gap = np.mean(gaps)
                close_count = sum(1 for g in gaps if g < 0.15)
                overlap_count = sum(1 for g in gaps if g <= 0.05)
                self.log_to_console(f"  └{'─' * 86}┘")
                self.log_to_console(f"     Total gaps: {len(gaps)} | Avg: {avg_gap:.2f}m | Min: {min_gap:.2f}m | Max: {max_gap:.2f}m")
                if close_count > 0:
                    self.log_to_console(f"     ⚠ {close_count} branch pair(s) vertically close (<15cm)")
                if overlap_count > 0:
                    self.log_to_console(f"     ❗ {overlap_count} branch pair(s) overlapping vertically (≤5cm)")

        self.log_to_console(f"{'='*90}\n")

    def select_volume_folder(self):
        """Allow user to pre-select a folder for batch volume saving."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder for Volume Saves",
            ""
        )
        if folder:
            self.volume_folder_path = folder
            self.log_to_console(f"📁 Volume folder selected: {folder}")
            QMessageBox.information(self, "Success", f"Volume folder set to:\n{folder}")
        else:
            self.log_to_console("ℹ️ No folder selected")

    def take_tree_screenshots(self):
        """Take screenshots of the tree from 4 different views."""
        import tempfile
        import os

        if not self.plotter:
            return []

        screenshot_paths = []

        try:
            # Store original camera position
            original_camera = self.plotter.camera.copy()

            # Define camera positions for each view
            views = [
                ('front', [1, 0, 0], [0, 0, 1]),    # Front view
                ('back', [-1, 0, 0], [0, 0, 1]),    # Back view
                ('left', [0, 1, 0], [0, 0, 1]),     # Left view
                ('right', [0, -1, 0], [0, 0, 1])    # Right view
            ]

            for view_name, position, up_vector in views:
                # Set camera position
                self.plotter.camera.position = position
                self.plotter.camera.focal_point = [0, 0, 0]  # Center of tree
                self.plotter.camera.up = up_vector
                self.plotter.reset_camera()

                # Update plotter
                self.plotter.update()

                # Take screenshot
                temp_file = tempfile.NamedTemporaryFile(suffix=f'_{view_name}.png', delete=False)
                screenshot_path = temp_file.name
                temp_file.close()

                # Capture screenshot
                self.plotter.screenshot(screenshot_path)
                screenshot_paths.append(screenshot_path)

                self.log_to_console(f"Captured {view_name} view screenshot")            # Restore original camera position
            self.plotter.camera = original_camera
            self.plotter.reset_camera()
            self.plotter.update()

        except Exception as e:
            self.log_to_console(f"Error taking screenshots: {str(e)}")
            # Clean up any screenshots taken so far
            self.cleanup_screenshots(screenshot_paths)
            return []

        return screenshot_paths

    def run_ai_analysis(self, screenshot_paths):
        """Run AI analysis on the screenshots using local LM Studio or NVIDIA NIM API."""
        import base64
        from PIL import Image
        import io
        import litellm

        def encode_image(image_path, max_size=(896, 896), quality=85):
            """Encode image file to base64 string with optional resizing"""
            with Image.open(image_path) as img:
                # Convert to RGB if necessary (for PNG with transparency, etc.)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')

                # Resize if larger than max_size
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save to bytes buffer as JPEG
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
                buffer.seek(0)

                return base64.b64encode(buffer.getvalue()).decode('utf-8')

        try:
            # Check if using local LM Studio or NVIDIA NIM
            use_local_model = os.getenv("USE_LOCAL_LM_STUDIO", "false").lower() == "true"
            
            if use_local_model:
                # Use local LM Studio model
                lm_studio_api_url = os.getenv("LM_STUDIO_API_URL", "http://localhost:1234/v1")
                model = os.getenv("LM_STUDIO_MODEL", "local-model")  # Name of loaded model in LM Studio
                
                self.log_to_console(f"Using local LM Studio model from {lm_studio_api_url}")
                
                # Set up LiteLLM for local LM Studio (OpenAI-compatible API)
                litellm.api_base = lm_studio_api_url
                litellm.api_key = "not-needed"  # LM Studio typically doesn't require API key
            else:
                # Use NVIDIA NIM cloud API
                model = "nvidia_nim/meta/llama-4-maverick-17b-128e-instruct"
                
                # Set API key from environment or use the one from original script
                api_key = os.getenv("NVIDIA_API_KEY", "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")
                os.environ["NVIDIA_NIM_API_KEY"] = api_key
                
                self.log_to_console("Using NVIDIA NIM cloud API")

            # Add analysis prompt
            prompt = """You are an AI agent evaluating tree segmentation quality in point cloud data from aerial leaf-off LiDAR imagery. Analyze these images from different views of a tree and provide your assessment in JSON format only.

Context: These images show point clouds colored by RGB values from aerial orthoimagery (leaf-off condition):
- DECIDUOUS TREES: Appear grey to white in color (branches visible without leaves)
- CONIFEROUS TREES: Appear green in color (foliage present year-round) with a cone/pyramidal shape. NOTE: Coniferous trees may have white/grey coloring at the BASE (trunk area) and green coloring in the CROWN/TOP - look at the upper portion to identify tree type
- NOISE/GROUND: Random scattered points, no organized structure, no distinct tree crowns
- MULTIPLE TREES: Several distinct tree structures/crowns visible in the same segment (segmentation error)

IMPORTANT: Do NOT mark multiple tree detection as noise. Multiple trees are valid tree structures but indicate a segmentation error where two or more trees were grouped together.

First, determine what this segment contains: noise/ground, a single tree, or multiple trees. Then provide appropriate analysis.

Please respond with a valid JSON object.

If the point cloud appears to be noise or random points (NO distinct tree structure), use this format:
{
  "is_tree": "no",
  "appears_to_be_noise": "yes",
  "recommended_action": "convert_to_noise_class",
  "noise_itc_value": 9999,
  "analysis_summary": "brief description of why this appears to be noise rather than a tree"
}

If the point cloud contains MULTIPLE DISTINCT TREES, use this format:
{
  "is_tree": "yes",
  "appears_to_be_noise": "no",
  "multiple_trees_detected": "yes",
  "total_trunks_detected": integer (count the number of distinct tree trunks/structures),
  "distinct_crowns": integer (count the number of separate crown structures visible),
  "trunk_disconnected": "yes",
  "tree_type": "mixed" or list individual types observed,
  "analysis_summary": "The point cloud contains multiple trees rather than a single tree, with several distinct tree structures visible across different views. The presence of multiple trees indicates that the segmentation is not accurate for a single tree. Recommend re-segmentation to separate individual trees."
}

If the point cloud appears to be a SINGLE VALID TREE, use this format:
{
  "is_tree": "yes",
  "appears_to_be_noise": "no",
  "multiple_trees_detected": "no",
  "tree_type": "coniferous" or "deciduous" (coniferous trees show GREEN coloring in the CROWN/TOP with cone/pyramidal shape, may have white/grey at base; deciduous trees show GREY/WHITE coloring overall with branching structure visible),
  "trunk_well_defined": "yes" or "no" (answer "yes" if the central trunk forms a single, continuous, well-connected vertical structure from base to crown - check for large disconnects or gaps),
  "trunk_disconnected": "yes" or "no" (answer "yes" if the central trunk appears broken into separate large segments with significant gaps between them),
  "total_trunks_detected": integer (count the number of separate large trunk segments - use 1 for a single connected trunk, higher numbers for disconnected segments),
  "crown_shape_quality": "good", "fair", or "poor" (evaluate if the crown shape is well-formed and organized - good for conical/pyramidal coniferous or rounded deciduous, poor for fragmented or irregular shapes),
  "analysis_summary": "brief description of your assessment focusing on tree type, trunk continuity, crown shape, and segmentation quality"
}

Important:
- Only output valid JSON, no additional text
- Color interpretation: Look at the CROWN/TOP of the point cloud for tree type identification
  * GREEN crown = coniferous (evergreen) - may have white/grey base/trunk
  * GREY/WHITE overall = deciduous (leaf-off)
- CRITICAL: Multiple trees are NOT noise - they are valid trees with poor segmentation
- For coniferous trees: Examine the upper crown portion for green coloring and pyramidal shape, even if base is discolored
- For noise detection: look for scattered/random colored points, no clear tree structures, no organized crown shapes
- For multiple trees: look for several distinct crown structures and separate trunks in one segment
- For single tree analysis: evaluate the central trunk for continuity and the crown for good shape
- A well-defined single tree should have a continuous trunk from base to crown and a well-organized crown shape
- Coniferous: look for cone/pyramidal shape (especially in upper crown) and green coloring in foliage area
- Deciduous: look for grey/white skeletal branching structure with organized crown"""

            # Prepare message content
            content = [{"type": "text", "text": prompt}]
            for image_path in screenshot_paths:
                base64_image = encode_image(image_path, max_size=(896, 896))
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })

            messages = [{"role": "user", "content": content}]

            self.log_to_console("Running AI analysis...")

            # Call LiteLLM with appropriate settings
            if use_local_model:
                # For local models, use simpler API call
                response = litellm.completion(
                    model=f"openai/{model}",
                    messages=messages,
                    max_tokens=512,
                    temperature=0.20,
                    top_p=0.70,
                    stream=True
                )
            else:
                # For NVIDIA NIM
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.20,
                    top_p=0.70,
                    frequency_penalty=0.00,
                    presence_penalty=0.00,
                    stream=True  # Enable streaming for real-time output
                )

            # Handle streaming response
            full_response = ""
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        full_response += delta.content

            return full_response.strip()

        except Exception as e:
            self.log_to_console(f"Error running AI analysis: {str(e)}")
            return f"Failed to run AI analysis: {str(e)}"

    def display_ai_results(self, ai_result):
        """Display the AI analysis results in a dialog."""
        if not ai_result or ai_result.startswith("Failed"):
            QMessageBox.warning(self, "AI Analysis Failed", ai_result)
            return

        # Create result dialog
        result_dialog = QDialog(self)
        result_dialog.setWindowTitle("AI Tree Structure Analysis")
        result_dialog.setGeometry(300, 300, 600, 400)
        
        # Set dialog background to match app theme
        result_dialog.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #e0e0e0;
            }
        """)

        layout = QVBoxLayout(result_dialog)

        # Title
        title_label = QLabel("AI Tree Structure Analysis")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #4CAF50;")
        layout.addWidget(title_label)

        # Tree info
        tree_info = f"Analyzed Tree: {self.current_tree_id or 'Unknown'} ({len(self.current_tree_points) if self.current_tree_points is not None else 0} points)"
        info_label = QLabel(tree_info)
        info_label.setStyleSheet("font-weight: bold; color: #e0e0e0;")
        layout.addWidget(info_label)

        # Try to parse JSON response
        try:
            import json
            json_result = json.loads(ai_result)
            
            # Create structured display
            results_layout = QVBoxLayout()
            
            # Check if this is noise detection or tree analysis
            is_tree = json_result.get('is_tree', 'yes')  # Default to tree analysis for backward compatibility
            
            if is_tree.lower() == 'no':
                # Noise detection result
                appears_noise = json_result.get('appears_to_be_noise', 'unknown')
                noise_color = "#FF4444" if appears_noise.lower() == "yes" else "#4CAF50"
                noise_label = QLabel(f"Appears to be Noise: {appears_noise.upper()}")
                noise_label.setStyleSheet(f"font-weight: bold; color: {noise_color}; font-size: 12px;")
                results_layout.addWidget(noise_label)
                
                # Recommended action
                recommended_action = json_result.get('recommended_action', 'unknown')
                action_label = QLabel(f"Recommended Action: {recommended_action.replace('_', ' ').upper()}")
                action_label.setStyleSheet("font-weight: bold; color: #FF8844; font-size: 12px;")
                results_layout.addWidget(action_label)
                
                # Noise ITC value
                noise_itc = json_result.get('noise_itc_value', 'unknown')
                itc_label = QLabel(f"ITC Value for Noise: {noise_itc}")
                itc_label.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 12px;")
                results_layout.addWidget(itc_label)
                
                # Add "Convert to Noise" button
                convert_button = ModernButton("Convert to Noise Class (ITC 9999)")
                convert_button.clicked.connect(lambda: self.convert_to_noise_class(9999, self.last_analyzed_points))
                results_layout.addWidget(convert_button)
                
            else:
                # Tree analysis result
                # Tree type
                tree_type = json_result.get('tree_type', 'unknown')
                tree_type_color = "#4CAF50" if tree_type.lower() in ['coniferous', 'deciduous'] else "#FF8844"
                tree_type_label = QLabel(f"Tree Type: {tree_type.upper()}")
                tree_type_label.setStyleSheet(f"font-weight: bold; color: {tree_type_color}; font-size: 12px;")
                results_layout.addWidget(tree_type_label)
                
                # Trunk well defined
                trunk_status = json_result.get('trunk_well_defined', 'unknown')
                trunk_color = "#4CAF50" if trunk_status.lower() == "yes" else "#FF4444"
                trunk_label = QLabel(f"Trunk Well Defined: {trunk_status.upper()}")
                trunk_label.setStyleSheet(f"font-weight: bold; color: {trunk_color}; font-size: 12px;")
                results_layout.addWidget(trunk_label)
                
                # Trunk disconnected
                trunk_disconnected = json_result.get('trunk_disconnected', 'unknown')
                disconnected_color = "#FF4444" if trunk_disconnected.lower() == "yes" else "#4CAF50"
                disconnected_label = QLabel(f"Trunk Disconnected: {trunk_disconnected.upper()}")
                disconnected_label.setStyleSheet(f"font-weight: bold; color: {disconnected_color}; font-size: 12px;")
                results_layout.addWidget(disconnected_label)
                
                # Total trunks detected
                trunk_count = json_result.get('total_trunks_detected', 'unknown')
                trunk_count_label = QLabel(f"Total Trunks Detected: {trunk_count}")
                trunk_count_label.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 12px;")
                results_layout.addWidget(trunk_count_label)
            
            # Analysis summary (common to both formats)
            summary_text = json_result.get('analysis_summary', 'No summary provided')
            summary_label = QLabel("Analysis Summary:")
            summary_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px;")
            results_layout.addWidget(summary_label)
            
            summary_display = QTextEdit()
            summary_display.setPlainText(summary_text)
            summary_display.setReadOnly(True)
            summary_display.setMaximumHeight(100)
            summary_display.setStyleSheet("""
                QTextEdit {
                    background-color: #363636;
                    color: #e0e0e0;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px;
                }
            """)
            results_layout.addWidget(summary_display)
            
            # Raw JSON response from LLM
            raw_json_label = QLabel("Raw LLM Response (JSON):")
            raw_json_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin-top: 10px;")
            results_layout.addWidget(raw_json_label)
            
            raw_json_display = QTextEdit()
            raw_json_display.setPlainText(json.dumps(json_result, indent=2))
            raw_json_display.setReadOnly(True)
            raw_json_display.setMaximumHeight(150)
            raw_json_display.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #00ff00;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Courier New', monospace;
                    font-size: 10px;
                }
            """)
            results_layout.addWidget(raw_json_display)
            
            layout.addLayout(results_layout)
            
        except json.JSONDecodeError:
            # Fallback to raw text display if JSON parsing fails
            error_label = QLabel("⚠️ AI response was not in expected JSON format. Raw response:")
            error_label.setStyleSheet("color: #FF8844; font-size: 11px;")
            layout.addWidget(error_label)
            
            result_text = QTextEdit()
            result_text.setPlainText(ai_result)
            result_text.setReadOnly(True)
            result_text.setStyleSheet("""
                QTextEdit {
                    background-color: #363636;
                    color: #e0e0e0;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px;
                    selection-background-color: #4CAF50;
                }
            """)
            layout.addWidget(result_text)

        # Close button
        close_button = ModernButton("Close")
        close_button.clicked.connect(result_dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        result_dialog.exec()





    def cleanup_screenshots(self, screenshot_paths):
        """Clean up temporary screenshot files."""
        for path in screenshot_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                self.log_to_console(f"Warning: Failed to clean up {path}: {str(e)}")

    def save_analysis_screenshots(self, temp_screenshot_paths, analysis_dir, analysis_id):
        """Save screenshots to the analysis directory with descriptive names."""
        import shutil

        saved_paths = []
        view_names = ['front', 'back', 'left', 'right']

        try:
            for i, temp_path in enumerate(temp_screenshot_paths):
                view_name = view_names[i] if i < len(view_names) else f'view_{i}'
                filename = f"{analysis_id}_{view_name}.png"
                dest_path = os.path.join(analysis_dir, filename)

                # Copy the temporary screenshot to the analysis directory
                shutil.copy2(temp_path, dest_path)
                saved_paths.append(dest_path)

                self.log_to_console(f"Saved {view_name} screenshot: {filename}")

            return saved_paths

        except Exception as e:
            self.log_to_console(f"Error saving analysis screenshots: {str(e)}")
            return []

    def save_analysis_results(self, analysis_dir, analysis_id, ai_result, screenshot_paths):
        """Save analysis results, prompt, and metadata to the analysis directory."""
        try:
            # Save AI prompt
            prompt = """You are an AI agent evaluating tree segmentation quality in point cloud data. Analyze these images from different views of a tree and provide your assessment in JSON format only.

Context: These images show the output of a tree segmentation algorithm where:
- Yellow points represent trunk/stem points
- Purple points represent branches and foliage
- The goal is to assess the quality of the tree segmentation

Please respond with a valid JSON object containing exactly these fields:
{
  "trunk_well_defined": "yes" or "no" (answer "yes" if the yellow trunk points form a single, continuous, well-connected vertical structure from base to top - check for large disconnects or gaps in the trunk),
  "trunk_disconnected": "yes" or "no" (answer "yes" if the yellow trunk appears broken into separate large segments with significant gaps between them),
  "total_trunks_detected": integer (count the number of separate large trunk segments you can identify in the yellow points - use 1 for a single connected trunk, higher numbers for disconnected segments),
  "analysis_summary": "brief description of your assessment focusing on trunk continuity and segmentation quality"
}

Important: 
- Only output valid JSON, no additional text
- Focus on the yellow trunk points - look for large disconnects or gaps that break trunk continuity
- A well-defined trunk should appear as continuous yellow points from base to crown
- Ignore purple branch/foliage points for trunk assessment"""

            prompt_file = os.path.join(analysis_dir, f"{analysis_id}_prompt.txt")
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            self.log_to_console(f"Saved analysis prompt: {os.path.basename(prompt_file)}")

            # Save AI response
            response_file = os.path.join(analysis_dir, f"{analysis_id}_response.txt")
            with open(response_file, 'w', encoding='utf-8') as f:
                f.write(ai_result)
            self.log_to_console(f"Saved AI response: {os.path.basename(response_file)}")

            # Save metadata
            metadata_file = os.path.join(analysis_dir, f"{analysis_id}_metadata.txt")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                f.write(f"Analysis ID: {analysis_id}\n")
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Tree ID: {self.current_tree_id or 'Unknown'}\n")
                f.write(f"Number of Points: {len(self.current_tree_points) if self.current_tree_points is not None else 0}\n")
                f.write(f"Screenshots: {len(screenshot_paths)}\n")
                for i, path in enumerate(screenshot_paths):
                    f.write(f"  - {os.path.basename(path)}\n")
                f.write(f"Analysis Success: {'Yes' if not ai_result.startswith('Failed') else 'No'}\n")

            self.log_to_console(f"Saved analysis metadata: {os.path.basename(metadata_file)}")

        except Exception as e:
            self.log_to_console(f"Error saving analysis results: {str(e)}")

    def extract_component(self):
        """
        Extract individual tree components (trunk and branches) from currently visualized trunk points
        using advanced connectivity-based branch extension algorithm with DBSCAN clustering.
        """
        if not hasattr(self, 'current_tree_points') or self.current_tree_points is None:
            QMessageBox.warning(self, "No Trunk Points", "No trunk points available. Please visualize a trunk first.")
            return

        try:
            # Get the points data - use all stem points from LAS data for proper analysis
            if self.las_data is None:
                QMessageBox.warning(self, "No LAS Data", "LAS data not available for advanced analysis.")
                return

            # Get all stem points (stemcls != 1) for the selected trees
            selected_tree_ids = self.get_selected_tree_ids()
            if not selected_tree_ids:
                QMessageBox.warning(self, "No Trees Selected", "Please select tree IDs first.")
                return

            itc_values = np.array(self.las_data['itc'])
            stemcls_values = np.array(self.las_data['stemcls'])

            # Get all stem points for selected trees
            all_stem_points = []
            for tree_id in selected_tree_ids:
                mask = (itc_values == tree_id) & (stemcls_values != 1)
                if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                    treefilter_values = np.array(self.las_data['treefilter'])
                    mask = mask & (treefilter_values == 2)

                if np.any(mask):
                    points = np.column_stack([
                        np.array(self.las_data.x)[mask],
                        np.array(self.las_data.y)[mask],
                        np.array(self.las_data.z)[mask]
                    ])
                    all_stem_points.append(points)

            if not all_stem_points:
                QMessageBox.warning(self, "No Stem Points", "No stem points found for selected trees.")
                return

            # Combine all stem points
            stem_points = np.vstack(all_stem_points)

            # Estimate branching height from current trunk visualization
            # Use the maximum height of currently visualized trunk points as branching height
            branching_height = np.max(self.current_tree_points[:, 2]) - np.min(self.current_tree_points[:, 2])

            # Extract components using the advanced algorithm
            components = extract_components(stem_points, branching_height)

            # Visualize the advanced components
            self._visualize_advanced_components(components, branching_height, stem_points)

            # Count total components (trunk + branches + unassigned if any)
            total_components = 1 + len(components['branches']) + (1 if len(components['unassigned']) > 0 else 0)
            QMessageBox.information(self, "Advanced Components Extracted",
                                  f"Successfully extracted {total_components} components:\n"
                                  f"• Trunk: {len(components['trunk'])} points\n"
                                  f"• Branches: {len(components['branches'])} branches\n"
                                  f"• Unassigned: {len(components['unassigned'])} points")

        except Exception as e:
            QMessageBox.warning(self, "Extraction Error", f"Error extracting components: {str(e)}")
            print(f"Component extraction error: {e}")

    def extract_dbh_components(self):
        """
        Extract components from DBH points only (below first split) using connectivity-based analysis.
        This analyzes the trunk structure below the first branching point.
        """
        if not hasattr(self, 'current_tree_points') or self.current_tree_points is None:
            QMessageBox.warning(self, "No Tree Points", "No tree points available. Please visualize a tree first.")
            return

        if self.las_data is None or 'dbh_points' not in self.las_data.point_format.dimension_names:
            QMessageBox.warning(self, "No DBH Points", "DBH points field not found. Please run split detection first.")
            return

        try:
            # Get DBH points for the current tree
            if self.current_mask is None:
                QMessageBox.warning(self, "No Tree Selected", "No tree is currently selected.")
                return
                
            tree_indices = np.where(self.current_mask)[0]
            dbh_values = np.array(self.las_data['dbh_points'])[tree_indices]
            dbh_mask = dbh_values == 1

            if not np.any(dbh_mask):
                QMessageBox.warning(self, "No DBH Points", "No DBH points found for the current tree.")
                return

            # Extract DBH point coordinates
            dbh_indices = tree_indices[dbh_mask]
            dbh_points = np.column_stack([
                np.array(self.las_data.x)[dbh_indices],
                np.array(self.las_data.y)[dbh_indices],
                np.array(self.las_data.z)[dbh_indices]
            ])

            self.log_to_console(f"📊 Extracting components from {len(dbh_points)} DBH points")

            # For DBH component extraction, we treat the entire DBH section as one unit
            # Use a small branching height to separate any potential sub-components
            min_z = np.min(dbh_points[:, 2])
            max_z = np.max(dbh_points[:, 2])
            branching_height = (max_z - min_z) * 0.5  # Use middle height as branching point

            # Extract components using connectivity-based algorithm
            components = extract_components(dbh_points, branching_height)

            # Create scalar field for DBH components
            self.create_dbh_components_field(components, dbh_indices)

            # Visualize the DBH components
            self._visualize_dbh_components(components, branching_height, dbh_points)

            # Count total components
            total_components = 1 + len(components['branches']) + (1 if len(components['unassigned']) > 0 else 0)
            QMessageBox.information(self, "DBH Components Extracted",
                                  f"Successfully extracted {total_components} components from DBH points:\n"
                                  f"• Trunk: {len(components['trunk'])} points\n"
                                  f"• Branches: {len(components['branches'])} branches\n"
                                  f"• Unassigned: {len(components['unassigned'])} points")

        except Exception as e:
            QMessageBox.warning(self, "DBH Extraction Error", f"Error extracting DBH components: {str(e)}")
            print(f"DBH component extraction error: {e}")



    def _add_dbh_circle_fitting_for_section(self, dbh_points, section_id, circle_color, avg_color, measurement_label="DBH", run_id=None):
        """Add circle fitting visualization for section points with section-specific naming and colors."""
        if len(dbh_points) == 0:
            return {'circles': [], 'avg_radius': 0.0, 'height_range': 0.0}

        # Get height range for DBH points
        min_z = np.min(dbh_points[:, 2])
        max_z = np.max(dbh_points[:, 2])
        height_range = max_z - min_z

        self.log_to_console(f"📏 Section {section_id} - Z range {min_z:.2f} to {max_z:.2f}m (height: {height_range:.2f}m)")

        # Calculate circle centers (trajectory points) at regular height intervals
        circle_centers = []
        circle_radii = []
        circle_heights = []  # Store heights for DBH extraction
        step = 0.1  # 10cm height steps
        current_z = min_z

        while current_z <= max_z:
            # Extract points within thickness around current height
            thickness = 0.05  # 5cm thickness for more precise fitting
            height_mask = (dbh_points[:, 2] >= current_z - thickness/2) & \
                         (dbh_points[:, 2] <= current_z + thickness/2)
            height_points = dbh_points[height_mask]

            if len(height_points) >= 3:  # Need at least 3 points for circle fitting
                # Calculate bounding circle using centroid method
                cluster_xy = height_points[:, :2]  # Only X,Y coordinates
                centroid = np.mean(cluster_xy, axis=0)
                distances = np.linalg.norm(cluster_xy - centroid, axis=1)
                radius = np.max(distances)

                # Only include circles within reasonable radius bounds (3cm to 50cm for DBH)
                if 0.03 <= radius <= 0.5:
                    circle_centers.append([centroid[0], centroid[1], current_z])
                    circle_radii.append(radius)
                    circle_heights.append(current_z - min_z)  # Height from min_z
                    self.log_to_console(f"✅ Section {section_id} - Z={current_z:.2f}m, center=({centroid[0]:.3f}, {centroid[1]:.3f}), radius={radius:.3f}m")

            current_z += step

        # Display the center trajectory points
        if len(circle_centers) > 0:
            centers_array = np.array(circle_centers)
            centers_cloud = pv.PolyData(centers_array)

            # Use white spheres for trajectory points
            trajectory_name = f'dbh_trajectory_section_{section_id}' if run_id is None else f'dbh_trajectory_run_{run_id}_section_{section_id}'
            self.plotter.add_mesh(centers_cloud, color='white', point_size=8,
                                render_points_as_spheres=True, opacity=1.0,
                                name=trajectory_name, label=f'Section {section_id} Trajectory ({len(circle_centers)} pts)',
                                pickable=False)

            # Compute average center and radius for all circles
            avg_x = np.mean([c[0] for c in circle_centers])
            avg_y = np.mean([c[1] for c in circle_centers])
            final_center = [avg_x, avg_y, 0]  # Z not used for center
            final_radius = np.mean(circle_radii)

            # Display the circles at each height level as filled disks
            if len(circle_centers) > 0:
                # Create all individual circle meshes first
                individual_circles = []
                for i, (center, radius) in enumerate(zip(circle_centers, circle_radii)):
                    # Log the first circle's centroid (lowest Z) before drawing - this is the "last circle" for extrapolation
                    if i == 0:
                        self.log_to_console(f"🎯 LAST CIRCLE (lowest Z): Section {section_id}, Z={center[2]:.2f}m, centroid=({center[0]:.3f}, {center[1]:.3f}), radius={radius:.3f}m")
                    
                    # Create a circle at this height
                    circle = pv.Circle(radius=radius, resolution=32)
                    # Translate circle to the center position
                    circle.translate([center[0], center[1], center[2]], inplace=True)
                    individual_circles.append(circle)

                # Merge all individual circles into a single mesh for better performance
                merged_individual = individual_circles[0].copy()
                for circle in individual_circles[1:]:
                    merged_individual = merged_individual + circle

                # Add the merged mesh to the plotter
                individual_name = f'dbh_individual_circles_section_{section_id}' if run_id is None else f'dbh_individual_circles_run_{run_id}_section_{section_id}'
                self.plotter.add_mesh(merged_individual, color=circle_color, opacity=0.3,
                                    name=individual_name,
                                    label=f'Section {section_id} Individual Circles ({len(circle_centers)} circles)',
                                    pickable=False)

            # Add average circle at EVERY height level where individual circles exist
            self._add_average_dbh_circles_for_section(circle_centers, final_center, final_radius, section_id, avg_color, run_id=run_id)

            self.log_to_console(f"📊 Added section {section_id} with {len(circle_centers)} {measurement_label} circles")

            # Extract DBH at the configured reference height above the tree base using the AVERAGE radius
            # Only compute DBH when this section contains the global DBH height.
            dbh_at_1_3m = None
            dbh_center_at_1_3m = None
            dbh_z_at_1_3m = None
            target_height = getattr(self, 'dbh_reference_height', 1.3)
            tree_base_z = float(np.min(self.current_tree_points[:, 2])) if hasattr(self, 'current_tree_points') and self.current_tree_points is not None else float(min_z)
            dbh_target_z = tree_base_z + target_height

            if len(circle_heights) > 0:
                section_min_z = float(min_z)
                section_max_z = float(max_z)

                if section_min_z <= dbh_target_z <= section_max_z:
                    # Use the fitted circle closest to the global DBH target height.
                    circle_zs = np.array([center[2] for center in circle_centers], dtype=float)
                    target_idx = int(np.argmin(np.abs(circle_zs - dbh_target_z)))
                    avg_radius_at_1_3m = float(circle_radii[target_idx])
                    dbh_at_1_3m = avg_radius_at_1_3m * 2  # Diameter

                    # Use the selected circle center for visualization
                    dbh_center_at_1_3m = np.array([circle_centers[target_idx][0], circle_centers[target_idx][1], dbh_target_z])
                    dbh_z_at_1_3m = dbh_target_z

                    self.log_to_console(f"🌳 DBH at {target_height:.1f}m above base: {dbh_at_1_3m*100:.1f} cm (radius at target Z: {avg_radius_at_1_3m*100:.1f} cm)")

                    # DBH visualization at section level has been removed to avoid duplicate/green overlays.
                    # DBH value is still calculated and returned in section data; trunk-level (blue) overlays
                    # are used for display instead.
                elif measurement_label.lower() == "diameter":
                    self.log_to_console(f"⚠️ Section height range ({height_range:.2f}m) does not include DBH height at {dbh_target_z:.2f}m")
                else:
                    self.log_to_console(f"⚠️ Section height range ({height_range:.2f}m) doesn't reach {target_height:.1f}m for {measurement_label} measurement")

            # Return circle data for volume calculation
            return {
                'circles': list(zip(circle_centers, circle_radii)),
                'avg_radius': final_radius,
                'avg_center': [final_center[0], final_center[1]],  # Save the average center coordinates
                'height_range': height_range,
                'min_z': min_z,
                'max_z': max_z,
                'dbh_at_1_3m': dbh_at_1_3m,  # Diameter at 1.3m in meters (using avg radius)
                'dbh_center_at_1_3m': dbh_center_at_1_3m.tolist() if dbh_center_at_1_3m is not None else None,
                'dbh_z_at_1_3m': dbh_z_at_1_3m,
                'dbh_target_z': dbh_target_z
            }
        else:
            self.log_to_console(f"⚠️ No valid circles found for section {section_id}")
            return {'circles': [], 'avg_radius': 0.0, 'height_range': 0.0, 'dbh_at_1_3m': None, 'dbh_target_z': None}

    def _calculate_section_volume(self, section_data):
        """Calculate the volume of a section based on fitted circles using cylinder approximation."""
        if not section_data or 'avg_radius' not in section_data or section_data['avg_radius'] <= 0:
            return 0.0

        # Since we use the average radius for all height levels, this creates a cylinder
        avg_radius = section_data['avg_radius']
        height_range = section_data.get('height_range', 0.0)

        if height_range <= 0:
            return 0.0

        # Volume of cylinder: V = π × r² × h
        cylinder_volume = np.pi * (avg_radius ** 2) * height_range

        return cylinder_volume

    def _check_ground_proximity_and_extrapolate(self, section_data, selected_points, section_id, circle_color, avg_color):
        """Check if the lowest circle is close to ground and extrapolate downward if needed."""
        self.log_to_console(f"🔍 Checking ground proximity for section {section_id}")
        
        if not section_data or 'circles' not in section_data or not section_data['circles']:
            self.log_to_console(f"⚠️ No circle data available for section {section_id}")
            return section_data

        # Determine ground level - use minimum Z of all tree points or selected points
        if hasattr(self, 'current_tree_points') and self.current_tree_points is not None:
            ground_level = np.min(self.current_tree_points[:, 2])
            self.log_to_console(f"🌍 Ground level from tree points: {ground_level:.2f}m")
        else:
            ground_level = np.min(selected_points[:, 2])
            self.log_to_console(f"🌍 Ground level from selected points: {ground_level:.2f}m")

        # Get the lowest circle height
        min_z = section_data.get('min_z', float('inf'))
        self.log_to_console(f"📏 Lowest circle Z: {min_z:.2f}m")
        
        if min_z == float('inf'):
            self.log_to_console(f"⚠️ No min_z found in section data")
            return section_data

        # Check proximity to ground (within 0.5m tolerance)
        proximity_threshold = 0.5  # 50cm from ground
        distance_to_ground = min_z - ground_level
        
        self.log_to_console(f"📊 Distance to ground: {distance_to_ground:.2f}m (threshold: {proximity_threshold:.2f}m)")

        if distance_to_ground <= proximity_threshold:
            # Already close to ground, no extrapolation needed
            self.log_to_console(f"✅ Section {section_id} already close to ground - no extrapolation needed")
            return section_data

        self.log_to_console(f"📏 Section {section_id} - Lowest circle at {min_z:.2f}m, ground at {ground_level:.2f}m (gap: {distance_to_ground:.2f}m)")
        self.log_to_console(f"🔄 Extrapolating downward to reach ground...")

        # Extract existing circles
        existing_circles = section_data['circles']
        if not existing_circles:
            self.log_to_console(f"⚠️ No existing circles to extrapolate from")
            return section_data

        # Get the step size used for circle fitting (typically 0.1m)
        step = 0.1  # 10cm steps

        # Calculate how many additional circles we need
        num_additional_circles = int(np.ceil(distance_to_ground / step))
        if num_additional_circles > 20:  # Limit to prevent excessive extrapolation
            num_additional_circles = 20
            self.log_to_console(f"⚠️ Limiting extrapolation to 20 circles to prevent excessive extension")

        self.log_to_console(f"📏 Planning to add {num_additional_circles} extrapolated circles")

        # Get the last (lowest) circle data for extrapolation
        last_center, last_radius = existing_circles[-1]

        # Extrapolate downward (batch circles into single mesh for performance)
        extrapolated_circles = []
        extrapolated_meshes = []
        current_z = min_z - step

        for i in range(num_additional_circles):
            if current_z < ground_level:
                self.log_to_console(f"🛑 Stopping extrapolation at Z={current_z:.2f}m (below ground level {ground_level:.2f}m)")
                break  # Don't go below ground

            # Use the same center X,Y as the last circle, but at lower Z
            # Keep the same radius as the last circle for simplicity
            extrapolated_center = [last_center[0], last_center[1], current_z]
            extrapolated_circles.append((extrapolated_center, last_radius))

            self.log_to_console(f"➕ Added extrapolated circle at Z={current_z:.2f}m, center=({last_center[0]:.3f}, {last_center[1]:.3f}), radius={last_radius:.3f}m")

            # Build circle mesh but defer adding to plotter
            circle = pv.Circle(radius=last_radius, resolution=32)
            circle.translate(extrapolated_center, inplace=True)
            extrapolated_meshes.append(circle)

            current_z -= step

        # Merge all extrapolated circles into a single mesh for instant rendering
        if extrapolated_meshes:
            merged_extrapolated = extrapolated_meshes[0].copy()
            for mesh in extrapolated_meshes[1:]:
                merged_extrapolated = merged_extrapolated + mesh
            self.plotter.add_mesh(merged_extrapolated, color=circle_color, opacity=0.3,
                                name=f'dbh_circle_section_{section_id}_extrapolated',
                                label=f'Section {section_id} Extrapolated ({len(extrapolated_meshes)} circles)',
                                pickable=False)

        # Add extrapolated circles to the section data
        all_circles = existing_circles + extrapolated_circles

        # Recalculate averages with extrapolated circles
        all_centers = [center for center, _ in all_circles]
        all_radii = [radius for _, radius in all_circles]

        new_avg_x = np.mean([c[0] for c in all_centers])
        new_avg_y = np.mean([c[1] for c in all_centers])
        new_avg_radius = np.mean(all_radii)

        new_min_z = min(c[2] for c in all_centers)
        new_max_z = max(c[2] for c in all_centers)
        new_height_range = new_max_z - new_min_z

        # Update section data
        updated_section_data = {
            'circles': all_circles,
            'avg_radius': new_avg_radius,
            'avg_center': [new_avg_x, new_avg_y],
            'height_range': new_height_range,
            'min_z': new_min_z,
            'max_z': new_max_z,
            'extrapolated': True,
            'original_height_range': section_data.get('height_range', 0.0),
            'original_min_z': section_data.get('min_z', float('inf')),
            'original_max_z': section_data.get('max_z', float('inf')),
            'extrapolated_height_range': new_height_range,
            'extrapolated_min_z': new_min_z,
            'extrapolated_max_z': new_max_z,
            'num_extrapolated_circles': len(extrapolated_circles),
            'ground_level_used': ground_level
        }

        # Add average circles for extrapolated section
        extrapolated_centers = [center for center, _ in extrapolated_circles]
        if extrapolated_centers:
            self._add_average_dbh_circles_for_section(extrapolated_centers,
                                                    [new_avg_x, new_avg_y, 0],
                                                    new_avg_radius,
                                                    f"{section_id}_extrapolated",
                                                    avg_color)

        self.log_to_console(f"✅ Added {len(extrapolated_circles)} extrapolated circles, extended height range to {new_height_range:.2f}m")
        self.log_to_console(f"📊 Updated averages - radius: {new_avg_radius:.3f}m, center: ({new_avg_x:.3f}, {new_avg_y:.3f})")

        return updated_section_data

    def _check_global_ground_proximity_and_extrapolate(self):
        """Check ground proximity across all accumulated sections and extrapolate if needed."""
        if not self.accumulated_volume_sections:
            return

        self.log_to_console(f"🌍 Checking global ground proximity across {len(self.accumulated_volume_sections)} sections")

        # Determine ground level from the global LAS dataset bounding box (true ground)
        if self.las_data is not None:
            # Use the global bounding box min z as ground level
            all_z_values = np.array(self.las_data.z)
            ground_level = np.min(all_z_values)
            self.log_to_console(f"🌍 Global ground level from LAS dataset: {ground_level:.2f}m (true ground)")
            
            # Stop extrapolation 0.5m above ground to avoid ground interference
            extrapolation_stop_level = ground_level + 0.5
            self.log_to_console(f"📏 Extrapolation will stop at Z: {extrapolation_stop_level:.2f}m (0.5m above ground)")
        else:
            self.log_to_console(f"⚠️ No LAS data available for ground level detection")
            return

        # Find the lowest fitted circle across all sections (not just the min Z of input points)
        global_min_fitted_z = float('inf')
        lowest_section = None
        
        for section in self.accumulated_volume_sections:
            if 'circle_data' in section and section['circle_data']:
                circles = section['circle_data'].get('circles', [])
                if circles:
                    # Get the minimum Z from actual fitted circles
                    section_min_fitted_z = min(center[2] for center, _ in circles)
                    if section_min_fitted_z < global_min_fitted_z:
                        global_min_fitted_z = section_min_fitted_z
                        lowest_section = section

        if global_min_fitted_z == float('inf'):
            self.log_to_console(f"⚠️ No fitted circles found in any section")
            return

        global_min_z = global_min_fitted_z  # Use the actual lowest fitted circle Z

        if global_min_z == float('inf'):
            self.log_to_console(f"⚠️ No valid circle data found in any section")
            return

        self.log_to_console(f"📏 Global lowest circle Z: {global_min_z:.2f}m (from section {lowest_section['section_id'] if lowest_section else 'unknown'})")

        # Check proximity to stop level
        proximity_threshold = 0.0  # Always extrapolate if below stop level
        distance_to_stop = global_min_z - extrapolation_stop_level
        
        self.log_to_console(f"📊 Global distance to stop level: {distance_to_stop:.2f}m (stopping 0.5m above ground)")

        if distance_to_stop <= proximity_threshold:
            self.log_to_console(f"✅ Global lowest circle already at or above stop level - no extrapolation needed")
            return

        self.log_to_console(f"🔄 Global extrapolation needed - gap: {distance_to_stop:.2f}m")
        self.log_to_console(f"🔄 Extrapolating downward from global lowest point...")

        # Use the lowest section's data for extrapolation
        if not lowest_section or 'circle_data' not in lowest_section:
            self.log_to_console(f"⚠️ No valid lowest section data for extrapolation")
            return

        lowest_circle_data = lowest_section['circle_data']
        existing_circles = lowest_circle_data.get('circles', [])
        
        if not existing_circles:
            self.log_to_console(f"⚠️ No circles in lowest section")
            return

        # Get the step size
        step = 0.1  # 10cm steps

        # Calculate how many additional circles we need
        num_additional_circles = int(np.ceil(distance_to_stop / step))
        
        # Apply safety limit to prevent excessive extrapolation
        max_extrapolated_circles = 100
        if num_additional_circles > max_extrapolated_circles:
            num_additional_circles = max_extrapolated_circles
            self.log_to_console(f"📏 Limiting extrapolation to {max_extrapolated_circles} circles for safety")
        
        self.log_to_console(f"📏 Planning to add {num_additional_circles} global extrapolated circles (until ground level)")

        # Use the centroid from the lowest individual circle (same as the last red avg circle position)
        lowest_circle_center, lowest_circle_radius = existing_circles[0]  # First circle is lowest Z
        extrapolation_centroid = [lowest_circle_center[0], lowest_circle_center[1]]
        
        self.log_to_console(f"🎯 LOWEST CIRCLE (for extrapolation): Section {lowest_section['section_id']}, Z={lowest_circle_center[2]:.2f}m, centroid=({lowest_circle_center[0]:.3f}, {lowest_circle_center[1]:.3f}), radius={lowest_circle_radius:.3f}m")
        self.log_to_console(f"📍 Using lowest circle centroid for extrapolation (matches red avg circle position): ({extrapolation_centroid[0]:.3f}, {extrapolation_centroid[1]:.3f})m")

        # Use the average radius across all circles from the lowest section for consistency
        all_radii = []
        for section in self.accumulated_volume_sections:
            if 'circle_data' in section and section['circle_data']:
                section_circles = section['circle_data'].get('circles', [])
                for _, radius in section_circles:
                    all_radii.append(radius)
        
        global_avg_radius = np.mean(all_radii) if all_radii else 0.1  # Default fallback
        self.log_to_console(f"📏 Global average radius: {global_avg_radius:.3f}m (from {len(all_radii)} total circles)")

        # Start extrapolation from the lowest measured circle Z
        current_z = global_min_z

        # Create a new global extrapolated section
        extrapolated_circles = []

        # Calculate extrapolation z levels
        extrapolation_z_levels = []
        current_z = global_min_z - step
        for _ in range(num_additional_circles):
            if current_z < extrapolation_stop_level:
                break
            extrapolation_z_levels.append(current_z)
            current_z -= step

        # If the last level is above stop level, add stop level
        if extrapolation_z_levels and extrapolation_z_levels[-1] > extrapolation_stop_level:
            extrapolation_z_levels.append(extrapolation_stop_level)

        # Now add circles for each z in extrapolation_z_levels
        extrapolated_circle_meshes = []
        for i, z in enumerate(extrapolation_z_levels):
            extrapolated_center = [extrapolation_centroid[0], extrapolation_centroid[1], z]
            extrapolated_circles.append((extrapolated_center, global_avg_radius))

            # Log the first extrapolated circle's centroid
            if i == 0:
                self.log_to_console(f"🎯 FIRST EXTRAPOLATED CIRCLE: Z={z:.2f}m, centroid=({extrapolation_centroid[0]:.3f}, {extrapolation_centroid[1]:.3f}), radius={global_avg_radius:.3f}m")

            self.log_to_console(f"➕ Added global extrapolated circle at Z={z:.2f}m, center=({extrapolation_centroid[0]:.3f}, {extrapolation_centroid[1]:.3f}), radius={global_avg_radius:.3f}m")

            # Create circle mesh but don't add to plotter yet
            circle = pv.Circle(radius=global_avg_radius, resolution=32)
            circle.translate(extrapolated_center, inplace=True)
            extrapolated_circle_meshes.append(circle)

        # Merge all extrapolated circles into a single mesh for better performance
        if extrapolated_circle_meshes:
            merged_extrapolated = extrapolated_circle_meshes[0].copy()
            for circle in extrapolated_circle_meshes[1:]:
                merged_extrapolated = merged_extrapolated + circle

            # Add the merged mesh to the plotter
            self.plotter.add_mesh(merged_extrapolated, color='cyan', opacity=0.3,
                                name=f'dbh_global_extrapolated_circles',
                                label=f'Global Extrapolated Circles ({len(extrapolated_circle_meshes)} circles)',
                                pickable=False)

        if extrapolated_circles:
            # Create a new global extrapolated section
            global_section_id = "global_extrapolated"
            
            # Calculate averages for extrapolated circles
            all_centers = [center for center, _ in extrapolated_circles]
            all_radii = [radius for _, radius in extrapolated_circles]
            
            global_avg_x = np.mean([c[0] for c in all_centers])
            global_avg_y = np.mean([c[1] for c in all_centers])
            global_avg_radius = np.mean(all_radii)
            
            global_min_z_new = min(c[2] for c in all_centers)
            global_max_z_new = max(c[2] for c in all_centers)
            global_height_range = global_max_z_new - global_min_z_new

            # Create extrapolated section data
            extrapolated_section_data = {
                'circles': extrapolated_circles,
                'avg_radius': global_avg_radius,
                'avg_center': [global_avg_x, global_avg_y],
                'height_range': global_height_range,
                'min_z': global_min_z_new,
                'max_z': global_max_z_new
            }

            # Add average circles for global extrapolated section
            self._add_average_dbh_circles_for_section(all_centers,
                                                    [global_avg_x, global_avg_y, 0],
                                                    global_avg_radius,
                                                    global_section_id,
                                                    'red')

            # Add to accumulated sections
            global_section_info = {
                'tree_id': lowest_section['tree_id'] if lowest_section else self.current_tree_id,
                'section_id': global_section_id,
                'points': np.array([]),  # No original points for extrapolated
                'point_color': 'cyan',
                'circle_color': 'cyan',
                'volume': self._calculate_section_volume(extrapolated_section_data),
            'circle_data': extrapolated_section_data,
            'extrapolated': True,
            'original_height_range': 0.0,
            'original_min_z': global_min_z,
            'original_max_z': global_min_z,
            'extrapolated_height_range': global_height_range,
            'extrapolated_min_z': global_min_z_new,
            'extrapolated_max_z': global_max_z_new,
            'num_extrapolated_circles': len(extrapolated_circles),
            'ground_level_used': ground_level
            }
            self.accumulated_volume_sections.append(global_section_info)
            # Calculate total cylinder height across all sections
            all_z = []
            for section in self.accumulated_volume_sections:
                if 'circle_data' in section and section['circle_data']:
                    circles = section['circle_data'].get('circles', [])
                    for center, _ in circles:
                        all_z.append(center[2])
            
            if all_z:
                total_min_z = min(all_z)
                total_max_z = max(all_z)
                total_height = total_max_z - total_min_z
                self.log_to_console(f"📐 Total cylinder height: {total_height:.2f}m (from Z {total_min_z:.2f}m to {total_max_z:.2f}m)")

    def _add_average_dbh_circles_for_section(self, circle_centers, avg_center, avg_radius, section_id, avg_color, run_id=None):
        """Add average circle at every height level for a specific section."""
        if len(circle_centers) == 0:
            return

        try:
            # Create all average circle meshes first
            avg_circles = []
            for i, center in enumerate(circle_centers):
                height_z = center[2]  # Z coordinate of this height level

                # Create average circle at this height
                avg_circle = pv.Circle(radius=avg_radius, resolution=64)
                avg_circle.translate([center[0], center[1], height_z], inplace=True)

                # Make it wireframe (boundary only)
                avg_circle_wireframe = pv.PolyData(avg_circle.points)
                avg_circle_wireframe.lines = avg_circle.lines
                
                avg_circles.append(avg_circle_wireframe)

            # Merge all average circles into a single mesh for better performance
            if len(avg_circles) > 0:
                merged_average = avg_circles[0].copy()
                for circle in avg_circles[1:]:
                    merged_average = merged_average + circle

                # Add the merged mesh to the plotter
                actor_name = f'dbh_avg_circles_section_{section_id}' if run_id is None else f'dbh_avg_circles_run_{run_id}_section_{section_id}'
                self.plotter.add_mesh(merged_average, color=avg_color, line_width=3, opacity=0.9,
                                    name=actor_name,
                                    label=f'Section {section_id} Avg Circles ({len(circle_centers)} circles)',
                                    pickable=False)

            # Add a single center marker for the average center trajectory
            centers_array = np.array([[center[0], center[1], center[2]] for center in circle_centers])
            avg_centers_cloud = pv.PolyData(centers_array)
            traj_name = f'dbh_avg_trajectory_section_{section_id}' if run_id is None else f'dbh_avg_trajectory_run_{run_id}_section_{section_id}'
            self.plotter.add_mesh(avg_centers_cloud, color=avg_color, point_size=6,
                                render_points_as_spheres=True, opacity=1.0,
                                name=traj_name, label=f'Section {section_id} Avg Trajectory ({len(circle_centers)} pts)',
                                pickable=False)

            self.log_to_console(f"🎯 Added section {section_id} average circles at {len(circle_centers)} height levels (R={avg_radius:.3f}m)")

        except Exception as e:
            self.log_to_console(f"❌ Error adding average DBH circles for section {section_id}: {str(e)}")
            print(f"Error in _add_average_dbh_circles_for_section: {e}")

    def calculate_volume_from_selection(self):
        """
        Perform circle fitting on selected points for volume calculation.
        OVERLAYS results on existing tree visualization - does NOT clear the view.
        Accumulates results from multiple selections for comprehensive volume analysis.
        """
        if not hasattr(self, 'current_tree_points') or self.current_tree_points is None:
            QMessageBox.warning(self, "No Tree Points", "No tree points available. Please visualize a tree first.")
            return

        if self.selected_point_indices is None or len(self.selected_point_indices) == 0:
            n_points = len(self.current_tree_points)
            has_branch_detection = (
                hasattr(self, 'branch_assignment') and
                self.branch_assignment is not None and
                len(self.branch_assignment) == n_points
            )
            has_trunk_detection = (
                hasattr(self, 'trunk_assignment') and
                self.trunk_assignment is not None and
                len(self.trunk_assignment) == n_points
            )

            if has_branch_detection or has_trunk_detection:
                self.selected_point_indices = np.arange(n_points, dtype=int)
                mode_msg = "branches/trunks" if has_branch_detection and has_trunk_detection else ("branches" if has_branch_detection else "trunks")
                self.log_to_console(f"ℹ️ No manual selection found. Using all {n_points} current tree points because {mode_msg} are already detected.")
            else:
                QMessageBox.warning(self, "No Selection", "No points selected. Please use the polygon selection tool first.")
                return

        # Validate selected indices are within the range of current visualization points.
        # If they appear to be original LAS indices (out-of-range), try remapping to visualization indices.
        try:
            sel = np.asarray(self.selected_point_indices)
            if sel.size > 0 and len(self.current_tree_points) > 0 and np.max(sel) >= len(self.current_tree_points):
                # Attempt to build mapping from original LAS indices -> visualization indices
                global_indices = None
                try:
                    if hasattr(self, 'all_masks') and self.all_masks is not None and len(self.all_masks) > 0:
                        per_mask_indices = [np.where(mask)[0] for mask in self.all_masks]
                        global_indices = np.concatenate(per_mask_indices)
                    elif hasattr(self, 'current_mask') and self.current_mask is not None and len(self.current_mask) == len(self.las_data.points):
                        global_indices = np.where(self.current_mask)[0]
                except Exception:
                    global_indices = None

                if global_indices is not None:
                    mapping = {int(orig): int(viz) for viz, orig in enumerate(global_indices)}
                    remapped = [mapping[int(x)] for x in sel if int(x) in mapping]
                    if len(remapped) == 0:
                        QMessageBox.warning(self, "Selection Index Error", "Selected indices appear out of range and could not be remapped to the current view. Please re-select points.")
                        return
                    self.selected_point_indices = np.array(remapped, dtype=int)
                    self.log_to_console("🔁 Remapped selection indices from original LAS indices to current visualization indices.")
                else:
                    QMessageBox.warning(self, "Selection Index Error", "Selected indices are out of range for the current view and no index mapping is available. Please re-select points.")
                    return
        except Exception as e:
            # In case of any unexpected failure during remapping, abort gracefully
            self.log_to_console(f"⚠️ Error validating selection indices: {e}")
            QMessageBox.warning(self, "Selection Index Error", f"Error validating selection indices: {e}")
            return

        try:
            # Only calculate volume if trunk/branch detection state has changed since last calculation
            current_sig = (getattr(self, 'current_tree_id', None),
                           getattr(self, '_trunk_detection_version', 0),
                           getattr(self, '_branch_detection_version', 0))
            if getattr(self, '_last_volume_calc_signature', None) == current_sig:
                self.log_to_console("ℹ️ Volume calculation skipped: no change in trunk/branch detection since last calculation.")
                return

            volume_groups, is_branch_mode = self._get_volume_groups_from_selection()
            if not volume_groups:
                QMessageBox.warning(self, "No Valid Groups", "No valid point groups found for volume calculation.")
                return

            # Start a new overlay run so every section in this run gets unique actor names.
            self._volume_calc_run_id = int(getattr(self, '_volume_calc_run_id', 0)) + 1
            current_run_id = self._volume_calc_run_id
            self.log_to_console(f"🔖 Starting volume overlay run {current_run_id}")
            
            # Determine tree_id for this section based on selected points
            if hasattr(self, 'current_tree_ids') and self.current_tree_ids is not None:
                selected_tree_ids = self.current_tree_ids[self.selected_point_indices]
                # Use the tree ID that appears most frequently in the selection
                unique_ids, counts = np.unique(selected_tree_ids, return_counts=True)
                section_tree_id = unique_ids[np.argmax(counts)]
                
                # Log if points from multiple trees were selected
                if len(unique_ids) > 1:
                    self.log_to_console(f"⚠️ Selected points from {len(unique_ids)} trees, assigning section to tree {section_tree_id} (most points)")
            else:
                # Fallback to current_tree_id
                section_tree_id = self.current_tree_id
            
            # Remove existing accumulated sections for this tree so each successful run is fresh
            try:
                prev_count = len(self.accumulated_volume_sections)
                self.accumulated_volume_sections = [s for s in self.accumulated_volume_sections if str(s.get('tree_id', '')) != str(section_tree_id)]
                removed = prev_count - len(self.accumulated_volume_sections)
                if removed > 0:
                    self.log_to_console(f"🧹 Cleared {removed} previous section(s) for tree {section_tree_id} to start a fresh volume calculation")
            except Exception:
                pass

            # Start section numbering fresh for this tree
            section_id = 1

            total_selected_points = sum(len(group_points) for _, _, group_points in volume_groups)
            if is_branch_mode:
                self.log_to_console(
                    f"📏 Branch-wise volume mode: {len(volume_groups)} branches, {total_selected_points} selected points (tree {section_tree_id})"
                )
            else:
                self.log_to_console(
                    f"📏 Standard volume mode: section {section_id}, {total_selected_points} selected points (tree {section_tree_id})"
                )

            # Debug: Log accumulated sections count
            self.log_to_console(f"🔍 Current accumulated sections before adding: {len(self.accumulated_volume_sections)}")

            # Define colors for different sections (cycling through a palette)
            section_colors = ['cyan', 'magenta', 'yellow', 'lime', 'orange', 'pink', 'purple', 'brown']
            point_color = section_colors[(section_id - 1) % len(section_colors)]
            circle_color = section_colors[(section_id - 1) % len(section_colors)]
            avg_color = 'red'  # Keep average circles red for consistency

            last_section_id = None
            last_section_points = 0
            last_section_volume = 0.0
            last_section_data = None
            section_metric_values_cm = []

            if self.plotter is not None:
                # NEVER clear the plotter - overlay volume results on existing tree visualization
                # This preserves the tree visualization while adding volume analysis

                # Suppress rendering during batch additions for performance
                self.plotter.suppress_rendering = True

                for group_branch_id, _, group_points in volume_groups:
                    point_color = section_colors[(section_id - 1) % len(section_colors)]
                    circle_color = section_colors[(section_id - 1) % len(section_colors)]
                    branch_suffix = f" | B{group_branch_id}" if group_branch_id is not None else ""
                    branch_trunk_id = None
                    if is_branch_mode and group_branch_id is not None and hasattr(self, 'branch_meta'):
                        branch_meta = self.branch_meta.get(int(group_branch_id), {})
                        branch_trunk_id = branch_meta.get('trunk_id')

                    # Show selected points for this section
                    selected_cloud = pv.PolyData(group_points)
                    self.plotter.add_points(
                        selected_cloud,
                        color=point_color,
                        point_size=4,
                        opacity=0.6,
                        name=f'volume_section_{section_id}_points',
                        label=f'Section {section_id}{branch_suffix} Points ({len(group_points)} pts)',
                        pickable=False
                    )

                    # Add circle fitting to selected points with section-specific naming
                    measurement_label = "Diameter" if is_branch_mode else "DBH"
                    section_data = self._add_dbh_circle_fitting_for_section(
                        group_points,
                        section_id,
                        circle_color,
                        avg_color,
                        measurement_label=measurement_label,
                        run_id=current_run_id
                    )

                    # Calculate volume for this section
                    section_volume = self._calculate_section_volume(section_data)

                    # Store this section's data including volume
                    section_info = {
                        'tree_id': section_tree_id,
                        'section_id': section_id,
                        'trunk_id': int(branch_trunk_id) if branch_trunk_id is not None else None,
                        'branch_id': int(group_branch_id) if group_branch_id is not None else None,
                        'points': group_points.copy(),
                        'point_color': point_color,
                        'circle_color': circle_color,
                        'volume': section_volume,
                        'circle_data': section_data
                    }

                    # Avoid appending duplicate sections when re-running calculation without changes.
                    # Consider duplicate if tree_id, trunk_id, branch_id match and
                    # point count, centroid and volume are effectively identical.
                    is_dup = False
                    try:
                        new_n = len(section_info['points'])
                        new_centroid = np.mean(section_info['points'], axis=0) if new_n > 0 else np.array([0.0, 0.0, 0.0])
                        new_vol = float(section_info.get('volume', 0.0) or 0.0)

                        for ex in self.accumulated_volume_sections:
                            try:
                                if ex.get('tree_id') != section_info.get('tree_id'):
                                    continue
                                if ex.get('trunk_id') != section_info.get('trunk_id'):
                                    continue
                                if ex.get('branch_id') != section_info.get('branch_id'):
                                    continue

                                ex_n = len(ex.get('points') or [])
                                if ex_n != new_n:
                                    continue

                                ex_centroid = np.mean(ex.get('points'), axis=0) if ex_n > 0 else np.array([0.0, 0.0, 0.0])
                                if np.linalg.norm(ex_centroid - new_centroid) > 1e-3:
                                    continue

                                ex_vol = float(ex.get('volume', 0.0) or 0.0)
                                if abs(ex_vol - new_vol) > 1e-6:
                                    continue

                                # All checks passed — treat as duplicate
                                is_dup = True
                                break
                            except Exception:
                                continue
                    except Exception:
                        is_dup = False

                    if is_dup:
                        self.log_to_console(f"🔁 Skipped duplicate section {section_id} for tree {section_tree_id} (no changes detected)")
                    else:
                        self.accumulated_volume_sections.append(section_info)

                    last_section_id = section_id
                    last_section_points = len(group_points)
                    last_section_volume = section_volume
                    last_section_data = section_data

                    if group_branch_id is not None:
                        self.log_to_console(
                            f"📏 Section {section_id} (Branch B{group_branch_id}): {len(group_points)} pts, {section_volume:.4f} m³"
                        )
                    else:
                        self.log_to_console(
                            f"📏 Section {section_id}: {len(group_points)} pts, {section_volume:.4f} m³"
                        )

                    if is_branch_mode:
                        avg_radius = section_data.get('avg_radius') if section_data else None
                        diameter_cm = (avg_radius * 2 * 100) if avg_radius else None
                        branch_label = f"B{group_branch_id}" if group_branch_id is not None else "N/A"
                        metric_text = f"{diameter_cm:.1f} cm" if diameter_cm is not None else "N/A"
                        self.log_to_console(
                            f"   ↳ Diameter (section avg) | Section {section_id} | Branch {branch_label}: {metric_text}"
                        )
                    else:
                        dbh_at_1_3m = section_data.get('dbh_at_1_3m') if section_data else None
                        dbh_cm = (dbh_at_1_3m * 100) if dbh_at_1_3m else None
                        if dbh_cm is not None:
                            section_metric_values_cm.append(dbh_cm)
                        metric_text = f"{dbh_cm:.1f} cm" if dbh_cm is not None else "N/A"
                        self.log_to_console(
                            f"   ↳ DBH @{getattr(self, 'dbh_reference_height', 1.3):.1f}m | Section {section_id}: {metric_text}"
                        )

                    section_id += 1

                # Re-enable rendering after batch additions
                self.plotter.suppress_rendering = False
                self.plotter.render()

                # Perform global ground proximity check in all modes.
                # In branch mode this helps DBH estimation when a trunk misses the exact DBH plane.
                self._check_global_ground_proximity_and_extrapolate()

                # Debug: Log accumulated sections count after adding
                self.log_to_console(f"✅ Total accumulated sections now: {len(self.accumulated_volume_sections)}")

                # Build and emit trunk summary table for the current accumulated results
                trunk_summary, trunk_summary_lines, trunk_total_volume = self._build_trunk_volume_summary_table()
                trunk_dbh_summary, trunk_dbh_lines, trunk_dbh_details = self._build_trunk_dbh_summary_table() if is_branch_mode else ({}, [], {})

                if is_branch_mode and trunk_dbh_details:
                    self._add_trunk_dbh_overlays(trunk_dbh_details)

                if trunk_summary:
                    self.log_to_console(f"📦 Total trunks used for volume: {len(trunk_summary)}")
                    self.log_to_console("📋 Trunk volume summary:")
                    for line in trunk_summary_lines:
                        self.log_to_console(line)
                        print(line)
                    self.log_to_console(f"📊 Combined trunk volume: {trunk_total_volume:.4f} m³")
                    print(f"Combined trunk volume: {trunk_total_volume:.4f} m³")
                else:
                    self.log_to_console("📦 Total trunks used for volume: 0")
                    self.log_to_console("📋 Trunk volume summary: none")
                    print("Total trunks used for volume: 0")
                    print("Trunk volume summary: none")

                if is_branch_mode:
                    if trunk_dbh_summary:
                        dbh_msg = f"📐 Trunk DBH summary ({getattr(self, 'dbh_reference_height', 1.3):.1f}m above base):"
                        self.log_to_console(dbh_msg)
                        for line in trunk_dbh_lines:
                            self.log_to_console(line)
                            print(line)
                    else:
                        dbh_msg = f"📐 Trunk DBH summary ({getattr(self, 'dbh_reference_height', 1.3):.1f}m above base): none"
                        self.log_to_console(dbh_msg)

                # Update info text to show accumulated results
                total_sections = len(self.accumulated_volume_sections)
                total_points = sum(len(section['points']) for section in self.accumulated_volume_sections)
                total_volume = sum(section['volume'] for section in self.accumulated_volume_sections)

                # Show measurement text based on mode
                dbh_h = getattr(self, 'dbh_reference_height', 1.3)
                if is_branch_mode:
                    if trunk_dbh_summary:
                        dbh_lines = []
                        for key, dbh in sorted(trunk_dbh_summary.items()):
                            parts = str(key).rsplit('_', 1)
                            if len(parts) == 2:
                                tree_id, trunk_id = parts[0], parts[1]
                                dbh_lines.append(f"Tree{tree_id}/T{trunk_id}: {dbh:.1f} cm")
                            else:
                                dbh_lines.append(f"T{key}: {dbh:.1f} cm")
                        dbh_text = "\nDBH by trunk: " + "; ".join(dbh_lines)
                    else:
                        dbh_text = "\nDBH by trunk: N/A"
                else:
                    dbh_at_1_3m = last_section_data.get('dbh_at_1_3m') if last_section_data else None
                    dbh_text = f"\nLast DBH @{dbh_h:.1f}m: {dbh_at_1_3m*100:.1f} cm" if dbh_at_1_3m else f"\nLast DBH @{dbh_h:.1f}m: N/A"

                metric_summary_text = ""
                if is_branch_mode and trunk_dbh_summary:
                    metric_summary_text = (
                        f"\nDBH @{dbh_h:.1f}m (all trunks): min {np.min(list(trunk_dbh_summary.values())):.1f}, "
                        f"max {np.max(list(trunk_dbh_summary.values())):.1f}, avg {np.mean(list(trunk_dbh_summary.values())):.1f} cm"
                    )
                elif section_metric_values_cm:
                    metric_name = f"DBH @{dbh_h:.1f}m (all sections)" if not is_branch_mode else "Diameter (all sections)"
                    metric_summary_text = (
                        f"\n{metric_name}: min {np.min(section_metric_values_cm):.1f}, "
                        f"max {np.max(section_metric_values_cm):.1f}, avg {np.mean(section_metric_values_cm):.1f} cm"
                    )

                mode_text = "Mode: Branch-wise" if is_branch_mode else "Mode: Standard"

                trunk_summary_overlay = ""
                if trunk_summary:
                    compact_rows = []
                    for tid in sorted(trunk_summary.keys()):
                        data = trunk_summary[tid]
                        compact_rows.append(f"T{tid}: {data['total_volume']:.4f} m³ / {data['num_branches']} branches")
                    trunk_summary_overlay = "\nTrunks Used: " + str(len(trunk_summary)) + "\n" + "\n".join(compact_rows)

                info_text = (f"Accumulated Volume Calculation\n"
                            f"{mode_text}\n"
                            f"Sections: {total_sections}\n"
                            f"Total Points: {total_points}\n"
                            f"Combined Trunk Volume: {total_volume:.4f} m³\n"
                            f"Trunks Used: {len(trunk_summary) if trunk_summary else 0}"
                            f"{trunk_summary_overlay}"
                            f"{metric_summary_text}"
                            f"{dbh_text}\n"
                            f"Last Section: {last_section_id} ({last_section_points} pts, {last_section_volume:.4f} m³)")

                # Remove previous info text if it exists
                try:
                    self.plotter.remove_actor('volume_info_text')
                except:
                    pass

                self.plotter.add_text(info_text, position='upper_left', font_size=10, color='#FFFFFF',
                                    name='volume_info_text')
                self._set_volume_overlay_actors_unpickable()

                # Ensure plotter updates to show all accumulated sections
                self.plotter.update()
                # NOTE: Don't reset_camera() here - preserve user's current view of the tree

                # Mark that volume has been calculated for this detection state
                try:
                    self._last_volume_calc_signature = (
                        getattr(self, 'current_tree_id', None),
                        getattr(self, '_trunk_detection_version', 0),
                        getattr(self, '_branch_detection_version', 0)
                    )
                    self.log_to_console(f"✅ Recorded volume calculation state: tree={self._last_volume_calc_signature[0]}, trunk_v={self._last_volume_calc_signature[1]}, branch_v={self._last_volume_calc_signature[2]}")
                except Exception:
                    pass

            # Enable clear button now that we have results
            self.clear_volume_button.setEnabled(True)
            self.save_volume_button.setEnabled(True)
            self.export_trunks_button.setEnabled(True)

        except Exception as e:
            QMessageBox.warning(self, "Volume Calculation Error", f"Error performing volume calculation: {str(e)}")
            print(f"Volume calculation error: {e}")

    def _get_volume_groups_from_selection(self):
        """Return grouped points for volume calculation as (branch_id, indices, points)."""
        selected_indices = np.asarray(self.selected_point_indices)
        selected_points = self.current_tree_points[selected_indices]

        # Default behavior: all selected points as one section
        default_group = [(None, selected_indices, selected_points)]

        if not hasattr(self, 'branch_assignment') or self.branch_assignment is None:
            # Ensure no trunk grouping leftover
            self.volume_groups_by_trunk = {}
            return default_group, False

        if len(self.branch_assignment) != len(self.current_tree_points):
            self.log_to_console("⚠️ Branch assignment size mismatch with current tree points. Falling back to standard volume mode.")
            return default_group, False

        selected_branch_ids = self.branch_assignment[selected_indices]
        unique_branch_ids = sorted(int(branch_id) for branch_id in np.unique(selected_branch_ids) if int(branch_id) >= 0)

        if not unique_branch_ids:
            self.log_to_console("⚠️ No valid branch IDs in current selection. Falling back to standard volume mode.")
            return default_group, False

        grouped = []
        for branch_id in unique_branch_ids:
            branch_mask = selected_branch_ids == branch_id
            branch_indices = selected_indices[branch_mask]
            if len(branch_indices) < 3:
                continue
            branch_points = self.current_tree_points[branch_indices]
            grouped.append((branch_id, branch_indices, branch_points))

        if not grouped:
            self.log_to_console("⚠️ Branch groups were too small for fitting. Falling back to standard volume mode.")
            self.volume_groups_by_trunk = {}
            return default_group, False

        # Build trunk-scoped grouping for downstream per-trunk aggregation
        try:
            self.volume_groups_by_trunk = {}
            for branch_id, branch_indices, branch_points in grouped:
                trunk_id = None
                # Prefer explicit branch_meta mapping if available
                if hasattr(self, 'branch_meta') and branch_id in self.branch_meta:
                    trunk_id = int(self.branch_meta[branch_id].get('trunk_id', -1))
                else:
                    # Fallback: infer trunk by majority vote of trunk_assignment within branch indices
                    if hasattr(self, 'trunk_assignment') and self.trunk_assignment is not None:
                        trunks_in_branch = self.trunk_assignment[branch_indices]
                        valid = trunks_in_branch[trunks_in_branch >= 0]
                        if len(valid) > 0:
                            vals, counts = np.unique(valid, return_counts=True)
                            trunk_id = int(vals[np.argmax(counts)])
                if trunk_id is None or trunk_id < 0:
                    trunk_id = -1

                self.volume_groups_by_trunk.setdefault(int(trunk_id), []).append((branch_id, branch_indices, branch_points))
        except Exception:
            self.volume_groups_by_trunk = {}

        return grouped, True

    def _build_trunk_volume_summary_table(self):
        """Build trunk volume totals and formatted console rows from accumulated section data."""
        trunk_summary = {}

        # Prefer explicit trunk ids saved in sections; fall back to section grouping if needed.
        for section in self.accumulated_volume_sections:
            trunk_id = section.get('trunk_id', None)
            branch_id = section.get('branch_id', None)
            volume = float(section.get('volume', 0.0) or 0.0)
            # Use the saved point count when available (reloaded data has an
            # empty points array but retains num_points from the JSON).
            _saved_num_points = section.get('num_points')
            num_points = int(_saved_num_points) if _saved_num_points is not None else len(section.get('points', []))

            if trunk_id is None:
                # If no trunk id is present, skip from the trunk table rather than inventing one.
                continue

            trunk_key = int(trunk_id)
            rec = trunk_summary.setdefault(trunk_key, {
                'total_volume': 0.0,
                'num_branches': 0,
                'total_points': 0,
                'branch_ids': set()
            })
            rec['total_volume'] += volume
            rec['total_points'] += num_points
            if branch_id is not None and branch_id not in rec['branch_ids']:
                rec['branch_ids'].add(int(branch_id))
                rec['num_branches'] = len(rec['branch_ids'])

        # Convert to display-friendly structure and format rows
        total_volume = sum(rec['total_volume'] for rec in trunk_summary.values())
        rows = []
        header = f"{'Trunk':<8} {'Volume_m3':>12} {'#Branches':>10} {'#Points':>10}"
        rows.append(header)
        rows.append("-" * len(header))

        for trunk_id in sorted(trunk_summary.keys()):
            rec = trunk_summary[trunk_id]
            row = f"{trunk_id:<8} {rec['total_volume']:12.4f} {rec['num_branches']:10d} {rec['total_points']:10d}"
            rows.append(row)

        return trunk_summary, rows, total_volume

    def _to_local_branch_id(self, global_branch_id):
        """Convert global branch ID to local (per-trunk) branch ID using branch_meta."""
        if global_branch_id is None or not hasattr(self, 'branch_meta') or not self.branch_meta:
            return global_branch_id
        try:
            meta = self.branch_meta.get(int(global_branch_id), {})
            return meta.get('local_id', global_branch_id)
        except (ValueError, TypeError):
            return global_branch_id

    def _build_trunk_dbh_summary_table(self):
        """Build trunk-level DBH totals using section-fitted circles (same pipeline as volume sections)."""
        trunk_dbh: Dict[int, Dict[str, Any]] = {}
        target_height = getattr(self, 'dbh_reference_height', 1.3)

        if hasattr(self, 'current_tree_points') and self.current_tree_points is not None:
            tree_base_z = float(np.min(self.current_tree_points[:, 2]))
            dbh_target_z = tree_base_z + target_height
        else:
            tree_base_z = 0.0
            dbh_target_z = target_height

        debug_logs = [
            f"🔍 DBH DEBUG: target_height={target_height:.2f}m, tree_base_z={tree_base_z:.2f}m, dbh_target_z={dbh_target_z:.2f}m",
            f"🔍 DBH DEBUG: scanning {len(self.accumulated_volume_sections)} accumulated section(s)",
        ]

        # Track the closest section per trunk as a fallback when no section's
        # Z range contains dbh_target_z (e.g. no trunk points near that height).
        closest_fallback: Dict[str, Dict[str, Any]] = {}

        for section in self.accumulated_volume_sections:
            trunk_id = section.get('trunk_id', None)
            if trunk_id is None:
                continue

            circle_data = section.get('circle_data') or {}
            section_min_z = circle_data.get('min_z')
            section_max_z = circle_data.get('max_z')
            avg_radius = circle_data.get('avg_radius')
            avg_center = circle_data.get('avg_center')
            tree_id = section.get('tree_id', '?')
            branch_id = section.get('branch_id', None)
            sec_id = section.get('section_id', '?')

            avg_r_str = f"{avg_radius:.3f}" if avg_radius is not None else "None"
            z_min_str = f"{section_min_z:.2f}" if section_min_z is not None else "?"
            z_max_str = f"{section_max_z:.2f}" if section_max_z is not None else "?"

            local_branch = self._to_local_branch_id(branch_id)
            global_str = f"(global={branch_id})" if branch_id is not None and branch_id != local_branch else ""
            debug_logs.append(
                f"🔍 DBH DEBUG: Section sec={sec_id} tree={tree_id} trunk={trunk_id} branch={local_branch}{global_str} "
                f"Z=[{z_min_str}, {z_max_str}] avg_R={avg_r_str}"
            )

            # Per-section DBH target Z: prefer the tree base Z recorded when the
            # section was processed (saved in the JSON), so reloaded data
            # reproduces the original DBH reference height even when no tree is
            # currently visualized. Falls back to the saved circle_data target Z,
            # then to the global tree base Z.
            _saved_base = section.get('tree_base_z')
            if _saved_base is not None:
                try:
                    section_tree_base_z = float(_saved_base)
                except (ValueError, TypeError):
                    section_tree_base_z = tree_base_z
            else:
                _saved_target = circle_data.get('dbh_target_z')
                if _saved_target is not None:
                    try:
                        section_tree_base_z = float(_saved_target) - target_height
                    except (ValueError, TypeError):
                        section_tree_base_z = tree_base_z
                else:
                    section_tree_base_z = tree_base_z
            section_dbh_target_z = section_tree_base_z + target_height

            candidate = None

            if (avg_radius is not None and avg_center is not None and len(avg_center) >= 2
                    and section_min_z is not None and section_max_z is not None):
                try:
                    _sec_num = int(str(sec_id))
                except (ValueError, TypeError):
                    _sec_num = 0

                # Use XY of the individual circle closest to section_dbh_target_z
                # so the blue circle aligns with the red circle at that height.
                circles = circle_data.get('circles', [])
                best_xy = avg_center  # fallback to section average XY
                best_z = section_dbh_target_z  # fallback to the DBH height
                best_dist = float('inf')
                if circles and len(circles) > 0:
                    for center, _radius in circles:
                        dist = abs(center[2] - section_dbh_target_z)
                        if dist < best_dist:
                            best_dist = dist
                            best_xy = [center[0], center[1]]
                            best_z = float(center[2])

                if section_min_z <= section_dbh_target_z <= section_max_z:
                    # Trunk has points at the DBH height: draw the blue circle
                    # at the DBH height itself.
                    candidate = {
                        'tree_id': str(tree_id),
                        'dbh_cm': float(avg_radius) * 2.0 * 100.0,
                        'radius_m': float(avg_radius),
                        'center_xyz': [float(best_xy[0]), float(best_xy[1]), float(section_dbh_target_z)],
                        'score': 0.0,
                        'priority': 0,
                        'section_id': f"section_avg@{sec_id}",
                        'branch_id': self._to_local_branch_id(branch_id),
                        'dbh_target_z': float(section_dbh_target_z),
                        '_sec_num': int(_sec_num),
                    }
                    debug_logs.append(
                        f"   ✅ QUALIFIES: Z range contains dbh_target_z → candidate (priority=0, sec_num={_sec_num})"
                    )
                else:
                    # Record as a fallback candidate using the closest circle to
                    # the DBH height, so trees without trunk points near that
                    # height still get a blue DBH circle drawn. The circle is
                    # drawn at the actual closest circle's Z for realism.
                    fallback_key = f"{str(tree_id)}_{int(trunk_id)}"
                    fallback_dist = abs(section_min_z - section_dbh_target_z) if section_dbh_target_z < section_min_z else abs(section_max_z - section_dbh_target_z)
                    fallback_candidate = {
                        'tree_id': str(tree_id),
                        'dbh_cm': float(avg_radius) * 2.0 * 100.0,
                        'radius_m': float(avg_radius),
                        'center_xyz': [float(best_xy[0]), float(best_xy[1]), float(best_z)],
                        'score': float(best_dist),
                        'priority': 1,
                        'section_id': f"section_avg@{sec_id}",
                        'branch_id': self._to_local_branch_id(branch_id),
                        'dbh_target_z': float(section_dbh_target_z),
                        '_sec_num': int(_sec_num),
                        '_fallback_dist': float(fallback_dist),
                    }
                    existing_fb = closest_fallback.get(fallback_key)
                    if existing_fb is None or fallback_dist < existing_fb.get('_fallback_dist', float('inf')):
                        closest_fallback[fallback_key] = fallback_candidate
                    debug_logs.append(
                        f"   ⏳ FALLBACK candidate for {fallback_key}: Z range [{z_min_str}, {z_max_str}] does NOT contain "
                        f"dbh_target_z={section_dbh_target_z:.2f} (closest circle dist={best_dist:.3f}m)"
                    )
            elif avg_radius is None:
                debug_logs.append("   ❌ SKIPPED: no avg_radius")
            else:
                debug_logs.append("   ❌ SKIPPED: missing avg_center or Z range")

            if candidate is not None:
                tree_id_str = str(tree_id)
                composite_key = f"{tree_id_str}_{int(trunk_id)}"
                rec = trunk_dbh.get(composite_key)
                if rec is None:
                    trunk_dbh[composite_key] = candidate
                    debug_logs.append(
                        f"   🏆 SELECTED for {composite_key}: branch={branch_id}, DBH={candidate['dbh_cm']:.1f}cm, sec_num={candidate['_sec_num']}"
                    )
                else:
                    new_sort = (candidate['priority'], -candidate['_sec_num'], candidate['score'])
                    old_sort = (rec['priority'], -rec.get('_sec_num', 0), rec['score'])
                    if new_sort < old_sort:
                        trunk_dbh[composite_key] = candidate
                        debug_logs.append(
                            f"   🔄 REPLACED {composite_key}: old branch={rec.get('branch_id')} sec_num={rec.get('_sec_num')} → new branch={branch_id} sec_num={candidate['_sec_num']}"
                        )
                    else:
                        debug_logs.append(
                            f"   ⏩ IGNORED for {composite_key}: existing has better sort (old_sec_num={rec.get('_sec_num')}, new_sec_num={candidate['_sec_num']})"
                        )

        # Apply closest-circle fallback for trunks that had no section containing
        # the DBH height, so a blue DBH circle is still drawn.
        for fallback_key, fallback_candidate in closest_fallback.items():
            if fallback_key not in trunk_dbh:
                trunk_dbh[fallback_key] = fallback_candidate
                debug_logs.append(
                    f"   🎯 FALLBACK SELECTED for {fallback_key}: no section at DBH height, "
                    f"using closest circle (branch={fallback_candidate.get('branch_id')}, "
                    f"DBH={fallback_candidate['dbh_cm']:.1f}cm, dist={fallback_candidate.get('_fallback_dist', 0):.3f}m)"
                )

        # No trunk-point refit fallback here by design:
        # DBH should come from section-fitted circles used by the same branch/volume pipeline.

        trunk_dbh_values = {key: rec['dbh_cm'] for key, rec in trunk_dbh.items()}
        debug_logs.append(f"🔍 DBH DEBUG: final candidates = {list(trunk_dbh.keys())}")
        for key, rec in trunk_dbh.items():
            debug_logs.append(
                f"   {key}: branch={rec.get('branch_id')} DBH={rec['dbh_cm']:.1f}cm source={rec.get('section_id')} sec_num={rec.get('_sec_num', '?')}"
            )
        self.log_many_to_console(debug_logs)
        rows = []
        header = f"{'Tree/Trunk':<16} {'DBH_cm':>12} {'Source':>24}"
        rows.append(header)
        rows.append("-" * len(header))

        for composite_key in sorted(trunk_dbh.keys()):
            rec = trunk_dbh[composite_key]
            tree_id = rec.get('tree_id', '?')
            # Parse trunk_id from composite key for display
            parts = composite_key.rsplit('_', 1)
            trunk_display = parts[-1] if len(parts) == 2 else str(composite_key)
            label = f"Tree{tree_id}/T{trunk_display}"
            rows.append(f"{label:<16} {rec['dbh_cm']:12.1f} {str(rec['section_id']):>24}")

        return trunk_dbh_values, rows, trunk_dbh

    def _fit_single_circle_at_height(self, points, target_z, target_height=None, thickness=0.05, search_step=0.05, max_search=0.30):
        """Fallback only: fit one circle at the requested height using the section DBH logic."""
        if target_height is None:
            target_height = getattr(self, 'dbh_reference_height', 1.3)
        if points is None or len(points) < 3:
            return None

        z_values = points[:, 2]
        offsets = [0.0]
        current = search_step
        while current <= max_search + 1e-9:
            offsets.extend([current, -current])
            current += search_step

        for offset in offsets:
            slice_z = target_z + offset
            height_mask = (z_values >= slice_z - thickness / 2.0) & (z_values <= slice_z + thickness / 2.0)
            height_points = points[height_mask]

            if len(height_points) < 3:
                continue

            cluster_xy = height_points[:, :2]
            centroid = np.mean(cluster_xy, axis=0)
            distances = np.linalg.norm(cluster_xy - centroid, axis=1)
            radius = float(np.max(distances))

            if 0.03 <= radius <= 0.5:
                return {
                    'center_xy': centroid,
                    'radius_m': radius,
                    'score': abs(offset),
                    'z_used': slice_z,
                    'n_points': len(height_points),
                }

        return None

    def _add_trunk_dbh_overlays(self, trunk_dbh_details: Dict[str, Dict[str, Any]]):
        """Render trunk-level DBH circles and labels in blue for all trunks with DBH estimates.

        Circles and labels are batched into two actors. Adding one mesh + one
        label actor per trunk is much slower because each add_mesh/add_point_labels
        rebuilds VTK state and can trigger a render.
        """
        if self.plotter is None or not trunk_dbh_details:
            return

        import re as _re

        circle_specs = []
        label_points = []
        label_texts = []

        for composite_key, rec in trunk_dbh_details.items():
            center = rec.get('center_xyz')
            radius_m = rec.get('radius_m')
            dbh_cm = rec.get('dbh_cm')
            tree_id = rec.get('tree_id', '?')
            section_id = rec.get('section_id', '?')
            branch_id = rec.get('branch_id', None)

            if center is None or radius_m is None or dbh_cm is None:
                continue

            parts = composite_key.rsplit('_', 1)
            trunk_display = parts[-1] if len(parts) == 2 else str(composite_key)

            sec_display = ""
            if section_id and section_id != '?':
                m = _re.search(r'@(\d+)', str(section_id))
                if m:
                    sec_display = f"/S{m.group(1)}"
                else:
                    sec_display = f"/{section_id}"

            source_info = ""
            if branch_id is not None:
                source_info += f"/B{branch_id}"
            source_info += sec_display

            try:
                center_xyz = [float(center[0]), float(center[1]), float(center[2])]
                radius_val = float(radius_m)
                circle_specs.append((center_xyz, radius_val))
                label_points.append([center_xyz[0] + radius_val * 1.25, center_xyz[1], center_xyz[2]])
                label_texts.append(f'T{tree_id}/T{trunk_display}{source_info}: {float(dbh_cm):.1f}cm')
            except Exception as e:
                self.log_to_console(f"⚠️ Failed to prepare blue trunk DBH overlay for tree {tree_id} trunk {trunk_display}: {e}")

        if not circle_specs:
            return

        was_suppressed = bool(getattr(self.plotter, 'suppress_rendering', False))
        self.plotter.suppress_rendering = True
        try:
            merged_circles = self._build_circles_mesh(circle_specs, resolution=64)
            self.plotter.add_mesh(
                merged_circles,
                color='blue',
                opacity=0.9,
                line_width=4,
                style='wireframe',
                name='trunk_dbh_circles',
                label=f'Trunk DBH Circles ({len(circle_specs)})',
                pickable=False
            )

            if label_points:
                self.plotter.add_point_labels(
                    label_points,
                    label_texts,
                    font_size=12,
                    text_color='blue',
                    point_size=0,
                    always_visible=True,
                    name='trunk_dbh_labels',
                    pickable=False,
                    render=False
                )
        except Exception as e:
            self.log_to_console(f"⚠️ Failed to draw blue trunk DBH overlays: {e}")
        finally:
            if not was_suppressed:
                self.plotter.suppress_rendering = False
                self.plotter.render()

    def _log_section_diameter_breakdown(self):
        """Log a per-section diameter breakdown to the console (only when ≤3 trees loaded)."""
        if not self.accumulated_volume_sections:
            return
        unique_trees = set(str(s.get('tree_id', '')) for s in self.accumulated_volume_sections) - {''}
        if len(unique_trees) > 3:
            return

        self.log_to_console("=" * 60)
        self.log_to_console("📐 SECTION DIAMETER BREAKDOWN (section avg radius × 2)")
        self.log_to_console("=" * 60)

        # Group by tree → trunk → branch (deduplicate by (tree_id, section_id))
        tree_groups: dict = {}
        seen = set()
        for s in self.accumulated_volume_sections:
            tid = str(s.get('tree_id', '?'))
            sid = s.get('section_id', '?')
            dedup_key = (tid, str(sid))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            tid = str(s.get('tree_id', '?'))
            trid = s.get('trunk_id')
            bid = s.get('branch_id')
            sid = s.get('section_id', '?')
            cd = s.get('circle_data') or {}
            ar = cd.get('avg_radius')
            diam_cm = None if ar is None else float(ar) * 2.0 * 100.0
            zmin = cd.get('min_z')
            zmax = cd.get('max_z')
            tree_groups.setdefault(tid, {}).setdefault(trid, {}).setdefault(bid, []).append({
                'section': sid,
                'diam_cm': diam_cm,
                'zmin': zmin,
                'zmax': zmax,
            })

        for tree_id in sorted(tree_groups):
            self.log_to_console(f"\n🌳 Tree {tree_id}")
            for trunk_id in sorted(tree_groups[tree_id], key=lambda x: (isinstance(x, str), x if x is not None else -1)):
                branches = tree_groups[tree_id][trunk_id]
                self.log_to_console(f"  └─ Trunk {trunk_id}")
                for branch_id in sorted(branches, key=lambda x: (isinstance(x, str), x if x is not None else -1)):
                    sections = branches[branch_id]
                    branch_label = f"B{branch_id}" if branch_id is not None else "(no branch)"
                    # Compute branch average diameter across its sections
                    branch_diams = [s['diam_cm'] for s in sections if s['diam_cm'] is not None]
                    branch_avg = np.mean(branch_diams) if branch_diams else None
                    avg_str = f" → branch avg: {branch_avg:.1f} cm" if branch_avg is not None else ""
                    self.log_to_console(f"     ├─ {branch_label}{avg_str}")
                    for s in sections:
                        d_str = f"{s['diam_cm']:.1f} cm" if s['diam_cm'] is not None else "N/A"
                        z_str = f"Z=[{s['zmin']:.2f}, {s['zmax']:.2f}]" if s['zmin'] is not None and s['zmax'] is not None else ""
                        self.log_to_console(f"     │   S{s['section']}: {d_str}  {z_str}")
        self.log_to_console("=" * 60)

    def _add_section_info_labels(self):
        """Add 3D labels for each accumulated volume section showing trunk/branch/section info.

        Labels are placed at the average center XY with Z at the section's min_z.
        Only rendered when the load contains 3 or fewer trees; larger loads skip
        the white section labels to keep the scene readable and responsive.
        """
        if self.plotter is None:
            return

        unique_tree_ids = set(str(s.get('tree_id', '')) for s in self.accumulated_volume_sections) - {''}
        if len(unique_tree_ids) > 3:
            self.log_to_console(
                f"⏩ Skipping section labels: {len(unique_tree_ids)} trees loaded (>3 threshold)"
            )
            return

        seen = set()
        label_points = []
        label_texts = []
        for section in self.accumulated_volume_sections:
            dedup_key = (str(section.get('tree_id', '?')), str(section.get('section_id', '?')))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            circle_data = section.get('circle_data') or {}
            avg_center = circle_data.get('avg_center')
            if avg_center is None or len(avg_center) < 2:
                continue

            min_z = circle_data.get('min_z', 0.0)
            tree_id = section.get('tree_id', '?')
            trunk_id = section.get('trunk_id', None)
            branch_id = section.get('branch_id', None)
            sec_id = section.get('section_id', '?')

            parts = [f"T{tree_id}"]
            if trunk_id is not None:
                try:
                    parts.append(f"Tr{int(trunk_id)}")
                except (ValueError, TypeError):
                    parts.append(f"Tr{trunk_id}")
            if branch_id is not None:
                try:
                    parts.append(f"B{int(branch_id)}")
                except (ValueError, TypeError):
                    parts.append(f"B{branch_id}")
            parts.append(f"S{sec_id}")
            avg_r = circle_data.get('avg_radius')
            if avg_r is not None and avg_r > 0:
                diam_cm = float(avg_r) * 2.0 * 100.0
                label_text = f"{'/'.join(parts)}: {diam_cm:.1f}cm"
            else:
                label_text = "/".join(parts)

            label_points.append([float(avg_center[0]), float(avg_center[1]), float(min_z)])
            label_texts.append(label_text)

        if not label_points:
            return

        try:
            self.plotter.add_point_labels(
                label_points,
                label_texts,
                font_size=9,
                text_color='white',
                point_size=5,
                always_visible=True,
                name='section_info_labels',
                pickable=False,
                render=False
            )
            self.log_to_console(f"🏷️  Added {len(label_texts)} section labels")
        except Exception as e:
            self.log_to_console(f"⚠️ Failed to add section labels: {e}")

    def clear_accumulated_volume(self):
        """
        Clear all accumulated volume calculation results and reset the visualization.
        """
        try:
            # Clear accumulated data
            self.accumulated_volume_sections = []
            self.trees_with_volume_data.clear()
            
            # Reset volume calculation signature so a new tree can be calculated
            self._last_volume_calc_signature = None
            
            # Refresh tree list colors
            self._refresh_tree_list_colors()
            
            # Clear volume-related actors from plotter
            if self.plotter is not None:
                # Suppress rendering during batch removal for performance
                self.plotter.suppress_rendering = True
                
                # Remove all volume-related and DBH-related meshes and actors.
                # Snapshot the actor dict ONCE (iterating self.plotter.actors
                # repeatedly is O(n²) and very slow with thousands of actors).
                try:
                    actor_names = list(self.plotter.actors)
                except Exception:
                    actor_names = []
                actors_to_remove = [
                    name for name in actor_names
                    if ('volume' in name.lower() or
                        'dbh_' in name.lower() or
                        'trajectory' in name.lower() or
                        'circle' in name.lower() or
                        'section_info_label' in name.lower())
                ]

                for actor_name in actors_to_remove:
                    try:
                        self.plotter.remove_actor(actor_name)
                    except:
                        pass
                
                # Remove volume info text
                try:
                    self.plotter.remove_actor('volume_info_text')
                except:
                    pass
                
                # Also try to clear any text by adding empty text at the same position
                try:
                    self.plotter.add_text("", position='upper_left', font_size=10, color='#FFFFFF',
                                        name='volume_info_text')
                except:
                    pass
                
                # Re-enable rendering after batch removal
                self.plotter.suppress_rendering = False
                self.plotter.render()
                
                self.plotter.update()
            
            # Disable clear button
            self.clear_volume_button.setEnabled(False)
            self.export_trunks_button.setEnabled(False)
            
            self.log_to_console("🧹 Cleared all accumulated volume calculation results")
            
        except Exception as e:
            QMessageBox.warning(self, "Clear Error", f"Error clearing volume results: {str(e)}")
            print(f"Clear accumulated volume error: {e}")

    def save_volume_data(self):
        """Save current volume calculation data to a JSON file."""
        if not self.accumulated_volume_sections:
            # Log to GUI console instead of popping up a modal dialog
            self.log_to_console("⚠️ No volume calculation data to save.")
            return

        try:
            # Group sections by tree_id
            trees_data = {}
            for section in self.accumulated_volume_sections:
                # Skip sections with non-numeric section_ids except for global_extrapolated
                section_id = section['section_id']
                if section_id != "global_extrapolated":
                    try:
                        int(section_id)
                    except (ValueError, TypeError):
                        self.log_to_console(f"⚠️ Skipping section with non-numeric ID: {section_id}")
                        continue
                    
                tree_id = section['tree_id']
                if tree_id not in trees_data:
                    trees_data[tree_id] = {
                        'timestamp': str(pd.Timestamp.now()) if 'pd' in globals() else str(datetime.now()),
                        'sections': []
                    }

                # Record the tree base Z used for DBH (derived from the saved
                # DBH target Z minus the reference height) so reloaded data can
                # reproduce the original DBH reference height without needing
                # the tree visualized again.
                _cd = section.get('circle_data') or {}
                _dbh_target_z = _cd.get('dbh_target_z')
                try:
                    _base_z = float(_dbh_target_z) - float(getattr(self, 'dbh_reference_height', 1.3)) if _dbh_target_z is not None else None
                except (ValueError, TypeError):
                    _base_z = None
                if _base_z is None:
                    try:
                        _base_z = float(_cd.get('min_z')) if _cd.get('min_z') is not None else None
                    except (ValueError, TypeError):
                        _base_z = None

                section_data = {
                    'section_id': section['section_id'],
                    'trunk_id': section.get('trunk_id'),
                    'branch_id': section.get('branch_id'),
                    'volume': section['volume'],
                    'point_color': section['point_color'],
                    'circle_color': section['circle_color'],
                    'num_points': len(section['points']),
                    'circle_data': section['circle_data'],
                    'tree_base_z': _base_z,
                    'extrapolated': section.get('extrapolated', False),
                    'original_height_range': section.get('original_height_range'),
                    'extrapolated_height_range': section.get('extrapolated_height_range'),
                    'original_min_z': section.get('original_min_z'),
                    'extrapolated_min_z': section.get('extrapolated_min_z'),
                    'num_extrapolated_circles': section.get('num_extrapolated_circles'),
                    'ground_level_used': section.get('ground_level_used')
                }
                trees_data[tree_id]['sections'].append(section_data)

            # Calculate totals for each tree
            for tree_id, tree_data in trees_data.items():
                tree_data['total_sections'] = len(tree_data['sections'])
                tree_data['total_volume'] = sum(s['volume'] for s in tree_data['sections'])
                tree_data['total_points'] = sum(s['num_points'] for s in tree_data['sections'])

            # Prepare overall data structure
            save_data = {
                'trees': trees_data,
                'overall_totals': {
                    'total_sections': sum(tree_data['total_sections'] for tree_data in trees_data.values()),
                    'total_volume': sum(tree_data['total_volume'] for tree_data in trees_data.values()),
                    'total_points': sum(tree_data['total_points'] for tree_data in trees_data.values()),
                    'total_trees': len(trees_data)
                }
            }

            # Resolve a save folder automatically so the save button does not prompt for a folder.
            if self.volume_folder_path:
                folder = self.volume_folder_path
                self.log_to_console(f"💾 Using configured volume folder: {folder}")
            else:
                base_dir = None
                las_basename = None
                try:
                    if getattr(self, 'current_las_path', None):
                        base_dir = os.path.dirname(self.current_las_path)
                        las_basename = os.path.splitext(os.path.basename(self.current_las_path))[0]
                except Exception:
                    base_dir = None
                    las_basename = None

                if not base_dir:
                    base_dir = os.getcwd()
                    las_basename = "volume_data"

                folder = os.path.join(base_dir, 'volume', las_basename)
                self.log_to_console(f"💾 Auto-selected volume folder: {folder}")

            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                self.log_to_console(f"❌ Could not create volume folder {folder}: {e}")
                return

            self.volume_folder_path = folder
            if hasattr(self, 'volume_folder_label'):
                self.volume_folder_label.setText(f"Volume Folder: {os.path.basename(folder)}")

            if folder:
                import json
                
                saved_files = []
                for tree_id, tree_data in trees_data.items():
                    filename = os.path.join(folder, f"tree_{tree_id}.json")
                    
                    # Check if file exists and load existing data if it does
                    existing_data = None
                    if os.path.exists(filename):
                        try:
                            with open(filename, 'r') as f:
                                existing_data = json.load(f)
                            self.log_to_console(f"📂 Found existing file for tree {tree_id}, will merge data")
                        except Exception as e:
                            self.log_to_console(f"⚠️ Could not read existing file for tree {tree_id}: {e}, will create new file")
                    
                    # Merge with existing data if available
                    if existing_data and 'sections' in existing_data:
                        # Append new sections to existing tree
                        existing_data['sections'].extend(tree_data['sections'])
                        # Recalculate totals
                        existing_data['total_sections'] = len(existing_data['sections'])
                        existing_data['total_volume'] = sum(s['volume'] for s in existing_data['sections'])
                        existing_data['total_points'] = sum(s['num_points'] for s in existing_data['sections'])
                        save_data = existing_data
                        action = "merged with"
                    else:
                        save_data = tree_data
                        action = "saved to"
                    
                    with open(filename, 'w') as f:
                        json.dump(save_data, f, indent=2)
                    
                    saved_files.append(filename)
                    self.log_to_console(f"💾 Volume data for tree {tree_id} {action} {filename}")

                # Log success to GUI console instead of showing a popup
                total_sections = sum(tree_data['total_sections'] for tree_data in trees_data.values())
                total_volume = sum(tree_data['total_volume'] for tree_data in trees_data.values())
                self.log_to_console(
                    f"✅ Saved {len(saved_files)} tree files to {folder} | Total trees: {len(trees_data)} | "
                    f"Total sections: {total_sections} | Total volume: {total_volume:.4f} m³"
                )

        except Exception as e:
            # Log error to GUI console rather than showing a modal dialog
            self.log_to_console(f"❌ Error saving volume data: {e}")
            print(f"Save volume data error: {e}")

    def load_volume_data(self):
        """Load volume calculation data from tree JSON files in a folder."""
        try:
            self.progress_bar.setVisible(True)
            self._start_volume_load_profile()
            self._set_progress(2, "Resolving volume folder")
            self._profile_volume_load('start')

            # Reuse the remembered folder when available; otherwise resolve it from the current LAS path.
            folder = None
            if hasattr(self, 'volume_folder_path') and isinstance(self.volume_folder_path, str) and self.volume_folder_path and os.path.exists(self.volume_folder_path):
                folder = self.volume_folder_path
                self.log_to_console(f"📂 Using configured volume folder: {folder}")
            else:
                base_dir = None
                las_basename = None
                try:
                    if getattr(self, 'current_las_path', None):
                        base_dir = os.path.dirname(self.current_las_path)
                        las_basename = os.path.splitext(os.path.basename(self.current_las_path))[0]
                except Exception:
                    base_dir = None
                    las_basename = None

                if not base_dir:
                    base_dir = os.getcwd()
                    las_basename = "volume_data"

                folder = os.path.join(base_dir, 'volume', las_basename)
                self.log_to_console(f"📂 Auto-resolved volume folder: {folder}")

            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Volume Folder Error", f"Could not create volume folder:\n{folder}\n\n{e}")
                self._finish_volume_load_profile('folder_error')
                return

            import json
            import glob

            self.volume_folder_path = folder
            if hasattr(self, 'volume_folder_label'):
                self.volume_folder_label.setText(f"Volume Folder: {os.path.basename(folder)}")

            # Find all tree_*.json files in the folder
            all_tree_files = sorted(glob.glob(os.path.join(folder, "tree_*.json")))
            self._profile_volume_load('resolve_folder_and_list_files', extra=f'{len(all_tree_files)} files in {folder}')
            
            if not all_tree_files:
                QMessageBox.warning(self, "No Tree Files", f"No tree_*.json files found in {folder}")
                self._finish_volume_load_profile('no_files')
                return

            # If specific tree(s) are selected in the tree list, load only their data
            selected_tree_ids = self.get_selected_tree_ids()
            if selected_tree_ids:
                selected_ids_str = {str(tid) for tid in selected_tree_ids}
                tree_files = []
                for tree_file in all_tree_files:
                    filename = os.path.basename(tree_file)
                    file_tree_id = filename.replace('tree_', '').replace('.json', '')
                    if file_tree_id in selected_ids_str:
                        tree_files.append(tree_file)

                if not tree_files:
                    QMessageBox.warning(
                        self, "No Data For Selected Tree(s)",
                        f"No volume data files found for selected tree(s): {sorted(selected_tree_ids)}\n\n"
                        f"Folder searched: {folder}")
                    self._finish_volume_load_profile('no_selected_tree_files')
                    return

                self.log_to_console(
                    f"🎯 Loading volume data only for selected tree(s): {sorted(selected_tree_ids)} "
                    f"({len(tree_files)} of {len(all_tree_files)} files in folder)")
            else:
                tree_files = all_tree_files
                self.log_to_console(
                    f"📂 No trees selected - found {len(tree_files)} tree files in folder. Loading all files...")

            # Clear existing volume data if any
            if self.accumulated_volume_sections:
                reply = QMessageBox.question(self, "Clear Existing Data",
                                           "Loading new volume data will clear existing calculations. Continue?",
                                           QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    self._finish_volume_load_profile('cancelled')
                    return
                self.clear_accumulated_volume()
                self._profile_volume_load('clear_existing_volume')

            # Load data from all tree files
            self.accumulated_volume_sections = []
            loaded_trees = 0
            total_sections = 0

            self._set_progress(10, f"Reading {len(tree_files)} JSON files")

            # Read + parse all JSON files in parallel (I/O-bound). This is the
            # biggest win for folders with many tree files.
            from concurrent.futures import ThreadPoolExecutor

            def _read_tree_file(tree_file):
                with open(tree_file, 'r') as f:
                    return tree_file, json.load(f)

            parsed_files = []
            max_workers = min(32, max(4, (os.cpu_count() or 8) * 4))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for i, result in enumerate(executor.map(_read_tree_file, tree_files)):
                    parsed_files.append(result)
                    if i % max(1, len(tree_files) // 20) == 0:
                        self._set_progress(10 + int(30 * i / len(tree_files)),
                                           f"Reading JSON {i}/{len(tree_files)}")
            self._profile_volume_load('read_json_files', extra=f'{len(parsed_files)} files')

            self._set_progress(42, "Parsing sections")

            per_tree_logs = []
            for tree_file, tree_data in parsed_files:
                try:
                    # Extract tree_id from filename
                    filename = os.path.basename(tree_file)
                    tree_id = filename.replace('tree_', '').replace('.json', '')

                    # Validate data structure
                    if 'sections' not in tree_data:
                        per_tree_logs.append(f"⚠️ Skipping {filename}: no sections data")
                        continue

                    # Load sections for this tree
                    n_loaded = 0
                    for section_data in tree_data['sections']:
                        try:
                            # Handle both numeric and string section_ids
                            section_id = section_data['section_id']
                            if section_id == "global_extrapolated":
                                # Keep as string for extrapolated sections
                                pass
                            else:
                                # Convert numeric section_ids to int
                                section_id = int(section_id)
                            
                            section_info = {
                                'tree_id': tree_id,
                                'section_id': section_id,
                                'trunk_id': section_data.get('trunk_id'),
                                'branch_id': section_data.get('branch_id'),
                                'volume': section_data['volume'],
                                'point_color': section_data['point_color'],
                                'circle_color': section_data['circle_color'],
                                'points': np.array([]),  # Empty array since we don't save point data
                                'num_points': int(section_data.get('num_points', 0) or 0),
                                'tree_base_z': section_data.get('tree_base_z'),
                                'circle_data': section_data['circle_data']
                            }
                            self.accumulated_volume_sections.append(section_info)
                            total_sections += 1
                            n_loaded += 1
                        except (ValueError, TypeError) as e:
                            per_tree_logs.append(f"⚠️ Skipping section with invalid section_id '{section_data.get('section_id', 'unknown')}': {e}")
                            continue

                    loaded_trees += 1
                    per_tree_logs.append(f"✅ Loaded tree {tree_id} with {n_loaded} sections")

                except Exception as e:
                    per_tree_logs.append(f"⚠️ Error loading {tree_file}: {e}")
                    continue
            self._profile_volume_load('parse_sections', extra=f'{total_sections} sections from {loaded_trees} trees')

            # Flush all per-tree messages in a single console update
            self.log_many_to_console(per_tree_logs)

            # Deduplicate loaded sections by (tree_id, section_id) — the JSON
            # may contain duplicates from older save logic.
            self._set_progress(46, "Deduplicating sections")
            _seen = set()
            _deduped = []
            for _s in self.accumulated_volume_sections:
                _key = (str(_s.get('tree_id', '')), str(_s.get('section_id', '')))
                if _key not in _seen:
                    _seen.add(_key)
                    _deduped.append(_s)
            _dup_count = len(self.accumulated_volume_sections) - len(_deduped)
            if _dup_count > 0:
                self.log_to_console(f"🧹 Removed {_dup_count} duplicate section(s) from loaded data")
                self.accumulated_volume_sections = _deduped
                total_sections = len(self.accumulated_volume_sections)
            self._profile_volume_load('deduplicate_sections', extra=f'{total_sections} unique sections')

            # Track which trees have volume data for UI coloring.
            # Base this on ALL files present in the folder (not just the loaded
            # subset) so single-tree loads don't clear coloring for other trees.
            folder_tree_ids = set()
            for tree_file in all_tree_files:
                filename = os.path.basename(tree_file)
                folder_tree_ids.add(filename.replace('tree_', '').replace('.json', ''))
            self.trees_with_volume_data = folder_tree_ids
            
            # DEBUG: Print summary of loaded trees
            loaded_tree_ids = sorted(set(s['tree_id'] for s in self.accumulated_volume_sections))
            self.log_to_console(f"🔍 DEBUG: Loaded sections for {len(loaded_tree_ids)} tree(s): {loaded_tree_ids}")
            self.log_to_console(f"🔍 DEBUG: Folder contains volume data for {len(self.trees_with_volume_data)} trees: {sorted(self.trees_with_volume_data)}")
            
            # Refresh tree list colors to show which trees have volume data
            self._refresh_tree_list_colors()
            self._profile_volume_load('refresh_tree_list_colors')
            
            # Update UI
            self.clear_volume_button.setEnabled(True)
            self.save_volume_button.setEnabled(True)
            self.export_trunks_button.setEnabled(True)

            # Update info display
            total_sections = len(self.accumulated_volume_sections)
            total_volume = sum(s['volume'] for s in self.accumulated_volume_sections)
            total_trees = len(set(s['tree_id'] for s in self.accumulated_volume_sections))

            info_text = (f"Loaded Volume Calculation\n"
                        f"Trees: {total_trees}\n"
                        f"Sections: {total_sections}\n"
                        f"Total Volume: {total_volume:.4f} m³\n"
                        f"Source: {folder}")

            self.log_to_console(info_text)

            self.log_to_console(f"📂 Loaded volume data from {len(tree_files)} files in {folder}")
            
            # Restore visualizations for all loaded sections (batched for better performance)
            self.log_to_console(f"🎨 Restoring visualizations for {total_sections} sections...")
            if self.plotter is not None:
                self.plotter.suppress_rendering = True
            n_sections = len(self.accumulated_volume_sections)
            # Batch all section circles into a single mesh (one add_mesh call)
            # instead of one add_mesh per section, which is O(n²) and very slow
            # with hundreds of sections.
            individual_specs = []
            average_specs = []
            for i, section_info in enumerate(self.accumulated_volume_sections):
                circle_data = section_info.get('circle_data') or {}
                circles = circle_data.get('circles') or []
                if circles:
                    individual_specs.extend(circles)
                    avg_r = circle_data.get('avg_radius')
                    if avg_r and avg_r > 0:
                        average_specs.extend((center, avg_r) for center, _ in circles)
                if i % max(1, n_sections // 25) == 0:
                    self._set_progress(55 + int(40 * i / max(1, n_sections)),
                                       f"Restoring circles {i}/{n_sections}")

            if individual_specs:
                merged_individual = self._build_circles_mesh(individual_specs)
                self.plotter.add_mesh(
                    merged_individual,
                    color='cyan',
                    style='wireframe',
                    line_width=2,
                    opacity=0.9,
                    name='dbh_individual_circles_loaded',
                    label=f'Loaded Individual Circles ({len(individual_specs)} circles)',
                    pickable=False
                )
            if average_specs:
                merged_average = self._build_circles_mesh(average_specs)
                self.plotter.add_mesh(
                    merged_average,
                    color='red',
                    style='wireframe',
                    line_width=3,
                    opacity=0.9,
                    name='dbh_avg_circles_loaded',
                    label=f'Loaded Avg Circles ({len(average_specs)} circles)',
                    pickable=False
                )
            self._profile_volume_load('restore_section_circles', extra=f'{n_sections} sections')
            self._set_progress(96, "Building summaries")
            has_branch_mode = any(s.get('branch_id') is not None for s in self.accumulated_volume_sections)

            # Build trunk volume summary and log to console
            trunk_summary, trunk_summary_lines, trunk_total_volume = self._build_trunk_volume_summary_table()
            self._profile_volume_load('build_trunk_volume_summary')
            trunk_dbh_summary, trunk_dbh_lines, trunk_dbh_details = self._build_trunk_dbh_summary_table() if has_branch_mode else ({}, [], {})
            self._profile_volume_load(
                'build_trunk_dbh_summary',
                extra=f'{len(trunk_dbh_details)} trunks' if has_branch_mode else 'skipped'
            )

            if has_branch_mode and trunk_dbh_details:
                self._add_trunk_dbh_overlays(trunk_dbh_details)
                self._profile_volume_load('add_blue_dbh_overlays', extra=f'{len(trunk_dbh_details)} trunks')

            # Add section info labels showing trunk/branch/section for each loaded section
            self._add_section_info_labels()
            self._profile_volume_load('add_section_info_labels')
            if self.plotter is not None:
                self.plotter.suppress_rendering = False
                self._profile_volume_load('before_first_render')
                self.plotter.render()
                self._profile_volume_load('plotter_render')
            self._set_progress(97, "Finalizing")
            self.log_to_console(f"✅ Visualization restoration complete")
            self._log_section_diameter_breakdown()
            self._profile_volume_load('log_section_diameter_breakdown')

            if trunk_summary:
                self.log_to_console(f"📦 Total trunks used for volume: {len(trunk_summary)}")
                self.log_to_console("📋 Trunk volume summary:")
                for line in trunk_summary_lines:
                    self.log_to_console(line)
                    print(line)
                self.log_to_console(f"📊 Combined trunk volume: {trunk_total_volume:.4f} m³")
                print(f"Combined trunk volume: {trunk_total_volume:.4f} m³")
            else:
                self.log_to_console("📦 Total trunks used for volume: 0")
                self.log_to_console("📋 Trunk volume summary: none")
                print("Total trunks used for volume: 0")
                print("Trunk volume summary: none")

            if has_branch_mode:
                if trunk_dbh_summary:
                    dbh_h = getattr(self, 'dbh_reference_height', 1.3)
                    dbh_msg = f"📐 Trunk DBH summary ({dbh_h:.1f}m above base):"
                    self.log_to_console(dbh_msg)
                    for line in trunk_dbh_lines:
                        self.log_to_console(line)
                        print(line)
                else:
                    dbh_h = getattr(self, 'dbh_reference_height', 1.3)
                    dbh_msg = f"📐 Trunk DBH summary ({dbh_h:.1f}m above base): none"
                    self.log_to_console(dbh_msg)

            # Build volume info text overlay on the 3D plotter
            if self.plotter is not None:
                total_pts = sum(len(s.get('points', [])) for s in self.accumulated_volume_sections)
                mode_text = "Mode: Branch-wise" if has_branch_mode else "Mode: Standard"

                trunk_summary_overlay = ""
                if trunk_summary:
                    compact_rows = []
                    for tid in sorted(trunk_summary.keys()):
                        data = trunk_summary[tid]
                        compact_rows.append(f"T{tid}: {data['total_volume']:.4f} m³ / {data['num_branches']} branches")
                    trunk_summary_overlay = "\nTrunks Used: " + str(len(trunk_summary)) + "\n" + "\n".join(compact_rows)

                dbh_h = getattr(self, 'dbh_reference_height', 1.3)
                if has_branch_mode and trunk_dbh_summary:
                    dbh_lines = []
                    for key, dbh in sorted(trunk_dbh_summary.items()):
                        parts = str(key).rsplit('_', 1)
                        if len(parts) == 2:
                            tree_id, trunk_id = parts[0], parts[1]
                            dbh_lines.append(f"Tree{tree_id}/T{trunk_id}: {dbh:.1f} cm")
                        else:
                            dbh_lines.append(f"T{key}: {dbh:.1f} cm")
                    dbh_text = "\nDBH by trunk: " + "; ".join(dbh_lines)
                else:
                    dbh_text = "\nDBH: N/A"

                info_text = (f"Loaded Volume Calculation\n"
                            f"{mode_text}\n"
                            f"Sections: {total_sections}\n"
                            f"Total Points: {total_pts}\n"
                            f"Combined Trunk Volume: {total_volume:.4f} m³\n"
                            f"Trunks Used: {len(trunk_summary) if trunk_summary else 0}"
                            f"{trunk_summary_overlay}"
                            f"{dbh_text}\n"
                            f"Source: {os.path.basename(folder)}")

                try:
                    self.plotter.remove_actor('volume_info_text')
                except:
                    pass

                self.plotter.add_text(info_text, position='upper_left', font_size=10, color='#FFFFFF',
                                    name='volume_info_text')
                self.plotter.update()
                self._profile_volume_load('add_volume_info_text_and_update')

            self._set_progress(100, "Done")
            self.progress_bar.setVisible(False)
            self._finish_volume_load_profile('done')

            QMessageBox.information(self, "Load Successful",
                                  f"Volume data loaded from {len(tree_files)} files in {folder}\n"
                                  f"Trees: {total_trees}\n"
                                  f"Sections: {total_sections}\n"
                                  f"Total volume: {total_volume:.4f} m³")

        except Exception as e:
            self.progress_bar.setVisible(False)
            self._finish_volume_load_profile('error')
            QMessageBox.warning(self, "Load Error", f"Error loading volume data: {str(e)}")
            print(f"Load volume data error: {e}")

    def _restore_section_visualization(self, section_info):
        """Restore the visualization for a loaded section."""
        if self.plotter is None:
            return

        section_id = section_info['section_id']
        tree_id = str(section_info.get('tree_id', getattr(self, 'current_tree_id', 'unknown')))
        circle_color = section_info['circle_color']
        circle_data = section_info['circle_data']

        try:
            # Recreate circles from saved data
            if 'circles' in circle_data and circle_data['circles']:
                # Recreate trajectory points
                centers = [center for center, _ in circle_data['circles']]
                centers_array = np.array(centers)
                centers_cloud = pv.PolyData(centers_array)

                # Use tree-specific actor names to avoid collisions when restoring multiple trees
                # Removed white trajectory spheres as requested
                # self.plotter.add_mesh(centers_cloud, color='white', point_size=8,
                #                     render_points_as_spheres=True, opacity=1.0,
                #                     name=f'dbh_trajectory_tree_{tree_id}_section_{section_id}',
                #                     label=f'Tree {tree_id} - Section {section_id} Trajectory')

                # Build all individual circles in ONE vectorized pass and merge once.
                # (Previously each circle was created with pv.Circle + translate and
                # merged pairwise with `mesh + mesh`, which is O(n²) and very slow
                # when restoring many sections.)
                if len(circle_data['circles']) > 0:
                    merged_individual = self._build_circles_mesh(circle_data['circles'])

                    self.plotter.add_mesh(merged_individual, color=circle_color, style='wireframe', line_width=2, opacity=0.9,
                                        name=f'dbh_individual_circles_tree_{tree_id}_section_{section_id}',
                                        label=f'Tree {tree_id} - Section {section_id} Individual Circles ({len(circle_data["circles"])} circles)',
                                        pickable=False)

                # Recreate average circles if data available
                if 'avg_radius' in circle_data and 'avg_center' in circle_data and circle_data['avg_radius'] > 0:
                    avg_color = 'red'
                    avg_center = circle_data['avg_center']

                    # Build all average circles in one vectorized pass (same radius,
                    # centered at avg_center XY at each circle's height).
                    avg_specs = [
                        (center, circle_data['avg_radius'])
                        for center, _ in circle_data['circles']
                    ]
                    merged_average = self._build_circles_mesh(avg_specs)

                    self.plotter.add_mesh(merged_average, color=avg_color, style='wireframe', line_width=3, opacity=0.9,
                                        name=f'dbh_avg_circles_tree_{tree_id}_section_{section_id}',
                                        label=f'Tree {tree_id} - Section {section_id} Avg Circles ({len(circle_data["circles"])} circles)',
                                        pickable=False)

                    # Add a single center marker for the average center trajectory
                    centers_array = np.array([[center[0], center[1], center[2]] for center, _ in circle_data['circles']])
                    avg_centers_cloud = pv.PolyData(centers_array)
                    # Removed red trajectory spheres as requested
                    # self.plotter.add_mesh(avg_centers_cloud, color=avg_color, point_size=6,
                    #                     render_points_as_spheres=True, opacity=1.0,
                    #                     name=f'dbh_avg_trajectory_tree_{tree_id}_section_{section_id}',
                    #                     label=f'Tree {tree_id} - Section {section_id} Avg Trajectory ({len(circle_data["circles"]) } pts)')

        except Exception as e:
            print(f"Error restoring section {section_id} visualization: {e}")

    @staticmethod
    def _build_circles_mesh(circle_specs, resolution=32):
        """Build a single merged PolyData containing many circles, vectorized.

        circle_specs: iterable of (center_xyz, radius).
        Much faster than creating pv.Circle per circle and merging pairwise.
        """
        circle_specs = list(circle_specs)
        if not circle_specs:
            return pv.PolyData()

        centers = np.asarray([c for c, _ in circle_specs], dtype=float)
        radii = np.asarray([r for _, r in circle_specs], dtype=float)
        n = len(circle_specs)

        # Unit-circle template (XY plane, z=0)
        theta = np.linspace(0.0, 2.0 * np.pi, resolution, endpoint=False)
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)

        # Vertex positions: n circles × resolution points, scaled and translated
        pts = np.empty((n * resolution, 3), dtype=float)
        pts[:, 0] = np.repeat(centers[:, 0], resolution) + np.tile(cos_t, n) * np.repeat(radii, resolution)
        pts[:, 1] = np.repeat(centers[:, 1], resolution) + np.tile(sin_t, n) * np.repeat(radii, resolution)
        pts[:, 2] = np.repeat(centers[:, 2], resolution)

        # Line cells forming closed loops (VTK polyline format)
        lines = np.empty((n, resolution + 1), dtype=np.int64)
        lines[:, 0] = resolution
        idx = np.arange(n * resolution).reshape(n, resolution)
        lines[:, 1:] = np.roll(idx, shift=-1, axis=1)
        lines[:, 1] = idx[:, 0]  # close the loop back to the first point
        lines_flat = lines.reshape(-1)

        mesh = pv.PolyData()
        mesh.points = pts
        mesh.lines = lines_flat
        return mesh

    def get_visualized_tree_ids(self):
        """Get the tree IDs that are currently being visualized.
        
        Returns:
            Set of tree IDs currently visualized, or empty set if none.
        """
        if not hasattr(self, 'current_tree_id') or self.current_tree_id is None:
            return set()
        
        tree_id_str = str(self.current_tree_id)

        # Handle any label that contains tree IDs inside parentheses.
        if "(" in tree_id_str and ")" in tree_id_str:
            ids_part = tree_id_str[tree_id_str.find("(") + 1:tree_id_str.rfind(")")]
            if ids_part:
                id_strings = [id_str.strip() for id_str in ids_part.split(",") if id_str.strip()]
                if id_strings:
                    return set(id_strings)
        
        # Handle single tree case (just a number)
        try:
            # Try to convert directly to int
            tree_id = int(tree_id_str)
            return {str(tree_id)}
        except ValueError:
            pass
        
        # Fallback: return empty set
        return set()
        """Select a folder containing volume data files for automatic checking."""
        try:
            folder = QFileDialog.getExistingDirectory(
                self, "Select Volume Folder",
                self.volume_folder_path if self.volume_folder_path else ""
            )

            if folder:
                self.volume_folder_path = str(folder)  # Ensure it's a string
                self.volume_folder_label.setText(os.path.basename(folder))
                self.volume_folder_label.setStyleSheet("color: #4CAF50; font-style: normal;")
                
                # Scan for volume files and log identified trees
                self.scan_volume_folder_for_trees()
                
                self.log_to_console(f"📁 Volume folder selected: {folder}")
            else:
                self.volume_folder_path = None
                self.volume_folder_label.setText("No folder selected")
                self.volume_folder_label.setStyleSheet("color: #bbbbbb; font-style: italic;")
                self.log_to_console("📁 Volume folder cleared")

        except Exception as e:
            QMessageBox.warning(self, "Folder Selection Error", f"Error selecting volume folder: {str(e)}")

    def scan_volume_folder_for_trees(self):
        """Scan the selected volume folder for tree_*.json files and log identified trees."""
        if not hasattr(self, 'volume_folder_path') or not isinstance(self.volume_folder_path, str) or not self.volume_folder_path or not os.path.exists(self.volume_folder_path):
            return

        try:
            import glob

            # Find all tree_*.json files
            tree_files = glob.glob(os.path.join(self.volume_folder_path, "tree_*.json"))
            
            if not tree_files:
                self.log_to_console(f"📁 No volume files found in {self.volume_folder_path}")
                return

            # Extract tree IDs from filenames
            volume_tree_ids = set()
            for tree_file in tree_files:
                filename = os.path.basename(tree_file)
                tree_id = filename.replace('tree_', '').replace('.json', '')
                volume_tree_ids.add(tree_id)

            self.log_to_console(f"📊 Found volume data for {len(volume_tree_ids)} trees: {sorted(volume_tree_ids)}")

        except Exception as e:
            self.log_to_console(f"❌ Error scanning volume folder: {str(e)}")

    def check_volume_folder_for_trees(self):
        """Check the selected volume folder for tree_*.json files and update trees_with_volume_data set."""
        if not hasattr(self, 'volume_folder_path') or not isinstance(self.volume_folder_path, str) or not self.volume_folder_path or not os.path.exists(self.volume_folder_path):
            return

        try:
            import glob

            # Find all tree_*.json files
            tree_files = glob.glob(os.path.join(self.volume_folder_path, "tree_*.json"))
            
            if not tree_files:
                self.log_to_console(f"📁 No volume files found in {self.volume_folder_path}")
                self.trees_with_volume_data = set()
                return

            # Extract tree IDs from filenames
            volume_tree_ids = set()
            for tree_file in tree_files:
                filename = os.path.basename(tree_file)
                tree_id = filename.replace('tree_', '').replace('.json', '')
                volume_tree_ids.add(tree_id)

            # Update the trees_with_volume_data set
            self.trees_with_volume_data = volume_tree_ids
            
            self.log_to_console(f"📊 Updated volume data tracking for {len(volume_tree_ids)} trees: {sorted(volume_tree_ids)}")

        except Exception as e:
            self.log_to_console(f"❌ Error checking volume folder: {str(e)}")
            self.trees_with_volume_data = set()

    def on_volume_folder_checkbox_changed(self, state):
        """Handle volume folder checkbox state change."""
        if state == 2:  # Checked
            # Update tree list colors based on volume folder content
            if hasattr(self, 'volume_folder_path') and self.volume_folder_path and isinstance(self.volume_folder_path, str):
                self.check_volume_folder_for_trees()
                self._refresh_tree_list_colors()
        else:  # Unchecked
            # Clear volume data coloring
            self.trees_with_volume_data = set()
            self._refresh_tree_list_colors()

    def _refresh_tree_list_colors(self):
        """Refresh the colors of items in the tree list based on volume data availability."""
        if not hasattr(self, 'unique_itc_values') or self.unique_itc_values is None or len(self.unique_itc_values) == 0:
            return

        for i in range(self.tree_list.count()):
            item = self.tree_list.item(i)
            tree_id = str(item.text())
            if tree_id in self.trees_with_volume_data:
                item.setForeground(QColor('red'))
            else:
                item.setForeground(QColor('white'))

    def fit_to_screen(self):
        """
        Reset the camera to fit the original tree point cloud in the view.
        Excludes volume calculation circles to prevent excessive zoom-out.
        Also sets appropriate clipping planes to prevent disappearing objects.
        """
        try:
            if self.plotter is not None and self.current_tree_points is not None:
                # Calculate bounds of the original tree point cloud only
                bounds = np.array([
                    np.min(self.current_tree_points[:, 0]),  # x_min
                    np.max(self.current_tree_points[:, 0]),  # x_max
                    np.min(self.current_tree_points[:, 1]),  # y_min
                    np.max(self.current_tree_points[:, 1]),  # y_max
                    np.min(self.current_tree_points[:, 2]),  # z_min
                    np.max(self.current_tree_points[:, 2])   # z_max
                ])

                # Calculate diagonal for setting appropriate clipping planes
                diagonal = np.sqrt(
                    (bounds[1] - bounds[0])**2 +
                    (bounds[3] - bounds[2])**2 +
                    (bounds[5] - bounds[4])**2
                )

                # Set camera clipping planes to prevent disappearing objects
                # Near plane: much closer than default to handle small objects
                # Far plane: based on scene diagonal to include all relevant objects
                near_plane = max(diagonal * 0.001, 0.01)  # At least 1cm near plane
                far_plane = diagonal * 10.0  # 10x diagonal for far plane

                self.plotter.camera.clipping_range = (near_plane, far_plane)

                # Set camera to fit the tree bounds
                self.plotter.reset_camera(bounds=bounds)
                self.log_to_console("📹 Camera reset to fit original tree point cloud")
            elif self.plotter is not None:
                # Fallback to standard reset if no tree points available
                self.plotter.reset_camera()
                self.log_to_console("📹 Camera reset (no tree points available)")
            else:
                QMessageBox.information(self, "No Plotter", "No active 3D visualization to reset camera for.")
        except Exception as e:
            QMessageBox.warning(self, "Camera Reset Error", f"Error resetting camera: {str(e)}")
            print(f"Fit to screen error: {e}")

    def create_dbh_components_field(self, components, dbh_indices):
        """Create scalar field for DBH components: 0=trunk, 1+=branch IDs, 255=unassigned."""
        if self.las_data is None:
            return

        try:
            # Initialize field with zeros
            dbh_components = np.zeros(len(self.las_data), dtype=np.uint8)

            # Assign trunk points (value = 0)
            if len(components['trunk']) > 0:
                # Find indices of trunk points in the full LAS data
                trunk_points = components['trunk']
                for i, trunk_point in enumerate(trunk_points):
                    # Find the closest point in dbh_indices
                    diffs = np.column_stack([
                        np.array(self.las_data.x)[dbh_indices] - trunk_point[0],
                        np.array(self.las_data.y)[dbh_indices] - trunk_point[1],
                        np.array(self.las_data.z)[dbh_indices] - trunk_point[2]
                    ])
                    distances = np.linalg.norm(diffs, axis=1)
                    closest_idx = np.argmin(distances)
                    if distances[closest_idx] < 0.01:  # Very close match
                        dbh_components[dbh_indices[closest_idx]] = 0

            # Assign branch points (values 1, 2, 3, ...)
            for branch_id, branch_points in enumerate(components['branches'], 1):
                for branch_point in branch_points:
                    # Find the closest point in dbh_indices
                    diffs = np.column_stack([
                        np.array(self.las_data.x)[dbh_indices] - branch_point[0],
                        np.array(self.las_data.y)[dbh_indices] - branch_point[1],
                        np.array(self.las_data.z)[dbh_indices] - branch_point[2]
                    ])
                    distances = np.linalg.norm(diffs, axis=1)
                    closest_idx = np.argmin(distances)
                    if distances[closest_idx] < 0.01:  # Very close match
                        dbh_components[dbh_indices[closest_idx]] = branch_id

            # Assign unassigned points (value = 255)
            if len(components['unassigned']) > 0:
                unassigned_points = components['unassigned']
                for unassigned_point in unassigned_points:
                    # Find the closest point in dbh_indices
                    diffs = np.column_stack([
                        np.array(self.las_data.x)[dbh_indices] - unassigned_point[0],
                        np.array(self.las_data.y)[dbh_indices] - unassigned_point[1],
                        np.array(self.las_data.z)[dbh_indices] - unassigned_point[2]
                    ])
                    distances = np.linalg.norm(diffs, axis=1)
                    closest_idx = np.argmin(distances)
                    if distances[closest_idx] < 0.01:  # Very close match
                        dbh_components[dbh_indices[closest_idx]] = 255

            # Add or update the scalar field
            field_name = "dbh_components"
            if field_name in self.las_data.point_format.dimension_names:
                self.las_data[field_name] = dbh_components
                self.log_to_console("✅ Updated existing 'dbh_components' scalar field")
            else:
                try:
                    self.las_data.add_extra_dim(laspy.ExtraBytesParams(name=field_name, type=np.uint8))
                    self.las_data[field_name] = dbh_components
                    self.log_to_console("✅ Added new 'dbh_components' scalar field to LAS data")
                except Exception as e:
                    self.log_to_console(f"⚠️ Could not create 'dbh_components' field: {str(e)}")
                    return

            # Refresh color combo box to include the new field
            self.refresh_color_combo_box()

        except Exception as e:
            self.log_to_console(f"❌ Error creating DBH components field: {str(e)}")
            print(f"Error in create_dbh_components_field: {str(e)}")

    def _visualize_dbh_components(self, components, branching_height, dbh_points):
        """Visualize the extracted DBH components in the plotter with circle fitting."""
        if self.plotter is None:
            return

        try:
            self.plotter.clear()
            self._restore_gdb_layers()

            # Create point clouds for each component
            if len(components['trunk']) > 0:
                trunk_cloud = pv.PolyData(components['trunk'])
                self.plotter.add_points(trunk_cloud, color='brown', point_size=4, opacity=0.9,
                                      name='dbh_trunk', label='DBH Trunk')

            # Visualize branches with different colors
            branch_colors = ['green', 'blue', 'orange', 'purple', 'cyan', 'magenta', 'yellow']
            for i, branch_points in enumerate(components['branches']):
                if len(branch_points) > 0:
                    branch_cloud = pv.PolyData(branch_points)
                    color = branch_colors[i % len(branch_colors)]
                    self.plotter.add_points(branch_cloud, color=color, point_size=4, opacity=0.8,
                                          name=f'dbh_branch_{i+1}', label=f'DBH Branch {i+1}')

            # Visualize unassigned points
            if len(components['unassigned']) > 0:
                unassigned_cloud = pv.PolyData(components['unassigned'])
                self.plotter.add_points(unassigned_cloud, color='gray', point_size=3, opacity=0.6,
                                      name='dbh_unassigned', label='DBH Unassigned')

            # Add circle fitting for DBH points
            self._add_dbh_circle_fitting(dbh_points)

            # Add reference plane at branching height
            min_z = np.min(dbh_points[:, 2])
            branching_z = min_z + branching_height
            reference_plane = pv.Plane(center=(0, 0, branching_z), direction=(0, 0, 1),
                                     i_size=50, j_size=50)

            self.plotter.add_mesh(reference_plane, color='red', opacity=0.3,
                                name='branching_plane', label=f'Branching Height: {branching_height:.2f}m')

            # Add information text
            info_text = (f"DBH Components Analysis with Circle Fitting\n"
                        f"Branching Height: {branching_height:.2f}m\n"
                        f"Total DBH Points: {len(dbh_points)}\n"
                        f"Components: {1 + len(components['branches']) + (1 if len(components['unassigned']) > 0 else 0)}")

            self.plotter.add_text(info_text, position='upper_left', font_size=10, color='#FFFFFF')

            self.plotter.reset_camera()

        except Exception as e:
            self.log_to_console(f"❌ Error visualizing DBH components: {str(e)}")
            print(f"Error in _visualize_dbh_components: {e}")

    def _add_dbh_circle_fitting(self, dbh_points):
        """Add circle fitting visualization for DBH points at multiple height levels."""
        if len(dbh_points) == 0:
            return

        # Get height range for DBH points
        min_z = np.min(dbh_points[:, 2])
        max_z = np.max(dbh_points[:, 2])
        height_range = max_z - min_z

        self.log_to_console(f"📏 DBH Circle Fitting: Z range {min_z:.2f} to {max_z:.2f}m (height: {height_range:.2f}m)")

        # Calculate circle centers (trajectory points) at regular height intervals
        circle_centers = []
        circle_radii = []
        step = 0.1  # 10cm height steps
        current_z = min_z

        while current_z <= max_z:
            # Extract points within thickness around current height
            thickness = 0.05  # 5cm thickness for more precise fitting
            height_mask = (dbh_points[:, 2] >= current_z - thickness/2) & \
                         (dbh_points[:, 2] <= current_z + thickness/2)
            height_points = dbh_points[height_mask]

            if len(height_points) >= 3:  # Need at least 3 points for circle fitting
                # Calculate bounding circle using centroid method
                cluster_xy = height_points[:, :2]  # Only X,Y coordinates
                centroid = np.mean(cluster_xy, axis=0)
                distances = np.linalg.norm(cluster_xy - centroid, axis=1)
                radius = np.max(distances)

                # Only include circles within reasonable radius bounds (3cm to 50cm for DBH)
                if 0.03 <= radius <= 0.5:
                    circle_centers.append([centroid[0], centroid[1], current_z])
                    circle_radii.append(radius)
                    self.log_to_console(f"✅ DBH Circle: Z={current_z:.2f}m, center=({centroid[0]:.3f}, {centroid[1]:.3f}), radius={radius:.3f}m")

            current_z += step

        # Display the center trajectory points
        if len(circle_centers) > 0:
            centers_array = np.array(circle_centers)
            centers_cloud = pv.PolyData(centers_array)

            # Use white spheres for trajectory points
            self.plotter.add_mesh(centers_cloud, color='white', point_size=8,
                                render_points_as_spheres=True, opacity=1.0,
                                name='dbh_trajectory', label=f'DBH Trajectory ({len(circle_centers)} pts)',
                                pickable=False)

            # Compute average center and radius for all circles
            avg_x = np.mean([c[0] for c in circle_centers])
            avg_y = np.mean([c[1] for c in circle_centers])
            final_center = [avg_x, avg_y, 0]  # Z not used for center
            final_radius = np.mean(circle_radii)

            # Display the circles at each height level as filled disks
            for i, (center, radius) in enumerate(zip(circle_centers, circle_radii)):
                # Create a circle at this height
                circle = pv.Circle(radius=radius, resolution=32)
                # Translate circle to the center position
                circle.translate([center[0], center[1], center[2]], inplace=True)

                # Use filled circles (disks) for individual circles
                self.plotter.add_mesh(circle, color='cyan', opacity=0.3,
                                    name=f'dbh_circle_{i}', label=f'DBH Circle Z={center[2]:.1f}m',
                                    pickable=False)

            # Add average circle at EVERY height level where individual circles exist
            self._add_average_dbh_circles_at_all_levels(circle_centers, final_center, final_radius)

            self.log_to_console(f"📊 Added {len(circle_centers)} DBH circles for trajectory visualization")

        else:
            self.log_to_console("⚠️ No valid circles found for DBH trajectory")

    def _add_average_dbh_circles_at_all_levels(self, circle_centers, avg_center, avg_radius):
        """Add average circle at every height level where individual circles were calculated."""
        if len(circle_centers) == 0:
            return

        try:
            # Add average circle at EACH height level
            for i, center in enumerate(circle_centers):
                height_z = center[2]  # Z coordinate of this height level

                # Create average circle at this height
                avg_circle = pv.Circle(radius=avg_radius, resolution=64)
                avg_circle.translate([avg_center[0], avg_center[1], height_z], inplace=True)

                # Make it wireframe (boundary only)
                avg_circle_wireframe = pv.PolyData(avg_circle.points)
                avg_circle_wireframe.lines = avg_circle.lines

                # Use red color for average circles, slightly thicker
                self.plotter.add_mesh(avg_circle_wireframe, color='red', line_width=3, opacity=0.9,
                                    name=f'dbh_avg_circle_{i}', label=f'DBH Avg Circle Z={height_z:.1f}m',
                                    pickable=False)

            # Add a single center marker for the average center trajectory
            centers_array = np.array([[avg_center[0], avg_center[1], center[2]] for center in circle_centers])
            avg_centers_cloud = pv.PolyData(centers_array)
            self.plotter.add_mesh(avg_centers_cloud, color='red', point_size=6,
                                render_points_as_spheres=True, opacity=1.0,
                                name='dbh_avg_trajectory', label=f'DBH Avg Trajectory ({len(circle_centers)} pts)',
                                pickable=False)

            self.log_to_console(f"🎯 Added DBH Average Circles at {len(circle_centers)} height levels (R={avg_radius:.3f}m)")

        except Exception as e:
            self.log_to_console(f"❌ Error adding average DBH circles at all levels: {str(e)}")
            print(f"Error in _add_average_dbh_circles_at_all_levels: {e}")

    def _extract_components(self, points):
        """
        Extract tree components using connectivity-based branch extension.

        Args:
            points: numpy array of shape (N, 3) with XYZ coordinates

        Returns:
            List of component arrays, each containing points belonging to one component
        """
        # Sort points by height (Z coordinate) in descending order
        sorted_indices = np.argsort(points[:, 2])[::-1]
        sorted_points = points[sorted_indices]

        # Initialize components list
        components = []

        # Start with the highest point as the first component
        current_component = [sorted_points[0]]
        remaining_points = sorted_points[1:]

        # Parameters for connectivity
        max_distance = 0.15  # Maximum distance for connectivity (15cm)
        min_points_per_component = 10  # Minimum points for a valid component

        while len(remaining_points) > 0:
            # Find points within max_distance of any point in current component
            component_points = np.array(current_component)
            distances = np.min(cdist(remaining_points, component_points), axis=1)
            connected_mask = distances <= max_distance

            if np.any(connected_mask):
                # Add connected points to current component
                new_points = remaining_points[connected_mask]
                current_component.extend(new_points)
                remaining_points = remaining_points[~connected_mask]
            else:
                # No more connected points, save current component if large enough
                if len(current_component) >= min_points_per_component:
                    components.append(np.array(current_component))
                # Start new component with next highest remaining point
                if len(remaining_points) > 0:
                    current_component = [remaining_points[0]]
                    remaining_points = remaining_points[1:]
                else:
                    break

        # Add the last component if large enough
        if len(current_component) >= min_points_per_component:
            components.append(np.array(current_component))

        return components

    def _visualize_components(self, original_points, components):
        """
        Visualize the extracted components in the plotter.

        Args:
            original_points: Original point cloud
            components: List of component point arrays
        """
        # Clear existing plot
        self.plotter.clear()
        self._restore_gdb_layers()

        # Color map for components
        colors = plt.cm.tab10(np.linspace(0, 1, len(components)))

        # Add each component as a separate point cloud
        for i, component in enumerate(components):
            # Create point cloud for this component
            component_cloud = pv.PolyData(component)
            self.plotter.add_points(
                component_cloud,
                color=colors[i][:3],  # RGB values
                point_size=3,
                label=f'Component {i+1} ({len(component)} points)'
            )

        # Add info text about components
        total_points = sum(len(comp) for comp in components)
        self.plotter.add_text(f"Tree Components: {len(components)} components, {total_points} total points",
                             position='upper_left', font_size=12, color='#FFFFFF')

        # Reset camera to show all components
        self.plotter.reset_camera()


    def _visualize_advanced_components(self, components, branching_height, all_points):
        """
        Visualize the advanced extracted components (trunk, branches, unassigned).

        Args:
            components: Dictionary with trunk, branches, and unassigned points
            branching_height: Height where branching occurs
            all_points: All original stem points
        """
        # Clear existing plot
        self.plotter.clear()
        self._restore_gdb_layers()

        trunk_points = components['trunk']
        branches = components['branches']
        unassigned_points = components['unassigned']

        # Visualize trunk in brown
        if len(trunk_points) > 0:
            trunk_cloud = pv.PolyData(trunk_points)
            self.plotter.add_points(trunk_cloud, color='brown', point_size=4, opacity=0.9,
                                  label=f'Trunk ({len(trunk_points)} pts)')

        # Visualize branches with different colors
        branch_colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow']
        for i, branch_points in enumerate(branches):
            if len(branch_points) > 0:
                color = branch_colors[i % len(branch_colors)]
                branch_cloud = pv.PolyData(branch_points)
                self.plotter.add_points(branch_cloud, color=color, point_size=4, opacity=0.8,
                                      label=f'Branch {i+1} ({len(branch_points)} pts)')

        # Visualize unassigned points in gray
        if len(unassigned_points) > 0:
            unassigned_cloud = pv.PolyData(unassigned_points)
            self.plotter.add_points(unassigned_cloud, color='gray', point_size=3, opacity=0.6,
                                  label=f'Unassigned ({len(unassigned_points)} pts)')

        # Add reference plane at branching height
        if len(trunk_points) > 0:
            min_z = np.min(trunk_points[:, 2])
            branching_z = min_z + branching_height

            plane_bounds = [
                np.min(all_points[:, 0]) - 1, np.max(all_points[:, 0]) + 1,
                np.min(all_points[:, 1]) - 1, np.max(all_points[:, 1]) + 1,
                branching_z, branching_z
            ]

            reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                             float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                             float(branching_z)],
                                     i_size=plane_bounds[1]-plane_bounds[0],
                                     j_size=plane_bounds[3]-plane_bounds[2])
            self.plotter.add_mesh(reference_plane, color='red', opacity=0.3,
                                label=f'Branching Height: {branching_height:.1f}m')

        # Add info text about advanced components
        total_points = len(trunk_points) + sum(len(b) for b in branches) + len(unassigned_points)
        info_text = f"Advanced Tree Component Analysis\n"
        info_text += f"Total stem points: {total_points}\n"
        info_text += f"Trunk: {len(trunk_points)} points\n"
        for i, branch in enumerate(branches):
            info_text += f"Branch {i+1}: {len(branch)} points\n"
        if len(unassigned_points) > 0:
            info_text += f"Unassigned: {len(unassigned_points)} points\n"
        info_text += f"Branching height: {branching_height:.2f}m"

        self.plotter.add_text(info_text, position='upper_left', font_size=10, color='#FFFFFF')

        # Reset camera to show all components
        self.plotter.reset_camera()





def extract_components(points: np.ndarray, branching_height: float, assign_radius: float = 0.5,
                      vertical_window: float = 0.2, min_vertical_overlap: float = 0.1, use_nearest_neighbor: bool = False):
    """
    Extract tree components: trunk (below branching height) and branches (above, assigned to nearest cluster).

    Args:
        points: All stem points
        branching_height: Height where branching occurs (from base)
        assign_radius: Maximum horizontal distance for assigning points to branch centroids
        vertical_window: Vertical distance window for connectivity checks
        min_vertical_overlap: Minimum vertical overlap required for connectivity
    """
    min_z = np.min(points[:, 2])
    branching_z = min_z + branching_height

    # Separate points by height
    trunk_mask = points[:, 2] <= branching_z
    trunk_points = points[trunk_mask]
    branch_candidate_points = points[~trunk_mask]

    print(f"Branching height: {branching_height:.2f}m (Z = {branching_z:.2f}m)")
    print(f"Total points: {len(points)}")
    print(f"Trunk points: {len(trunk_points)}")
    print(f"Branch candidate points: {len(branch_candidate_points)}")

    # If no branch points, return just trunk
    if len(branch_candidate_points) == 0:
        return {
            'trunk': trunk_points,
            'branches': [],
            'unassigned': np.empty((0, 3))
        }

    # Use middle slice clustering for branch identification (same as visualization)
    # Calculate middle height of the crown
    if len(branch_candidate_points) > 0:
        crown_min_z = np.min(branch_candidate_points[:, 2])
        crown_max_z = np.max(branch_candidate_points[:, 2])
        middle_z = (crown_min_z + crown_max_z) / 2

        # Extract points near middle slice for clustering (within 0.1m tolerance)
        slice_tolerance = 0.1
        slice_mask = (branch_candidate_points[:, 2] >= middle_z - slice_tolerance) & (branch_candidate_points[:, 2] <= middle_z + slice_tolerance)
        slice_points = branch_candidate_points[slice_mask]

        centroids = []
        if len(slice_points) >= 3:
            # Apply DBSCAN clustering to horizontal slice (same as visualization)
            clustering = DBSCAN(eps=0.2, min_samples=3).fit(slice_points[:, :2])
            labels = clustering.labels_
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

            print(f"Found {n_clusters} branch clusters at middle slice (Z = {middle_z:.2f}m)")

            # Get centroids for each cluster
            for cluster_id in range(n_clusters):
                cluster_mask = labels == cluster_id
                cluster_points = slice_points[cluster_mask]
                if len(cluster_points) > 0:
                    centroid = np.mean(cluster_points, axis=0)
                    centroids.append(centroid)
        else:
            print("Warning: Insufficient points at middle slice for clustering")
            centroids = []

    if len(centroids) == 0:
        return {
            'trunk': trunk_points,
            'branches': [branch_candidate_points],
            'unassigned': np.empty((0, 3))
        }

    # Use connectivity-based approach (same as visualization)
    # Build connectivity graph for all branch candidate points
    horizontal_radius = 0.2  # 20cm horizontal connectivity radius
    vertical_radius = 0.5    # 50cm vertical connectivity radius

    print(f"Building connectivity graph with {len(branch_candidate_points)} branch candidate points...")
    print(f"Connectivity: horizontal={horizontal_radius}m, vertical={vertical_radius}m")
    n_points = len(branch_candidate_points)

    # Create adjacency matrix for 3D connectivity (horizontal + vertical)
    # Points are connected if within BOTH horizontal AND vertical radius
    rows = []
    cols = []

    for i in range(n_points):
        for j in range(i+1, n_points):
            # Check horizontal distance
            dist_xy = np.sqrt((branch_candidate_points[i, 0] - branch_candidate_points[j, 0])**2 +
                            (branch_candidate_points[i, 1] - branch_candidate_points[j, 1])**2)
            # Check vertical distance
            dist_z = abs(branch_candidate_points[i, 2] - branch_candidate_points[j, 2])
            
            if dist_xy <= horizontal_radius and dist_z <= vertical_radius:
                rows.extend([i, j])
                cols.extend([j, i])

    branch_arrays = []
    unassigned_points = []

    if len(rows) > 0:
        # Create sparse adjacency matrix
        adjacency = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_points, n_points))

        # Find connected components
        n_components, connectivity_labels = connected_components(csgraph=adjacency, directed=False, return_labels=True)

        print(f"Found {n_components} connected components in crown (3D connectivity)")

        # For each cluster from middle slice, find connected components containing cluster points
        for cluster_id in range(len(centroids)):
            cluster_mask = labels == cluster_id
            cluster_points = slice_points[cluster_mask]
            
            if len(cluster_points) > 0:
                # Find indices of cluster points in the full branch_candidate_points array
                cluster_indices = []
                for cluster_point in cluster_points:
                    # Find this point in the full branch candidate array
                    diffs = branch_candidate_points - cluster_point
                    distances = np.linalg.norm(diffs, axis=1)
                    idx = np.argmin(distances)
                    if distances[idx] < 0.01:  # Very close match
                        cluster_indices.append(idx)
                
                if len(cluster_indices) > 0:
                    # Get the component labels for these cluster points
                    cluster_component_labels = set(connectivity_labels[idx] for idx in cluster_indices)
                    
                    # Collect all points in these connected components
                    branch_points = []
                    for comp_label in cluster_component_labels:
                        component_mask = connectivity_labels == comp_label
                        component_points = branch_candidate_points[component_mask]
                        branch_points.extend(component_points)
                    
                    if len(branch_points) > 0:
                        branch_arrays.append(np.array(branch_points))

        # Find unassigned points (not in any branch's connected components)
        assigned_indices = set()
        for branch in branch_arrays:
            for branch_point in branch:
                # Find index of this point in branch_candidate_points
                diffs = branch_candidate_points - branch_point
                distances = np.linalg.norm(diffs, axis=1)
                idx = np.argmin(distances)
                if distances[idx] < 0.01:
                    assigned_indices.add(idx)
        
        unassigned_indices = [i for i in range(len(branch_candidate_points)) if i not in assigned_indices]
        if len(unassigned_indices) > 0:
            unassigned_points = branch_candidate_points[unassigned_indices]
        else:
            unassigned_points = np.empty((0, 3))
    else:
        # No connectivity found, assign all to first branch
        branch_arrays = [branch_candidate_points]
        unassigned_points = np.empty((0, 3))

    unassigned_array = np.array(unassigned_points) if len(unassigned_points) > 0 else np.empty((0, 3))

    print(f"Assigned to {len(branch_arrays)} branches")
    print(f"Unassigned points: {len(unassigned_array)}")
    print(f"Connectivity parameters: horizontal={horizontal_radius}m, vertical={vertical_radius}m")

    return {
        'trunk': trunk_points,
        'branches': branch_arrays,
        'unassigned': unassigned_array,
        'centroids': centroids
    }


def visualize_components(components: dict, plotter, branching_height: float, centroids: list, all_points: np.ndarray, viz_mode: str = 'components'):
    """
    Visualize tree components based on the specified mode.

    Args:
        components: Dictionary with trunk, branches, and unassigned points
        plotter: PyVista plotter instance
        branching_height: Height where branching occurs
        centroids: List of branch centroids
        all_points: All original points
        viz_mode: Visualization mode ('components', 'sequence', etc.)
    """
    if viz_mode == 'components':
        # Visualize each component with different colors
        trunk_points = components['trunk']
        branches = components['branches']
        unassigned_points = components['unassigned']

        # Clear existing plot
        plotter.clear()

        # Visualize trunk
        if len(trunk_points) > 0:
            trunk_cloud = pv.PolyData(trunk_points)
            plotter.add_mesh(trunk_cloud, color='brown', point_size=4, opacity=0.9,
                           label=f'Trunk ({len(trunk_points)} pts)', render_points_as_spheres=False)

        # Visualize branches with different colors
        branch_colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow']
        for i, branch_points in enumerate(branches):
            if len(branch_points) > 0:
                color = branch_colors[i % len(branch_colors)]
                branch_cloud = pv.PolyData(branch_points)
                plotter.add_mesh(branch_cloud, color=color, point_size=4, opacity=0.8,
                               label=f'Branch {i+1} ({len(branch_points)} pts)', render_points_as_spheres=False)

        # Visualize unassigned points
        if len(unassigned_points) > 0:
            unassigned_cloud = pv.PolyData(unassigned_points)
            plotter.add_mesh(unassigned_cloud, color='gray', point_size=3, opacity=0.6,
                           label=f'Unassigned ({len(unassigned_points)} pts)', render_points_as_spheres=False)

        # Add reference plane at branching height
        if len(trunk_points) > 0:
            min_z = np.min(trunk_points[:, 2])
            branching_z = min_z + branching_height

            plane_bounds = [
                np.min(all_points[:, 0]) - 1, np.max(all_points[:, 0]) + 1,
                np.min(all_points[:, 1]) - 1, np.max(all_points[:, 1]) + 1,
                branching_z, branching_z
            ]

            reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                             float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                             float(branching_z)],
                                     i_size=plane_bounds[1]-plane_bounds[0],
                                     j_size=plane_bounds[3]-plane_bounds[2])
            plotter.add_mesh(reference_plane, color='red', opacity=0.3,
                           label=f'Branching Height: {branching_height:.1f}m')

        # Add bounding box
        if len(all_points) > 0:
            bounds = [
                np.min(all_points[:, 0]), np.max(all_points[:, 0]),
                np.min(all_points[:, 1]), np.max(all_points[:, 1]),
                np.min(all_points[:, 2]), np.max(all_points[:, 2])
            ]
            bounding_box = pv.Cube(bounds=bounds)
            plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                           label='Bounding Box')

        # Calculate dimensions
        width = bounds[1] - bounds[0]
        length = bounds[3] - bounds[2]
        height = bounds[5] - bounds[4]

        info_text = f"Tree Component Analysis\n"
        info_text += f"Total stem points: {len(all_points)}\n"
        info_text += f"Trunk points: {len(trunk_points)}\n"
        for i, branch in enumerate(branches):
            info_text += f"Branch {i+1}: {len(branch)} points\n"
        info_text += f"Unassigned: {len(unassigned_points)} points\n"
        info_text += f"Dimensions: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
        info_text += f"Branching height: {branching_height:.2f}m"

        plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
        plotter.camera.azimuth = 45
        plotter.camera.elevation = 30
        plotter.update()

    else:
        print(f"Visualization mode '{viz_mode}' not implemented. Use 'components' for component visualization.")


def setup_exception_handler():
    """Set up global exception handler to capture unhandled errors including PyQt exceptions."""
    import traceback
    import logging
    
    # Configure logging to file for debugging
    log_dir = os.path.join(os.path.dirname(__file__), 'error_logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Global exception handler for uncaught exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.error(f"Uncaught exception:\n{error_msg}")
        print(f"\n{'='*60}\n❌ UNCAUGHT ERROR:\n{error_msg}\n{'='*60}\n", file=sys.stderr)
    
    sys.excepthook = handle_exception


class ErrorCapturingQApplication(QApplication):
    """Custom QApplication that captures and logs exceptions from the event loop."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exception_logged = False
    
    def notify(self, receiver, event):
        """Override notify to catch exceptions in PyQt slots and event handlers."""
        try:
            return super().notify(receiver, event)
        except Exception as e:
            error_msg = f"""
{'='*60}
❌ PyQt EVENT LOOP ERROR:
Exception in {receiver.__class__.__name__}.{event.__class__.__name__}
{'='*60}
{traceback.format_exc()}
{'='*60}
"""
            print(error_msg, file=sys.stderr)
            logging.error(f"PyQt event loop exception: {error_msg}")
            
            # Also show a GUI message box if possible
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Error", f"An error occurred:\n\n{str(e)}\n\nCheck error logs for details.")
            except:
                pass
            
            return False


def main():
    """Main application entry point."""
    import time
    
    # Set up error handling before creating GUI
    setup_exception_handler()
    
    startup_start = time.perf_counter()
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - Starting application...")
    
    # Use custom QApplication that captures PyQt exceptions
    app = ErrorCapturingQApplication(sys.argv)
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - QApplication created ({time.perf_counter() - startup_start:.2f}s)")

    # Set application properties
    app.setApplicationName("Tree Visualizer")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("TreeAIBox")
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - App properties set ({time.perf_counter() - startup_start:.2f}s)")

    # Create and show main window maximized
    window_start = time.perf_counter()
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - Creating TreeVisualizerGUI...")
    window = TreeVisualizerGUI()
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - TreeVisualizerGUI created ({time.perf_counter() - window_start:.2f}s)")
    
    window.showMaximized()
    print(f"[STARTUP] {time.strftime('%H:%M:%S')} - Window shown ({time.perf_counter() - startup_start:.2f}s total)")

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
