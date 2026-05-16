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
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit, QLabel, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QFrame, QComboBox, QCheckBox,
    QGroupBox, QScrollArea, QTextEdit, QDialog, QButtonGroup, QRadioButton, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from sklearn.cluster import DBSCAN
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from datetime import datetime
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import cdist
from scipy.spatial import KDTree
from concurrent.futures import ProcessPoolExecutor
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


class TreeVisualizerGUI(QMainWindow):
    """Main window for tree visualization GUI."""

    def __init__(self):
        import time
        init_start = time.perf_counter()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - TreeVisualizerGUI.__init__ starting...")
        
        super().__init__()
        print(f"[INIT] {time.strftime('%H:%M:%S')} - super().__init__ done ({time.perf_counter() - init_start:.3f}s)")
        
        self.las_data = None
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
        # Polygon selection variables
        self.polygon_selection_mode = False
        self.polygon_points = []
        self.selected_polygon = None
        self.selected_point_indices = None
        
        # Volume calculation accumulation variables
        self.accumulated_volume_sections = []  # List of (points, circles_data) tuples
        self.trees_with_volume_data = set()  # Track tree IDs that have volume calculation data
        self.volume_folder_path = None  # Path to folder containing volume data files
        self.itc_changes = []  # Track all ITC assignments in session
        self.last_analyzed_points = None  # Store points from last AI analysis for noise conversion
        self.tree_centroids_cache = {}  # Cache for tree centroids to speed up neighbor calculations
        self.centroids_kdtree = None  # KDTree for fast spatial queries
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
        self.plotter.add_text("Click on points to see ITC values", position='upper_right', 
                            font_size=10, color='#FFFFFF')
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
        sidebar.setMaximumWidth(320)
        sidebar.setMinimumWidth(280)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(sidebar)
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

        self.load_button = ModernButton("Load LAS File")
        self.load_button.clicked.connect(self.load_las_file)
        file_layout.addWidget(self.load_button)

        layout.addWidget(file_group)

        # Volume folder management section
        volume_group = QGroupBox("Volume Folder Management")
        volume_layout = QVBoxLayout(volume_group)
        volume_layout.setSpacing(8)

        # Volume folder selection
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Volume Folder:")
        folder_label.setFixedWidth(100)
        self.volume_folder_label = QLabel("No folder selected")
        self.volume_folder_label.setStyleSheet("color: #bbbbbb; font-style: italic;")
        self.volume_folder_label.setWordWrap(True)
        self.select_volume_folder_button = ModernButton("Select Folder")
        self.select_volume_folder_button.clicked.connect(self.select_volume_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.volume_folder_label, 1)
        folder_layout.addWidget(self.select_volume_folder_button)
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

        # Control buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)
        
        self.visualize_button = ModernButton("Visualize Tree")
        self.visualize_button.clicked.connect(self.visualize_tree)
        self.visualize_button.setEnabled(False)
        button_layout.addWidget(self.visualize_button)

        self.trunk_button = ModernButton("Trunk Visualisation")
        self.trunk_button.clicked.connect(self.visualize_trunk)
        self.trunk_button.setEnabled(False)
        button_layout.addWidget(self.trunk_button)

        # Add polygon selection controls right below trunk button
        polygon_layout = QVBoxLayout()
        self.draw_polygon_button = ModernButton("Draw Selection")
        self.draw_polygon_button.clicked.connect(self.on_draw_polygon_button_clicked)
        self.draw_polygon_button.setEnabled(False)
        self.draw_polygon_button.setToolTip("Draw a polygon to select points and assign new ITC values")
        
        # Initialize flag for polygon selection state
        self.polygon_selection_active = False
        
        self.select_all_points_button = ModernButton("Select All Points")
        self.select_all_points_button.clicked.connect(self.select_all_points)
        self.select_all_points_button.setEnabled(False)
        self.select_all_points_button.setToolTip("Select all points in the current visualization without drawing")
        
        self.assign_itc_button = ModernButton("Assign ITC")
        self.assign_itc_button.clicked.connect(lambda: self.assign_itc_to_selection())
        self.assign_itc_button.setEnabled(False)
        self.assign_itc_button.setToolTip("Assign new ITC value to selected points")
        
        polygon_layout.addWidget(self.draw_polygon_button)
        polygon_layout.addWidget(self.select_all_points_button)
        polygon_layout.addWidget(self.assign_itc_button)
        button_layout.addLayout(polygon_layout)

        self.volume_calc_button = ModernButton("Volume Calculation")
        self.volume_calc_button.clicked.connect(self.calculate_volume_from_selection)
        self.volume_calc_button.setEnabled(False)
        self.volume_calc_button.setToolTip("Perform circle fitting on selected points for volume calculation")
        button_layout.addWidget(self.volume_calc_button)

        self.save_volume_button = ModernButton("Save Volume Data")
        self.save_volume_button.clicked.connect(self.save_volume_data)
        self.save_volume_button.setEnabled(False)
        self.save_volume_button.setToolTip("Save current volume calculation data to file")
        button_layout.addWidget(self.save_volume_button)

        self.load_volume_button = ModernButton("Load Volume Data")
        self.load_volume_button.clicked.connect(self.load_volume_data)
        self.load_volume_button.setEnabled(True)
        self.load_volume_button.setToolTip("Load volume calculation data from file")
        button_layout.addWidget(self.load_volume_button)

        # Select folder for batch volume saves
        self.volume_folder_button = ModernButton("Select Volume Folder")
        self.volume_folder_button.clicked.connect(self.select_volume_folder)
        self.volume_folder_button.setEnabled(True)
        self.volume_folder_button.setToolTip("Pre-select folder for batch volume saves (avoids repeated folder selection)")
        button_layout.addWidget(self.volume_folder_button)

        self.clear_volume_button = ModernButton("Clear Volume Results")
        self.clear_volume_button.clicked.connect(self.clear_accumulated_volume)
        self.clear_volume_button.setEnabled(False)
        self.clear_volume_button.setToolTip("Clear all accumulated volume calculation results")
        button_layout.addWidget(self.clear_volume_button)



        self.crown_polygon_button = ModernButton("Tree Crown Polygon")
        self.crown_polygon_button.clicked.connect(self.create_tree_crown_polygon)
        self.crown_polygon_button.setEnabled(False)
        self.crown_polygon_button.setToolTip("Create 2D polygon from all tree points projected to XY plane")
        button_layout.addWidget(self.crown_polygon_button)



    # Extract component buttons removed per user request

        self.dbh_circles_button = ModernButton("DBH Circle Fitting")
        self.dbh_circles_button.clicked.connect(self.visualize_dbh_circles)
        self.dbh_circles_button.setEnabled(False)
        self.dbh_circles_button.setToolTip("Show circle fitting trajectory for DBH points in 3D")
        button_layout.addWidget(self.dbh_circles_button)

        self.fit_to_screen_button = ModernButton("Fit to Screen")
        self.fit_to_screen_button.clicked.connect(self.fit_to_screen)
        self.fit_to_screen_button.setEnabled(False)
        self.fit_to_screen_button.setToolTip("Reset camera to fit all visible objects in the view")
        button_layout.addWidget(self.fit_to_screen_button)

        self.split_button = ModernButton("Split Detection")
        self.split_button.clicked.connect(self.analyze_splits)
        self.split_button.setEnabled(False)
        button_layout.addWidget(self.split_button)

        # Add Decluster Branches controls
        decluster_layout = QHBoxLayout()
        self.slice_height_input = QSpinBox()
        self.slice_height_input.setMinimum(5)
        self.slice_height_input.setMaximum(50)
        self.slice_height_input.setValue(10)
        self.slice_height_input.setSuffix(" cm")
        self.slice_height_input.setToolTip("Height of each horizontal slice for branch separation")
        decluster_layout.addWidget(QLabel("Slice Height:"))
        decluster_layout.addWidget(self.slice_height_input)
        self.decluster_button = ModernButton("Decluster Branches")
        self.decluster_button.clicked.connect(self.visualize_height_slices)
        self.decluster_button.setEnabled(False)
        self.decluster_button.setToolTip("Separate trunk into horizontal slices for branch analysis")
        decluster_layout.addWidget(self.decluster_button)
        self.detect_branches_button = ModernButton("Detect Branches")
        self.detect_branches_button.clicked.connect(self.detect_branch_clusters_in_slices)
        self.detect_branches_button.setEnabled(False)
        self.detect_branches_button.setToolTip("Run DBSCAN on each slice to detect individual branches")
        decluster_layout.addWidget(self.detect_branches_button)
        button_layout.addLayout(decluster_layout)

        # Add AI Analysis button
        self.analyze_button = ModernButton("Analyze Tree")
        self.analyze_button.clicked.connect(self.analyze_tree_with_ai)
        self.analyze_button.setEnabled(False)
        self.analyze_button.setToolTip("Use AI to analyze tree structure and segmentation quality")
        button_layout.addWidget(self.analyze_button)

        # Add Batch Analyze button
        self.batch_analyze_button = ModernButton("Batch Analyze Trunk")
        self.batch_analyze_button.clicked.connect(self.batch_analyze_trunk_volumes)
        self.batch_analyze_button.setEnabled(False)
        self.batch_analyze_button.setToolTip("Analyze all trees in list: visualize trunk → select all points → calculate volume → save")
        button_layout.addWidget(self.batch_analyze_button)

        self.clear_button = ModernButton("Clear View")
        self.clear_button.clicked.connect(self.clear_plot)
        self.clear_button.setToolTip("Clear the 3D view and reset to default colors (removes cluster highlighting)")
        button_layout.addWidget(self.clear_button)

        self.save_button = ModernButton("Save LAS")
        self.save_button.clicked.connect(self.save_las_file)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)

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
        """Open file dialog and load LAS file."""
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("LAS files (*.las *.laz)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            self.load_las_data(file_path)

    def load_las_data(self, file_path):
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

            # Check for ITC field
            if 'itc' not in self.las_data.point_format.dimension_names:
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
                if num_points > LARGE_FILE_THRESHOLD:
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

            # Defer centroid pre-computation until first neighbor search to avoid slow loading
            # self.precompute_tree_centroids()  # Called lazily when needed

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
            self.save_button.setEnabled(True)
            self.fit_to_screen_button.setEnabled(True)

            total_time = time.perf_counter() - load_start
            print(f"[LOAD] {time.strftime('%H:%M:%S')} - Load complete: {total_time:.2f}s total")
            self.log_to_console(f"✅ Loaded {len(self.unique_itc_values)} trees from {num_points:,} points in {total_time:.2f}s")
            
            QMessageBox.information(self, "Success",
                                  f"Loaded {len(self.unique_itc_values)} unique tree IDs from {len(self.las_data.points)} points.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load LAS file:\n{str(e)}")
            self.las_data = None
        finally:
            self.progress_bar.setVisible(False)

    def update_tree_colors(self, color_field):
        """Update the coloring of the currently visualized tree."""
        if self.current_tree_points is None or self.current_tree_id is None or not self.plotter or not self.las_data or self.current_mask is None:
            print("Warning: No tree data available for coloring")
            return

        try:
            if color_field == "Default (green)":
                # Use default green color
                self.plotter.clear()
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, color='#4CAF50', point_size=2, render_points_as_spheres=False)
            elif color_field == "RGB (red, green, blue)":
                # Color by RGB values
                print(f"Coloring by RGB values")
                self.plotter.clear()
                
                # Extract RGB values from the current tree points
                available_fields = list(self.las_data.point_format.dimension_names)
                if 'red' in available_fields and 'green' in available_fields and 'blue' in available_fields:
                    # Get RGB values for the current tree(s)
                    all_rgb_values = []
                    if self.all_masks is not None:
                        # Multiple trees selected - use all_masks
                        for mask in self.all_masks:
                            red_vals = np.array(self.las_data['red'])[mask]
                            green_vals = np.array(self.las_data['green'])[mask]
                            blue_vals = np.array(self.las_data['blue'])[mask]
                            
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
                    self.plotter.add_points(point_cloud, scalars='rgb', rgb=True, point_size=2, render_points_as_spheres=False)
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
                            all_color_values = []
                            for mask in self.all_masks:
                                color_vals = np.array(self.las_data[color_field])[mask]
                                all_color_values.append(color_vals)
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
                    point_cloud = pv.PolyData(self.current_tree_points)
                    
                    if color_field == 'itc':
                        # Use a colormap with 9 distinct colors for ITC
                        self.plotter.add_points(point_cloud, scalars=color_values, point_size=2, render_points_as_spheres=False, 
                                              cmap='tab10', n_colors=9, clim=[0, 8])
                    else:
                        self.plotter.add_points(point_cloud, scalars=color_values, point_size=2, render_points_as_spheres=False, cmap='cividis')
                        
                except Exception as e:
                    print(f"Error coloring by field '{color_field}': {str(e)}")
                    QMessageBox.warning(self, "Warning", f"Failed to color by field '{color_field}': {str(e)}")
                    return

            # Reset camera and add title
            self.plotter.reset_camera()
            num_points = len(self.current_tree_points)
            self.plotter.add_text(f"Tree ID: {self.current_tree_id} ({num_points} points) - Color: {color_field}",
                                 position='upper_left', font_size=12, color='#FFFFFF')
            # Update instruction text
            self.plotter.add_text("Click on points to see ITC values", position='upper_right', 
                                font_size=10, color='#FFFFFF')
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

            # Extract and merge points for all selected trees
            all_points = []
            all_masks = []
            itc_values = np.array(self.las_data['itc'])
            
            for tree_id in selected_tree_ids:
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
                    all_masks.append(mask)

            if not all_points:
                print(f"Warning: No points found for selected tree IDs: {selected_tree_ids}")
                QMessageBox.warning(self, "Warning", f"No points found for selected tree IDs: {selected_tree_ids}")
                return

            # Merge all points
            merged_points = np.vstack(all_points)
            merged_mask = np.concatenate(all_masks)

            print(f"Visualizing {len(selected_tree_ids)} trees with {len(merged_points)} total points")

            # Create tree ID mapping for each point in merged_points
            self.current_tree_ids = []
            for i, (tree_id, points) in enumerate(zip(selected_tree_ids, all_points)):
                self.current_tree_ids.extend([tree_id] * len(points))
            self.current_tree_ids = np.array(self.current_tree_ids)

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
                all_color_values = []
                for mask in all_masks:
                    color_vals = np.array(self.las_data[color_field])[mask]
                    all_color_values.append(color_vals)
                self.current_color_values = np.concatenate(all_color_values)
                self.current_color_field = color_field
            else:
                self.current_color_values = None
                self.current_color_field = color_field

            # Collect ITC values for point picking
            all_itc_values = []
            for mask in all_masks:
                itc_vals = np.array(self.las_data['itc'])[mask]
                all_itc_values.append(itc_vals)
            self.current_itc_values = np.concatenate(all_itc_values)

            # Visualize with current color field
            self.update_tree_colors(color_field)

            # Add bounding box visualization
            if len(merged_points) > 0:
                bounds = [
                    np.min(merged_points[:, 0]), np.max(merged_points[:, 0]),
                    np.min(merged_points[:, 1]), np.max(merged_points[:, 1]),
                    np.min(merged_points[:, 2]), np.max(merged_points[:, 2])
                ]
                bounding_box = pv.Cube(bounds=bounds)
                self.plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                                    label='Tree Bounding Box')

            # Enable analyze button for tree analysis
            self.analyze_button.setEnabled(True)

            # Enable polygon selection buttons
            self.draw_polygon_button.setEnabled(True)
            self.select_all_points_button.setEnabled(True)

            # Disable split detection for multiple tree visualization
            self.split_button.setEnabled(False)

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
            # Visualize with current color field
            self.update_tree_colors(self.color_combo.currentText())

            # Enable split detection button for merged trunks
            self.split_button.setEnabled(True)
            self.analyze_button.setEnabled(True)
            self.decluster_button.setEnabled(True)
            self.detect_branches_button.setEnabled(True)

            # Enable polygon selection buttons
            self.draw_polygon_button.setEnabled(True)
            self.select_all_points_button.setEnabled(True)

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



    def analyze_splits(self):
        """Analyze split detection on the currently visualized trunk points."""
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            print("Warning: No trunk points available for split analysis")
            QMessageBox.warning(self, "Warning", "No trunk points available for split analysis.")
            return

        try:
            # Run split detection analysis on trunk points
            results = self.analyze_trunk_splits(self.current_tree_points)

            # Show interactive visualization for ALL height levels (not just branching)
            self.interactive_cluster_visualization(results)

            # Display results in a message box
            self.show_split_results(results)

        except Exception as e:
            print(f"Error in analyze_splits: {str(e)}")
            QMessageBox.critical(self, "Error", f"Split analysis failed: {str(e)}")

    def analyze_trunk_splits(self, trunk_points: np.ndarray):
        """
        Analyze split detection on trunk points using height-wise clustering.

        Args:
            trunk_points: Nx3 array of trunk points

        Returns:
            List of analysis results for each height, including cluster data for visualization
        """
        print("Analyzing trunk splits...")

        # Get parameters from UI inputs
        try:
            max_height = float(self.max_height_input.text())
            step = float(self.step_input.text())
            thickness = float(self.thickness_input.text())
            min_samples = int(self.min_points_input.text())
            
            # Validate parameters
            if max_height <= 0 or max_height > 50:
                raise ValueError("Max height must be between 0.1 and 50 meters")
            if step <= 0 or step > max_height:
                raise ValueError("Step must be between 0.01 and max height")
            if thickness <= 0 or thickness > 1:
                raise ValueError("Thickness must be between 0.01 and 1 meter")
            if min_samples < 2 or min_samples > 20:
                raise ValueError("Min points must be between 2 and 20")
                
        except ValueError as e:
            print(f"Error validating split detection parameters: {str(e)}")
            QMessageBox.warning(self, "Invalid Parameters", 
                              f"Please enter valid values for split detection parameters.\nError: {e}")
            return

        try:
            # DBSCAN eps parameter (fixed for now, could add UI control later)
            eps = 0.2

            min_z = np.min(trunk_points[:, 2])
            heights = np.arange(0.0, min(max_height, np.max(trunk_points[:, 2]) - min_z) + step, step)
            results = []

            for height in heights:
                target_z = min_z + height

                # Extract plane cut
                lower_bound = target_z - thickness/2
                upper_bound = target_z + thickness/2
                mask = (trunk_points[:, 2] >= lower_bound) & (trunk_points[:, 2] <= upper_bound)
                plane_points = trunk_points[mask]

                if len(plane_points) < min_samples:
                    results.append({
                        'height': height,
                        'n_points': len(plane_points),
                        'n_clusters': 0,
                        'n_noise': len(plane_points),
                        'cluster_sizes': [],
                        'plane_points': plane_points,
                        'labels': np.array([]),
                        'cluster_centers': []
                    })
                    continue

                # Extract 2D coordinates for clustering
                plane_points_2d = plane_points[:, :2]

                # Apply DBSCAN clustering
                clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(plane_points_2d)
                labels = clustering.labels_

                # Count clusters (excluding noise labeled -1)
                n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
                n_noise = list(labels).count(-1)

                # Get cluster sizes and centers
                cluster_sizes = []
                cluster_centers = []
                cluster_circles = []  # Store fitted circles for each cluster
                for label in set(labels):
                    if label != -1:
                        cluster_mask = labels == label
                        cluster_sizes.append(np.sum(cluster_mask))
                        cluster_center = np.mean(plane_points_2d[cluster_mask], axis=0)
                        cluster_centers.append(cluster_center)
                        
                        # Fit circle to cluster points
                        cluster_points = plane_points_2d[cluster_mask]
                        circle_params = self.fit_circle_to_points(cluster_points)
                        cluster_circles.append(circle_params)

                # Check circle sizes and merge if not within 80% of each other
                merged_clusters = False
                if len(cluster_circles) > 1:
                    radii = [circle['radius'] for circle in cluster_circles if circle is not None]
                    centers = [circle['center'] for circle in cluster_circles if circle is not None]
                    
                    if len(radii) > 1:
                        max_radius = max(radii)
                        min_radius = min(radii)
                        
                        # Check if circles overlap
                        circles_overlap = False
                        for i in range(len(centers)):
                            for j in range(i+1, len(centers)):
                                center1 = np.array(centers[i])
                                center2 = np.array(centers[j])
                                distance = np.linalg.norm(center1 - center2)
                                if distance < (radii[i] + radii[j]):
                                    circles_overlap = True
                                    break
                            if circles_overlap:
                                break
                        
                        # If circles are not within 80% of each other (smaller circle < 80% of larger) OR they overlap, merge all clusters
                        percentage = (min_radius / max_radius) * 100 if max_radius > 0 else 0
                        if percentage < 80 or circles_overlap:
                            merged_clusters = True
                            merge_reason = "overlapping circles" if circles_overlap else f"smaller circle is {percentage:.1f}% of larger"
                            print(f"Merging {len(cluster_circles)} clusters at height {height:.2f}m ({merge_reason})")
                            
                            # Combine all cluster points into one
                            all_cluster_points = []
                            for label in set(labels):
                                if label != -1:
                                    cluster_mask = labels == label
                                    cluster_points = plane_points_2d[cluster_mask]
                                    all_cluster_points.extend(cluster_points)
                            
                            all_cluster_points = np.array(all_cluster_points)
                            
                            # Fit single circle to all combined points
                            combined_circle = self.fit_circle_to_points(all_cluster_points)
                            
                            # Update results for merged clusters
                            cluster_sizes = [len(all_cluster_points)]
                            cluster_centers = [np.mean(all_cluster_points, axis=0)]
                            cluster_circles = [combined_circle]
                            n_clusters = 1
                            
                            # Update labels to treat all as one cluster
                            labels = np.where(labels != -1, 0, -1)

                results.append({
                    'height': height,
                    'n_points': len(plane_points),
                    'n_clusters': n_clusters,
                    'n_noise': n_noise,
                    'cluster_sizes': cluster_sizes,
                    'plane_points': plane_points,
                    'labels': labels,
                    'cluster_centers': cluster_centers,
                    'cluster_circles': cluster_circles,
                    'merged_clusters': merged_clusters,
                    'merge_reason': merge_reason if merged_clusters else None
                })

            print(f"Split analysis completed for {len(heights)} height levels")
            return results

        except Exception as e:
            print(f"Error in analyze_trunk_splits: {str(e)}")
            raise

    def fit_circle_to_points(self, points):
        """
        Fit a circle to a set of 2D points using least squares optimization.
        
        Args:
            points: Nx2 array of (x, y) coordinates
            
        Returns:
            Dictionary with circle parameters: {'center': (x, y), 'radius': r}
        """
        if len(points) < 3:
            # Not enough points for circle fitting, return centroid and average distance
            center = np.mean(points, axis=0)
            distances = np.linalg.norm(points - center, axis=1)
            radius = np.mean(distances)
            return {'center': center, 'radius': radius}
        
        try:
            from scipy.optimize import minimize
            
            # Initial guess: centroid and average distance to centroid
            x_mean, y_mean = np.mean(points, axis=0)
            distances = np.linalg.norm(points - np.array([x_mean, y_mean]), axis=1)
            r_guess = np.mean(distances)
            
            def circle_residuals(params):
                """Calculate residuals for circle fitting."""
                x_c, y_c, r = params
                distances = np.sqrt((points[:, 0] - x_c)**2 + (points[:, 1] - y_c)**2)
                return np.sum((distances - r)**2)
            
            # Optimize circle parameters
            result = minimize(circle_residuals, [x_mean, y_mean, r_guess], 
                            method='L-BFGS-B', 
                            bounds=[(None, None), (None, None), (0.01, None)])
            
            if result.success:
                x_c, y_c, r = result.x
                return {'center': np.array([x_c, y_c]), 'radius': r}
            else:
                # Fallback to simple method
                center = np.mean(points, axis=0)
                distances = np.linalg.norm(points - center, axis=1)
                radius = np.mean(distances)
                return {'center': center, 'radius': radius}
                
        except ImportError:
            # Fallback if scipy not available
            center = np.mean(points, axis=0)
            distances = np.linalg.norm(points - center, axis=1)
            radius = np.mean(distances)
            return {'center': center, 'radius': radius}

    def interactive_cluster_visualization(self, all_results):
        """
        Show interactive 2D cluster visualization for each height level.

        Args:
            all_results: List of all analysis results for each height
        """
        if not all_results:
            QMessageBox.information(self, "No Results", 
                                  "No analysis results available.")
            return

        # Create dialog for interactive visualization
        dialog = QDialog(self)
        dialog.setWindowTitle("Interactive Cluster Visualization - All Heights")
        dialog.setModal(False)  # Allow interaction with main window
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)  # Don't force on top
        dialog.resize(1000, 700)  # Made slightly larger for toolbar

        # Create layout
        layout = QVBoxLayout(dialog)

        # Create matplotlib figure with navigation toolbar
        self.cluster_fig = plt.figure(figsize=(10, 8))
        self.cluster_ax = self.cluster_fig.add_subplot(111)
        self.cluster_canvas = FigureCanvas(self.cluster_fig)
        
        # Add navigation toolbar for zoom/pan functionality
        from matplotlib.backends.backend_qt5 import NavigationToolbar2QT
        self.nav_toolbar = NavigationToolbar2QT(self.cluster_canvas, dialog)
        
        layout.addWidget(self.nav_toolbar)
        layout.addWidget(self.cluster_canvas)

        # Info label with interaction instructions
        self.cluster_info_label = QLabel()
        self.cluster_info_label.setStyleSheet("font-weight: bold; color: #666;")
        layout.addWidget(self.cluster_info_label)

        # Navigation buttons
        button_layout = QHBoxLayout()

        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(lambda: self.show_cluster_at_index(self.current_cluster_index - 1, all_results))
        button_layout.addWidget(self.prev_button)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(lambda: self.show_cluster_at_index(self.current_cluster_index + 1, all_results))
        button_layout.addWidget(self.next_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        # Initialize with first result
        self.current_cluster_index = 0
        self.show_cluster_at_index(0, all_results)

        # Update button states
        self.update_navigation_buttons(all_results)

        dialog.exec_()

        # After closing the 2D dialog, visualize split planes in the main 3D view
        self.visualize_split_planes(all_results)

        # Keep the last viewed cluster highlighting instead of resetting
        # The 3D view will maintain the cluster colors for the last viewed height

    def show_cluster_at_index(self, index, all_results):
        """Show the cluster visualization for the specified index."""
        if index < 0 or index >= len(all_results):
            return

        result = all_results[index]
        self.current_cluster_index = index

        # Clear previous plot
        self.cluster_ax.clear()

        # Get 2D points and labels
        plane_points = result['plane_points']
        labels = result['labels']

        if len(plane_points) == 0:
            self.cluster_ax.text(0.5, 0.5, 'No points at this height', 
                               ha='center', va='center', transform=self.cluster_ax.transAxes)
        else:
            # Extract 2D coordinates
            x_coords = plane_points[:, 0]
            y_coords = plane_points[:, 1]

            # Only add legend if there are labeled artists
            legend_handles = []
            unique_labels = set(labels)
            colors = plt.cm.rainbow(np.linspace(0, 1, len(unique_labels)))
            for i, label in enumerate(unique_labels):
                if label == -1:
                    # Noise points
                    mask = labels == label
                    if np.any(mask):
                        scatter = self.cluster_ax.scatter(x_coords[mask], y_coords[mask], 
                                                      c='black', alpha=0.5, s=20, label='Noise')
                        legend_handles.append(scatter)
                else:
                    # Cluster points
                    mask = labels == label
                    if np.any(mask):
                        scatter = self.cluster_ax.scatter(x_coords[mask], y_coords[mask], 
                                                      c=[colors[i]], alpha=0.7, s=30, 
                                                      label=f'Cluster {label} ({np.sum(mask)} points)')
                        legend_handles.append(scatter)

            # Plot cluster centers if available
            if result['cluster_centers']:
                centers = np.array(result['cluster_centers'])
                scatter_centers = self.cluster_ax.scatter(centers[:, 0], centers[:, 1], 
                                                      c='red', marker='x', s=100, linewidth=3, 
                                                      label='Cluster Centers')
                legend_handles.append(scatter_centers)

            # Plot fitted circles for each cluster
            if 'cluster_circles' in result and result['cluster_circles']:
                for i, circle_params in enumerate(result['cluster_circles']):
                    if circle_params:
                        center = circle_params['center']
                        radius = circle_params['radius']
                        
                        # Create circle patch
                        circle_patch = plt.Circle(center, radius, fill=False, 
                                                color=colors[i % len(colors)], 
                                                linewidth=2, linestyle='--',
                                                alpha=0.8, label=f'Cluster {i} Circle (r={radius:.2f}m)')
                        self.cluster_ax.add_patch(circle_patch)
                        
                        # Add circle center marker
                        self.cluster_ax.scatter([center[0]], [center[1]], 
                                              color=colors[i % len(colors)], marker='o', 
                                              s=50, edgecolors='black', linewidth=2,
                                              label=f'Cluster {i} Circle Center')

            # Add legend only if we have handles
            if legend_handles:
                self.cluster_ax.legend()
            self.cluster_ax.set_xlabel('X Coordinate')
            self.cluster_ax.set_ylabel('Y Coordinate')
            self.cluster_ax.set_title('.2f')
            self.cluster_ax.grid(True, alpha=0.3)

        # Update info label
        interaction_note = "💡 Use toolbar to zoom/pan 2D plot. Circles show fitted cluster boundaries. Interact with 3D view simultaneously."
        if result.get('merged_clusters', False):
            merge_reason = result.get('merge_reason', 'size differences or overlapping circles')
            merged_note = f"🔄 Clusters merged due to: {merge_reason}"
        else:
            merged_note = ""
        info_text = f"Height: {result['height']:.2f}m | Points: {result['n_points']} | " \
                   f"Clusters: {result['n_clusters']} | Noise: {result['n_noise']}\n" \
                   f"Height #{index + 1} of {len(all_results)}\n" \
                   f"{interaction_note}\n" \
                   f"{merged_note}"
        self.cluster_info_label.setText(info_text)

        # Redraw canvas
        self.cluster_canvas.draw()

        # Update navigation buttons
        self.update_navigation_buttons(all_results)

        # Highlight corresponding points in 3D visualization
        self.highlight_3d_clusters(result)

    def update_navigation_buttons(self, all_results):
        """Update the state of navigation buttons."""
        self.prev_button.setEnabled(self.current_cluster_index > 0)
        self.next_button.setEnabled(self.current_cluster_index < len(all_results) - 1)

    def highlight_3d_clusters(self, result):
        """Highlight the cluster points in the 3D visualization."""
        if not self.plotter or self.current_tree_points is None:
            return

        try:
            # Clear previous cluster highlighting
            self.plotter.remove_actor('cluster_highlighted_points')
            self.plotter.remove_actor('cluster_other_points')

            # Get the height and thickness for the current slice
            height = result['height']
            thickness = float(self.thickness_input.text())
            min_z = np.min(self.current_tree_points[:, 2])
            target_z = min_z + height

            # Define the height range for this slice
            lower_bound = target_z - thickness/2
            upper_bound = target_z + thickness/2

            # Find points in this height slice
            height_mask = (self.current_tree_points[:, 2] >= lower_bound) & \
                         (self.current_tree_points[:, 2] <= upper_bound)

            if not np.any(height_mask):
                return

            # Get cluster labels for points in this slice
            slice_points = self.current_tree_points[height_mask]
            slice_labels = result['labels']

            # Create colors for clusters (matching 2D visualization)
            unique_labels = set(slice_labels)
            n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)

            if n_clusters > 0:
                # Use same color scheme as 2D plot
                colors = plt.cm.rainbow(np.linspace(0, 1, len(unique_labels)))

                # Create color array for all slice points
                point_colors = np.zeros((len(slice_points), 3))

                for i, label in enumerate(unique_labels):
                    if label == -1:
                        # Noise points - gray
                        mask = slice_labels == label
                        point_colors[mask] = [0.5, 0.5, 0.5]  # Gray
                    else:
                        # Cluster points - rainbow colors
                        mask = slice_labels == label
                        rgb = colors[i][:3]  # Get RGB values
                        point_colors[mask] = rgb

                # Create point cloud for highlighted slice
                highlighted_cloud = pv.PolyData(slice_points)
                self.plotter.add_points(highlighted_cloud, scalars=point_colors,
                                      rgb=True, point_size=6, render_points_as_spheres=True,
                                      name='cluster_highlighted_points')

            # Show remaining trunk points in subdued color
            other_mask = ~height_mask
            if np.any(other_mask):
                other_points = self.current_tree_points[other_mask]
                other_cloud = pv.PolyData(other_points)
                self.plotter.add_points(other_cloud, color='#404040',  # Dark gray
                                      point_size=2, render_points_as_spheres=False,
                                      name='cluster_other_points')

            # Add fitted circles in 3D at the current height level
            if 'cluster_circles' in result and result['cluster_circles']:
                for i, circle_params in enumerate(result['cluster_circles']):
                    if circle_params:
                        center_2d = circle_params['center']
                        radius = circle_params['radius']
                        
                        # Create 3D circle at the current height
                        # Use parametric equation for circle
                        theta = np.linspace(0, 2*np.pi, 50)
                        x_circle = center_2d[0] + radius * np.cos(theta)
                        y_circle = center_2d[1] + radius * np.sin(theta)
                        z_circle = np.full_like(theta, target_z)  # At the slice height
                        
                        # Create circle points
                        circle_points_3d = np.column_stack([x_circle, y_circle, z_circle])
                        circle_cloud = pv.PolyData(circle_points_3d)
                        
                        # Use same color as 2D plot
                        color_rgb = colors[i % len(colors)][:3]
                        
                        # Add circle as line loop
                        lines = []
                        for j in range(len(circle_points_3d)):
                            lines.extend([circle_points_3d[j], circle_points_3d[(j+1) % len(circle_points_3d)]])
                        
                        if lines:
                            lines_array = np.array(lines)
                            self.plotter.add_lines(lines_array, color=color_rgb, width=3,
                                                 name=f'cluster_circle_{i}')

            # Update plot
            self.plotter.update()

        except Exception as e:
            print(f"Error highlighting 3D clusters: {str(e)}")
            # Fallback: just show all points in default color
            try:
                self.plotter.remove_actor('cluster_highlighted_points')
                self.plotter.remove_actor('cluster_other_points')
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, color='#4CAF50', point_size=2,
                                      render_points_as_spheres=False, name='cluster_highlighted_points')
                self.plotter.update()
            except:
                pass

    def reset_3d_visualization(self):
        """Reset the 3D visualization to default colors."""
        if not self.plotter or self.current_tree_points is None:
            return

        try:
            # Clear cluster highlighting actors
            self.plotter.remove_actor('cluster_highlighted_points')
            self.plotter.remove_actor('cluster_other_points')
            
            # Clear circle actors
            for i in range(10):  # Clear up to 10 circle actors
                try:
                    self.plotter.remove_actor(f'cluster_circle_{i}')
                except:
                    pass

            # Restore default visualization
            self.update_tree_colors(self.color_combo.currentText())

        except Exception as e:
            print(f"Error resetting 3D visualization: {str(e)}")
            # Fallback: just show all points in default green
            try:
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, color='#4CAF50', point_size=2,
                                      render_points_as_spheres=False)
                self.plotter.update()
            except:
                pass

    def show_split_results(self, results):
        """Display split analysis results to console."""
        if not results:
            self.log_to_console("Split Analysis: No analysis results available.")
            return

        # Find branching height (first height where clusters >= 2)
        branching_height = None
        for i, result in enumerate(results):
            if result['n_clusters'] >= 2 and (i == 0 or results[i-1]['n_clusters'] < 2):
                branching_height = result['height']
                break

        # Create results text
        result_text = f"Trunk Split Detection Results - {self.current_tree_id}\n"
        result_text += "=" * 60 + "\n\n"

        # Add parameters used
        result_text += "Parameters Used:\n"
        result_text += f"  Max Height: {self.max_height_input.text()}m\n"
        result_text += f"  Step: {self.step_input.text()}m\n"
        result_text += f"  Thickness: {self.thickness_input.text()}m\n"
        result_text += f"  Min Points: {self.min_points_input.text()}\n"
        result_text += f"  DBSCAN eps: 0.2m\n\n"

        if branching_height is not None:
            result_text += f"🔍 FIRST BRANCHING DETECTED at {branching_height:.1f}m above base!\n"
            result_text += f"   📍 Primary split location marked with bright red plane in 3D view\n\n"
        else:
            result_text += "✅ No branching detected within analyzed height range.\n\n"

        result_text += "Height Analysis:\n"
        result_text += "-" * 40 + "\n"
        result_text += f"{'Height':<8} {'Points':<8} {'Clusters':<10} {'Noise':<8} {'Sizes'}\n"
        result_text += "-" * 40 + "\n"

        # Count merged clusters and collect merge reasons
        merged_info = []
        for result in results:
            if result.get('merged_clusters', False):
                merge_reason = result.get('merge_reason', 'size differences or overlapping circles')
                merged_info.append(f"  {result['height']:.1f}m: {merge_reason}")

        for result in results:
            sizes_str = str(result.get('cluster_sizes', [])) if result.get('cluster_sizes') else 'N/A'
            merged_indicator = " (merged)" if result.get('merged_clusters', False) else ""
            result_text += f"{result['height']:<8.1f} {result['n_points']:<8} {result['n_clusters']:<10} {result['n_noise']:<8} {sizes_str}{merged_indicator}\n"

        if merged_info:
            result_text += f"\nMerged Clusters Details ({len(merged_info)} levels):\n"
            for info in merged_info:
                result_text += f"{info}\n"

        # Log to console instead of showing dialog
        self.log_to_console(result_text)

        # Additional prominent message for first split
        if branching_height is not None:
            self.log_to_console(f"🚨 FIRST SPLIT DETECTED: {branching_height:.1f}m above base - Marked with bright red plane in 3D view!")

        # Create DBH points scalar field
        self.create_dbh_points_field(results, branching_height)

    def visualize_split_planes(self, results):
        """Visualize split planes at branching heights."""
        if not self.plotter or not results:
            return

        # Find branching heights (where clusters >= 2)
        branching_heights = []
        for result in results:
            if result['n_clusters'] >= 2:
                branching_heights.append(result['height'])

        if not branching_heights:
            return  # No splits to visualize

        # Find the first branching height for special highlighting
        first_branching_height = None
        for i, result in enumerate(results):
            if result['n_clusters'] >= 2 and (i == 0 or results[i-1]['n_clusters'] < 2):
                first_branching_height = result['height']
                break

        # Get trunk base coordinates for plane positioning
        if self.current_tree_points is not None and len(self.current_tree_points) > 0:
            min_z = np.min(self.current_tree_points[:, 2])
            # Use centroid of base points for plane center
            base_points = self.current_tree_points[self.current_tree_points[:, 2] < min_z + 0.5]  # Points within 0.5m of base
            if len(base_points) > 0:
                center_x = np.mean(base_points[:, 0])
                center_y = np.mean(base_points[:, 1])
            else:
                # Fallback to overall centroid
                center_x = np.mean(self.current_tree_points[:, 0])
                center_y = np.mean(self.current_tree_points[:, 1])

            # Create and add split planes
            for i, height in enumerate(branching_heights):
                plane_z = min_z + height

                # Create a disk/plane at the branching height
                # Use a reasonable radius based on trunk spread
                radius = 0.5  # 1 meter diameter

                # Create a square plane and position it at the branching height
                plane_size = 1.0  # 1m x 1m plane
                plane_center = [float(center_x), float(center_y), float(plane_z)]
                plane = pv.Plane(center=plane_center, direction=(0, 0, 1),
                               i_size=plane_size, j_size=plane_size)

                # Special highlighting for first split
                is_first_split = (height == first_branching_height)
                if is_first_split:
                    # First split: Bright red, larger, more opaque
                    color = '#FF0000'  # Bright red
                    opacity = 0.9
                    plane_size = 1.5  # Larger plane
                    label = f'🚨 FIRST SPLIT: {height:.1f}m'
                    point_color = '#FF0000'
                else:
                    # Subsequent splits: Alternate colors, less prominent
                    color = '#FF4444' if i % 2 == 0 else '#FF8844'
                    opacity = 0.7
                    label = f'Split at {height:.1f}m'
                    point_color = color

                # Recreate plane with correct size for first split
                if is_first_split:
                    plane = pv.Plane(center=plane_center, direction=(0, 0, 1),
                                   i_size=plane_size, j_size=plane_size)

                # Add plane to plotter
                self.plotter.add_mesh(plane, color=color, opacity=opacity, label=label)

                # Add height label with appropriate styling
                label_offset = radius + 0.2 if is_first_split else radius + 0.1
                self.plotter.add_point_labels([(center_x + label_offset, center_y, plane_z)],
                                            [f'{height:.1f}m' + (' 🚨' if is_first_split else '')],
                                            font_size=12 if is_first_split else 10,
                                            text_color='yellow' if is_first_split else 'white',
                                            point_color=point_color, point_size=8 if is_first_split else 5)

        # Update the plot
        self.plotter.update()

    def create_dbh_points_field(self, results, branching_height):
        """Create DBH points scalar field containing trunk points below first split height."""
        if self.las_data is None or self.current_mask is None:
            return

        try:
            # Initialize dbh_points field with zeros
            dbh_points = np.zeros(len(self.las_data), dtype=np.uint8)

            # Get the height threshold
            if branching_height is not None:
                # Use first split height as threshold
                min_z = np.min(self.current_tree_points[:, 2])
                height_threshold = min_z + branching_height
                self.log_to_console(f"📏 Creating DBH points field: trunk points below {branching_height:.1f}m (first split height)")
            else:
                # No split detected, use all trunk points
                height_threshold = np.inf
                self.log_to_console("📏 Creating DBH points field: all trunk points (no split detected)")

            # Find indices of current tree points that are below the threshold
            tree_indices = np.where(self.current_mask)[0]
            tree_points_z = np.array(self.las_data.z)[tree_indices]

            # Mark points below threshold as DBH points (value = 1)
            dbh_mask = tree_points_z < height_threshold
            dbh_indices = tree_indices[dbh_mask]
            dbh_points[dbh_indices] = 1

            # Add or update the scalar field in LAS data
            field_name = "dbh_points"
            if field_name in self.las_data.point_format.dimension_names:
                # Field already exists, update it
                self.las_data[field_name] = dbh_points
                self.log_to_console("✅ Updated existing 'dbh_points' scalar field")
            else:
                # Field doesn't exist, add it
                try:
                    self.las_data.add_extra_dim(laspy.ExtraBytesParams(name=field_name, type=np.uint8))
                    self.las_data[field_name] = dbh_points
                    self.log_to_console("✅ Added new 'dbh_points' scalar field to LAS data")
                except Exception as e:
                    self.log_to_console(f"⚠️ Could not create 'dbh_points' field: {str(e)}")
                    return

            # Set the field values
            self.las_data['dbh_points'] = dbh_points

            # Count DBH points
            n_dbh_points = np.sum(dbh_points)
            self.log_to_console(f"📊 DBH points created: {n_dbh_points} points marked for tree {self.current_tree_id}")

            # Refresh color combo box to include the new DBH points field
            self.refresh_color_combo_box()

            # Enable DBH component extraction if we have DBH points
            if np.sum(dbh_points) > 0:
                if hasattr(self, 'extract_dbh_button'):
                    self.extract_dbh_button.setEnabled(True)
                self.dbh_circles_button.setEnabled(True)

        except Exception as e:
            self.log_to_console(f"❌ Error creating DBH points field: {str(e)}")
            print(f"Error in create_dbh_points_field: {str(e)}")

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
                neighbor_tree_ids.extend([candidate_tree_ids[i] for i in indices])
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
            print(f"Built KDTree with {len(centroids_array)} centroids")
        
        print(f"Pre-computed centroids for {len(self.tree_centroids_cache)} trees using {num_workers} parallel workers")

    def on_filter_changed(self):
        """Clear centroids cache when filter checkbox changes (will be recomputed lazily)."""
        if self.las_data is not None and len(self.unique_itc_values) > 0:
            self.tree_centroids_cache = {}
            self.centroids_kdtree = None
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

    def on_point_picked(self, picked_info):
        """Callback for point picking - shows ITC value of picked point."""
        if self.current_tree_points is None or self.current_itc_values is None:
            self.log_to_console("Warning: No tree data available for point picking")
            return

        try:
            # Get the picked point index
            if hasattr(picked_info, 'point_index'):
                point_index = picked_info.point_index
            elif isinstance(picked_info, dict) and 'point_index' in picked_info:
                point_index = picked_info['point_index']
            else:
                # Fallback: find closest point
                picked_point = picked_info
                if hasattr(picked_info, 'points'):
                    picked_point = picked_info.points[0]
                
                # Find closest point in current visualization
                distances = np.sum((self.current_tree_points - picked_point)**2, axis=1)
                point_index = np.argmin(distances)

            if point_index < len(self.current_itc_values):
                itc_value = self.current_itc_values[point_index]
                point_coords = self.current_tree_points[point_index]
                
                # Log to console
                message = f"Point picked - ITC: {itc_value}, Coordinates: ({point_coords[0]:.2f}, {point_coords[1]:.2f}, {point_coords[2]:.2f})"
                self.log_to_console(message)
            else:
                self.log_to_console("Warning: Point index out of range")

        except Exception as e:
            self.log_to_console(f"Error in point picking: {str(e)}")

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
            self.plotter.reset_camera()
            self.plotter.update()
        
        # Reset cluster highlighting state
        self.current_cluster_index = -1
        
        # Disable buttons when clearing
        self.split_button.setEnabled(False)
        self.decluster_button.setEnabled(False)
        self.detect_branches_button.setEnabled(False)
    # extract buttons removed
        self.dbh_circles_button.setEnabled(False)
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
        Automated batch processing: iterate through all tree IDs with trunk points,
        visualize trunk → select all points → calculate volume for each.
        Save folder is requested once at the beginning and reused for all saves.
        """
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        # Check if stemcls field exists
        if 'stemcls' not in self.las_data.point_format.dimension_names:
            QMessageBox.warning(self, "Warning", "No 'stemcls' scalar field found in the LAS file.")
            return

        try:
            import time

            batch_start_perf = time.perf_counter()
            batch_start_dt = datetime.now()
            self.log_to_console(f"⏱️ Batch analysis started at {batch_start_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            # Step 1: Prompt user for volume save folder (once at the beginning)
            folder = QFileDialog.getExistingDirectory(
                self, "Select Folder to Save Volume Results",
                ""
            )
            if not folder:
                self.log_to_console("ℹ️ Batch analysis cancelled - no folder selected.")
                return

            self.volume_folder_path = folder  # Store for reuse during batch
            self.log_to_console(f"✅ Volume save folder set to: {folder}")

            # Step 2: Get all tree IDs in sorted order (first to last)
            all_forest_ids = sorted(self.unique_itc_values.tolist())
            self.log_to_console(f"📋 Found {len(all_forest_ids)} tree IDs in list")

            # Step 3: Filter to only trees that have trunk points (stemcls != 1)
            itc_values = np.array(self.las_data['itc'])
            stemcls_values = np.array(self.las_data['stemcls'])
            
            valid_tree_ids = []
            for tree_id in all_forest_ids:
                mask = (itc_values == tree_id) & (stemcls_values != 1)
                if np.any(mask):
                    valid_tree_ids.append(tree_id)

            self.log_to_console(f"🌳 Trees with trunk points: {len(valid_tree_ids)} / {len(all_forest_ids)}")

            if not valid_tree_ids:
                QMessageBox.warning(self, "Warning", "No trees with trunk points found in the list.")
                return

            # Step 4: Clear any accumulated volume data to start fresh
            self.accumulated_volume_sections = []
            self.log_to_console("🔄 Cleared previous volume results.")

            # Step 5: Loop through each valid tree and process
            processed_count = 0
            skipped_trees = []
            
            for idx, tree_id in enumerate(valid_tree_ids, 1):
                self.log_to_console(f"\n\n📍 Processing tree {idx}/{len(valid_tree_ids)}: ID={tree_id}")
                
                try:
                    # Step 5a: Visualize trunk for this single tree
                    self._visualize_trunk_single_tree(tree_id)
                    QApplication.processEvents()  # Update UI
                    
                    # Step 5b: Select all points in the visualization
                    self._select_all_points_silent()
                    QApplication.processEvents()  # Update UI
                    
                    # Step 5c: Calculate volume for this selection
                    self._calculate_volume_silent()
                    QApplication.processEvents()  # Update UI
                    
                    processed_count += 1
                    self.log_to_console(f"✅ Successfully processed tree {tree_id}")
                    
                except Exception as e:
                    self.log_to_console(f"⚠️ Skipped tree {tree_id}: {str(e)}")
                    skipped_trees.append((tree_id, str(e)))
                finally:
                    elapsed_seconds = max(time.perf_counter() - batch_start_perf, 1e-9)
                    elapsed_minutes = elapsed_seconds / 60.0
                    trees_per_min = idx / elapsed_minutes if elapsed_minutes > 0 else 0.0
                    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))
                    self.log_to_console(
                        f"📈 Status: {idx}/{len(valid_tree_ids)} trees | {trees_per_min:.2f} trees/min | elapsed {elapsed_str}"
                    )

            # Step 6: Save all accumulated volumes once to the pre-selected folder
            if self.accumulated_volume_sections:
                self.log_to_console(f"\n\n📊 Saving {len(self.accumulated_volume_sections)} sections to file...")
                self._save_volume_data_silent()
            else:
                self.log_to_console("⚠️ No volume data to save.")

            batch_end_dt = datetime.now()
            elapsed_seconds = max(time.perf_counter() - batch_start_perf, 1e-9)
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))
            self.log_to_console(
                f"⏱️ Batch analysis ended at {batch_end_dt.strftime('%Y-%m-%d %H:%M:%S')} | duration {elapsed_str}"
            )

            # Step 7: Display completion summary
            self._display_batch_completion_summary(
                processed_count,
                len(valid_tree_ids),
                skipped_trees,
                batch_start_dt,
                batch_end_dt,
                elapsed_seconds,
            )

        except Exception as e:
            self.log_to_console(f"❌ Batch analysis error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Batch analysis failed: {str(e)}")


    def _visualize_trunk_single_tree(self, tree_id):
        """Visualize trunk for a single tree ID in batch mode."""
        if self.las_data is None:
            raise RuntimeError("No LAS data available")

        if not self.plotter:
            raise RuntimeError("3D viewer not initialized")

        # Clear previous visualization
        self.plotter.clear()

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

        if self.plotter is not None:
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
                    label=f'Section {section_id}{branch_suffix} Points ({len(group_points)} pts)'
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
                        f"📏 Calculated volume for tree {section_tree_id}, branch B{group_branch_id}: {section_volume:.4f} m³"
                    )
                else:
                    self.log_to_console(f"📏 Calculated volume for tree {section_tree_id}: {section_volume:.4f} m³")

                section_id += 1

            # Perform global ground proximity check only in non-branch mode
            if not is_branch_mode:
                self._check_global_ground_proximity_and_extrapolate()
            else:
                self.log_to_console("ℹ️ Branch mode: ground extrapolation disabled")

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
                
                section_data = {
                    'section_id': section['section_id'],
                    'branch_id': section.get('branch_id'),
                    'volume': section['volume'],
                    'point_color': section['point_color'],
                    'circle_color': section['circle_color'],
                    'num_points': len(section['points']),
                    'circle_data': section['circle_data']
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

            self.log_to_console(f"✅ All volume data saved to {self.volume_folder_path}")

        except Exception as e:
            self.log_to_console(f"❌ Error saving volume data: {str(e)}")
            raise

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
        summary += f"Volume folder: {self.volume_folder_path}\n"
        summary += f"Start time: {batch_start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"End time: {batch_end_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"Elapsed time: {elapsed_str}\n"
        summary += f"Average throughput: {average_trees_per_min:.2f} trees/min\n"
        
        if skipped_trees:
            summary += f"\nSkipped trees:\n"
            for tree_id, reason in skipped_trees:
                summary += f"  - Tree {tree_id}: {reason}\n"
        
        if self.accumulated_volume_sections:
            total_volume = sum(s['volume'] for s in self.accumulated_volume_sections)
            summary += f"\nTotal volume accumulated: {total_volume:.4f} m³\n"
        
        summary += f"{'='*60}\n"
        self.log_to_console(summary)

    def visualize_height_slices(self):
        """Visualize trunk divided into horizontal height slices for branch separation."""
        if self.current_tree_points is None:
            QMessageBox.warning(self, "Warning", "No trunk visualized. Please visualize a trunk first.")
            return

        try:
            # Get slice height in meters (convert from cm via spinner)
            slice_height_cm = self.slice_height_input.value()
            slice_height_m = slice_height_cm / 100.0
            
            self.log_to_console(f"\n{'='*60}")
            self.log_to_console(f"📏 Declustering trunk into {slice_height_cm} cm height slices...")
            self.log_to_console(f"{'='*60}")
            
            # Extract Z coordinates
            z_coords = self.current_tree_points[:, 2]
            min_z = np.min(z_coords)
            max_z = np.max(z_coords)
            trunk_height = max_z - min_z
            
            self.log_to_console(f"Trunk height range: {min_z:.2f}m to {max_z:.2f}m ({trunk_height:.2f}m total)")
            
            # Calculate slice boundaries
            slice_boundaries = np.arange(min_z, max_z + slice_height_m, slice_height_m)
            num_slices = len(slice_boundaries) - 1
            
            self.log_to_console(f"Total slices: {num_slices}")
            
            # Create color palette for slices
            # Use a rainbow-like palette with enough distinct colors
            import matplotlib.cm as cm
            import warnings
            
            # Suppress deprecation warning for get_cmap in matplotlib >= 3.7
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                if num_slices <= 10:
                    cmap = cm.get_cmap('tab10')
                elif num_slices <= 20:
                    cmap = cm.get_cmap('tab20')
                else:
                    cmap = cm.get_cmap('hsv')
            
            colors = cmap(np.linspace(0, 1, num_slices))
            
            # Clear current visualization
            self.plotter.clear()
            
            # Add each slice with unique color
            for i in range(num_slices):
                z_start = slice_boundaries[i]
                z_end = slice_boundaries[i + 1]
                
                # Create mask for points in this slice
                slice_mask = (z_coords >= z_start) & (z_coords < z_end)
                
                # For the last slice, include the upper boundary
                if i == num_slices - 1:
                    slice_mask = (z_coords >= z_start) & (z_coords <= z_end)
                
                slice_points = self.current_tree_points[slice_mask]
                
                if len(slice_points) > 0:
                    # Get color from colormap (already in [0, 1] range)
                    color = colors[i % len(colors)]
                    # PyVista accepts [0, 1] range colors directly, convert to native Python list
                    rgb_color = [float(color[0]), float(color[1]), float(color[2])]
                    
                    # Add slice to plotter
                    self.plotter.add_points(
                        slice_points,
                        color=rgb_color,
                        point_size=5,
                        name=f'Slice_{i}'
                    )
                    
                    # Log slice info
                    self.log_to_console(f"  Slice {i}: {z_start:.2f}m - {z_end:.2f}m | {len(slice_points)} points")
            
            # Add horizontal plane lines at slice boundaries for reference
            for i, z_val in enumerate(slice_boundaries):
                # Get min/max X,Y at this height to draw reference planes
                points_at_height = self.current_tree_points[
                    (z_coords >= z_val - 0.01) & (z_coords <= z_val + 0.01)
                ]
                if len(points_at_height) > 0:
                    x_min, x_max = np.min(points_at_height[:, 0]), np.max(points_at_height[:, 0])
                    y_min, y_max = np.min(points_at_height[:, 1]), np.max(points_at_height[:, 1])
                    
                    # Draw a small cross at the slice boundary center
                    center_x = (x_min + x_max) / 2
                    center_y = (y_min + y_max) / 2
                    
                    # Horizontal line
                    line_x = np.array([x_min, x_max])
                    line_y = np.array([center_y, center_y])
                    line_z = np.array([z_val, z_val])
                    
                    self.plotter.add_lines(
                        np.column_stack([line_x, line_y, line_z]),
                        color=(128, 128, 128),
                        width=1,
                        name=f'boundary_h_{i}'
                    )
            
            # Add legend if supported
            try:
                self.plotter.add_legend()
            except Exception as legend_error:
                self.log_to_console(f"(Legend display skipped: {str(legend_error)})")
            
            # Fit to screen and update
            self.plotter.reset_camera()
            self.plotter.update()
            
            self.log_to_console(f"✅ Height slice visualization complete!\n")
            
        except Exception as e:
            self.log_to_console(f"❌ Error visualizing height slices: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to visualize height slices:\n{str(e)}")

    def detect_branch_clusters_in_slices(self):
        """Detect individual branches using DBSCAN on radial coordinates within each height slice."""
        if self.current_tree_points is None:
            QMessageBox.warning(self, "Warning", "No trunk visualized. Please visualize a trunk first.")
            return
        
        try:
            self.log_to_console(f"\n{'='*60}")
            self.log_to_console(f"🌳 Detecting branches using radial DBSCAN clustering...")
            self.log_to_console(f"{'='*60}")
            
            # Get slice height parameters (same as visualization)
            slice_height_cm = self.slice_height_input.value()
            slice_height_m = slice_height_cm / 100.0
            
            # Extract coordinates
            points = self.current_tree_points
            z_coords = points[:, 2]
            min_z = np.min(z_coords)
            max_z = np.max(z_coords)
            
            # Calculate slice boundaries
            slice_boundaries = np.arange(min_z, max_z + slice_height_m, slice_height_m)
            num_slices = len(slice_boundaries) - 1
            
            self.log_to_console(f"📏 Slice height: {slice_height_cm}cm | Total slices: {num_slices}")
            
            # Initialize branch assignment array (-1 = noise, >=0 = branch_id)
            point_to_branch = np.full(len(points), -1, dtype=int)
            slice_cluster_map = {}  # Maps (slice_idx, local_cluster_id) to global branch_id
            next_branch_id = 0
            
            # Track clusters from previous slice for vertical connectivity
            prev_slice_clusters = {}  # Maps old_branch_id to centroid
            
            self.log_to_console(f"\n🔍 Running DBSCAN on each slice with eps=0.08m, min_samples=3...")
            
            # Process each slice
            for slice_idx in range(num_slices):
                z_start = slice_boundaries[slice_idx]
                z_end = slice_boundaries[slice_idx + 1]
                
                # Get points in this slice
                slice_mask = (z_coords >= z_start) & (z_coords < z_end)
                if slice_idx == num_slices - 1:
                    slice_mask = (z_coords >= z_start) & (z_coords <= z_end)
                
                slice_indices = np.where(slice_mask)[0]
                slice_points = points[slice_indices]
                
                if len(slice_points) < 3:
                    self.log_to_console(f"  Slice {slice_idx}: < 3 points, skipping")
                    continue
                
                # Calculate center of this slice
                center_x = np.mean(slice_points[:, 0])
                center_y = np.mean(slice_points[:, 1])
                
                # Get radial coordinates (relative to center)
                radial_coords = np.column_stack([
                    slice_points[:, 0] - center_x,
                    slice_points[:, 1] - center_y
                ])
                
                # Run DBSCAN on radial coordinates
                dbscan = DBSCAN(eps=0.08, min_samples=3)
                local_clusters = dbscan.fit_predict(radial_coords)
                
                num_clusters = len(set(local_clusters)) - (1 if -1 in local_clusters else 0)
                num_noise = np.sum(local_clusters == -1)
                
                self.log_to_console(f"  Slice {slice_idx}: {num_clusters} clusters, {num_noise} noise points")
                
                # Assign branch IDs with vertical tracking
                current_slice_clusters = {}
                for local_id in set(local_clusters):
                    if local_id == -1:  # Skip noise points
                        continue
                    
                    # Get points in this cluster
                    cluster_mask = local_clusters == local_id
                    cluster_indices = slice_indices[cluster_mask]
                    cluster_points = slice_points[cluster_mask]
                    
                    # Calculate cluster centroid
                    centroid = np.mean(cluster_points[:, :2], axis=0)
                    
                    # Check if this cluster connects to a cluster from previous slice
                    branch_id = None
                    if prev_slice_clusters:
                        # Find closest cluster in previous slice
                        min_dist = float('inf')
                        closest_prev_id = None
                        for prev_id, prev_centroid in prev_slice_clusters.items():
                            dist = np.linalg.norm(centroid - prev_centroid)
                            if dist < min_dist:
                                min_dist = dist
                                closest_prev_id = prev_id
                        
                        # If close enough (within 0.15m), merge with previous cluster
                        if closest_prev_id is not None and min_dist < 0.15:
                            branch_id = closest_prev_id
                            self.log_to_console(f"    Cluster {local_id}: Merged with branch {branch_id} (dist={min_dist:.3f}m)")
                    
                    if branch_id is None:
                        branch_id = next_branch_id
                        next_branch_id += 1
                        self.log_to_console(f"    Cluster {local_id}: New branch {branch_id}")
                    
                    # Assign branch ID to points
                    point_to_branch[cluster_indices] = branch_id
                    current_slice_clusters[branch_id] = centroid
                
                prev_slice_clusters = current_slice_clusters
            
            # Store branch assignment
            self.branch_assignment = point_to_branch
            
            self.log_to_console(f"\n✅ Branch detection complete!")
            self.log_to_console(f"   Total unique branches: {np.max(point_to_branch) + 1}")
            self.log_to_console(f"   Noise points: {np.sum(point_to_branch == -1)}")
            
            # Store branch assignment in memory for visualization and export
            # (LAS field modification may be handled during save operation)
            self.log_to_console(f"✅ Branch assignment stored in memory for visualization")
            
            # Visualize branches with different colors
            self.visualize_branches_from_assignment()
            
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
                    cmap = cm.get_cmap('tab10')
                elif num_branches <= 20:
                    cmap = cm.get_cmap('tab20')
                else:
                    cmap = cm.get_cmap('hsv')
            
            colors = cmap(np.linspace(0, 1, num_branches))
            
            # Calculate branch statistics for console output
            self.log_to_console(f"\n📋 BRANCH DETAILS:")
            self.log_to_console(f"{'Branch ID':<12} {'Size':<8} {'Min Z':<8} {'Max Z':<8} {'Height':<8} {'Δ Height':<12}")
            self.log_to_console(f"-" * 66)
            
            branch_info = {}
            branch_centroids = {}
            
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
                    
                    # Store for labeling
                    branch_info[branch_id] = {
                        'size': size,
                        'min_z': min_z,
                        'max_z': max_z,
                        'height': height,
                        'centroid': centroid
                    }
                    branch_centroids[branch_id] = centroid
                    
                    # Log statistics
                    self.log_to_console(
                        f"{branch_id:<12} {size:<8} {min_z:<8.2f} {max_z:<8.2f} "
                        f"{height:<8.2f} {max_z - min_z:<12.2f}"
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
                        self.plotter.add_point_labels(
                            np.array([centroid]),
                            [f'B{branch_id}'],
                            font_size=12,
                            text_color='white',
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
            
            # Update and display
            self.plotter.reset_camera()
            self.plotter.update()
            
            self.log_to_console(f"\n✅ Branch visualization complete!")
            self.log_to_console(f"   (Branch labels shown as 'B#' in 3D view)\n")
            
        except Exception as e:
            self.log_to_console(f"❌ Error visualizing branches: {str(e)}")
            import traceback
            self.log_to_console(traceback.format_exc())

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

    def visualize_dbh_circles(self):
        """
        Visualize circle fitting trajectory for DBH points in 3D.
        Shows only the circle fitting without component analysis.
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

            self.log_to_console(f"📏 Visualizing circle fitting for {len(dbh_points)} DBH points")

            # Visualize DBH points and circle fitting
            self._visualize_dbh_circles_only(dbh_points)

            QMessageBox.information(self, "DBH Circle Fitting",
                                  f"Successfully visualized circle fitting for {len(dbh_points)} DBH points")

        except Exception as e:
            QMessageBox.warning(self, "DBH Circle Visualization Error", f"Error visualizing DBH circles: {str(e)}")
            print(f"DBH circle visualization error: {e}")

    def _visualize_dbh_circles_only(self, dbh_points):
        """Visualize only the DBH points with circle fitting trajectory."""
        if self.plotter is None or len(dbh_points) == 0:
            return

        try:
            self.plotter.clear()

            # Show DBH points
            dbh_cloud = pv.PolyData(dbh_points)
            self.plotter.add_points(dbh_cloud, color='orange', point_size=3, opacity=0.7,
                                  name='dbh_points', label=f'DBH Points ({len(dbh_points)} pts)')

            # Add circle fitting
            self._add_dbh_circle_fitting(dbh_points)

            # Add information text
            min_z = np.min(dbh_points[:, 2])
            max_z = np.max(dbh_points[:, 2])
            height_range = max_z - min_z

            info_text = (f"DBH Circle Fitting Visualization\n"
                        f"Height Range: {min_z:.2f}m to {max_z:.2f}m\n"
                        f"Total Height: {height_range:.2f}m\n"
                        f"Total DBH Points: {len(dbh_points)}")

            self.plotter.add_text(info_text, position='upper_left', font_size=10, color='#FFFFFF')

            self.plotter.reset_camera()

        except Exception as e:
            self.log_to_console(f"❌ Error in DBH circles only visualization: {str(e)}")
            print(f"Error in _visualize_dbh_circles_only: {e}")

    def _add_dbh_circle_fitting_for_section(self, dbh_points, section_id, circle_color, avg_color, measurement_label="DBH"):
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
            self.plotter.add_mesh(centers_cloud, color='white', point_size=8,
                                render_points_as_spheres=True, opacity=1.0,
                                name=f'dbh_trajectory_section_{section_id}', label=f'Section {section_id} Trajectory ({len(circle_centers)} pts)')

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
                self.plotter.add_mesh(merged_individual, color=circle_color, opacity=0.3,
                                    name=f'dbh_individual_circles_section_{section_id}',
                                    label=f'Section {section_id} Individual Circles ({len(circle_centers)} circles)')

            # Add average circle at EVERY height level where individual circles exist
            self._add_average_dbh_circles_for_section(circle_centers, final_center, final_radius, section_id, avg_color)

            self.log_to_console(f"📊 Added section {section_id} with {len(circle_centers)} {measurement_label} circles")

            # Extract DBH at 1.3m from min_z using the AVERAGE radius (same as red circles)
            dbh_at_1_3m = None
            dbh_center_at_1_3m = None
            dbh_z_at_1_3m = None
            target_height = 1.3  # Standard DBH height
            
            # Check if 1.3m height is within the section's range
            if len(circle_heights) > 0 and height_range >= target_height:
                # Use the global average radius (same as red circles) for DBH
                avg_radius_at_1_3m = final_radius  # Use the average radius from all circles
                dbh_at_1_3m = avg_radius_at_1_3m * 2  # Diameter
                
                # Use average center for visualization
                dbh_center_at_1_3m = np.array([final_center[0], final_center[1], min_z + target_height])
                dbh_z_at_1_3m = min_z + target_height
                
                self.log_to_console(f"🌳 {measurement_label} at 1.3m from min_z: {dbh_at_1_3m*100:.1f} cm (avg radius: {avg_radius_at_1_3m*100:.1f} cm)")
                
                # Visualize DBH circle at 1.3m with green color
                dbh_circle = pv.Circle(radius=float(avg_radius_at_1_3m), resolution=64)
                dbh_circle.translate([float(dbh_center_at_1_3m[0]), float(dbh_center_at_1_3m[1]), float(dbh_z_at_1_3m)], inplace=True)
                self.plotter.add_mesh(dbh_circle, color='green', opacity=0.8, line_width=3,
                                    style='wireframe',
                                    name=f'dbh_1_3m_circle_section_{section_id}',
                                    label=f'Section {section_id} {measurement_label} @1.3m: {dbh_at_1_3m*100:.1f}cm')
                
                # Add a horizontal plane at 1.3m to indicate DBH measurement level
                plane_size = float(avg_radius_at_1_3m * 2.5)  # Slightly larger than diameter
                dbh_plane = pv.Plane(center=[float(dbh_center_at_1_3m[0]), float(dbh_center_at_1_3m[1]), float(dbh_z_at_1_3m)],
                                    direction=[0, 0, 1], i_size=plane_size, j_size=plane_size)
                self.plotter.add_mesh(dbh_plane, color='green', opacity=0.2,
                                    name=f'dbh_1_3m_plane_section_{section_id}',
                                    label=f'Section {section_id} {measurement_label} Plane @1.3m')
                
                # Add text label for DBH
                dbh_label_pos = [float(dbh_center_at_1_3m[0] + plane_size/2), float(dbh_center_at_1_3m[1]), float(dbh_z_at_1_3m)]
                self.plotter.add_point_labels([dbh_label_pos], [f'{measurement_label}: {dbh_at_1_3m*100:.1f}cm'],
                                             font_size=12, text_color='green', point_size=0,
                                             name=f'dbh_1_3m_label_section_{section_id}')
            else:
                self.log_to_console(f"⚠️ Section height range ({height_range:.2f}m) doesn't reach 1.3m for {measurement_label} measurement")

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
                'dbh_z_at_1_3m': dbh_z_at_1_3m
            }
        else:
            self.log_to_console(f"⚠️ No valid circles found for section {section_id}")
            return {'circles': [], 'avg_radius': 0.0, 'height_range': 0.0, 'dbh_at_1_3m': None}

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

        # Extrapolate downward
        extrapolated_circles = []
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

            # Add visualization for extrapolated circle
            circle = pv.Circle(radius=last_radius, resolution=32)
            circle.translate(extrapolated_center, inplace=True)
            self.plotter.add_mesh(circle, color=circle_color, opacity=0.3,
                                name=f'dbh_circle_section_{section_id}_extrapolated_{i}',
                                label=f'Section {section_id} Extrapolated Z={current_z:.1f}m')

            current_z -= step

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
            'max_z': new_max_z
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
                                label=f'Global Extrapolated Circles ({len(extrapolated_circle_meshes)} circles)')

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
                'circle_data': extrapolated_section_data
            }
            
            self.accumulated_volume_sections.append(global_section_info)
            
            self.log_to_console(f"✅ Added global extrapolated section with {len(extrapolated_circles)} circles")
            self.log_to_console(f"📊 Global extrapolation completed - height range: {global_height_range:.2f}m")
            
            # Log last extrapolated circle height and total cylinder height
            self.log_to_console(f"📏 Last extrapolated circle at Z: {extrapolation_stop_level:.2f}m")
            
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

    def _add_average_dbh_circles_for_section(self, circle_centers, avg_center, avg_radius, section_id, avg_color):
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
                self.plotter.add_mesh(merged_average, color=avg_color, line_width=3, opacity=0.9,
                                    name=f'dbh_avg_circles_section_{section_id}',
                                    label=f'Section {section_id} Avg Circles ({len(circle_centers)} circles)')

            # Add a single center marker for the average center trajectory
            centers_array = np.array([[center[0], center[1], center[2]] for center in circle_centers])
            avg_centers_cloud = pv.PolyData(centers_array)
            self.plotter.add_mesh(avg_centers_cloud, color=avg_color, point_size=6,
                                render_points_as_spheres=True, opacity=1.0,
                                name=f'dbh_avg_trajectory_section_{section_id}', label=f'Section {section_id} Avg Trajectory ({len(circle_centers)} pts)')

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
        if self.selected_point_indices is None or len(self.selected_point_indices) == 0:
            QMessageBox.warning(self, "No Selection", "No points selected. Please use the polygon selection tool first.")
            return

        if not hasattr(self, 'current_tree_points') or self.current_tree_points is None:
            QMessageBox.warning(self, "No Tree Points", "No tree points available. Please visualize a tree first.")
            return

        try:
            volume_groups, is_branch_mode = self._get_volume_groups_from_selection()
            if not volume_groups:
                QMessageBox.warning(self, "No Valid Groups", "No valid point groups found for volume calculation.")
                return
            
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
            
            # Find the maximum section_id for this tree to ensure proper numbering
            existing_section_ids = [int(s['section_id']) for s in self.accumulated_volume_sections if s['tree_id'] == section_tree_id and str(s['section_id']).isdigit()]
            section_id = max(existing_section_ids) + 1 if existing_section_ids else 1

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

                for group_branch_id, _, group_points in volume_groups:
                    point_color = section_colors[(section_id - 1) % len(section_colors)]
                    circle_color = section_colors[(section_id - 1) % len(section_colors)]
                    branch_suffix = f" | B{group_branch_id}" if group_branch_id is not None else ""

                    # Show selected points for this section
                    selected_cloud = pv.PolyData(group_points)
                    self.plotter.add_points(
                        selected_cloud,
                        color=point_color,
                        point_size=4,
                        opacity=0.6,
                        name=f'volume_section_{section_id}_points',
                        label=f'Section {section_id}{branch_suffix} Points ({len(group_points)} pts)'
                    )

                    # Add circle fitting to selected points with section-specific naming
                    measurement_label = "Diameter" if is_branch_mode else "DBH"
                    section_data = self._add_dbh_circle_fitting_for_section(
                        group_points,
                        section_id,
                        circle_color,
                        avg_color,
                        measurement_label=measurement_label
                    )

                    # Calculate volume for this section
                    section_volume = self._calculate_section_volume(section_data)

                    # Store this section's data including volume
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
                        if diameter_cm is not None:
                            section_metric_values_cm.append(diameter_cm)
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
                            f"   ↳ DBH @1.3m | Section {section_id}: {metric_text}"
                        )

                    section_id += 1

                # Perform global ground proximity check only in non-branch mode
                if not is_branch_mode:
                    self._check_global_ground_proximity_and_extrapolate()
                else:
                    self.log_to_console("ℹ️ Branch mode: ground extrapolation disabled")

                # Debug: Log accumulated sections count after adding
                self.log_to_console(f"✅ Total accumulated sections now: {len(self.accumulated_volume_sections)}")

                # Update info text to show accumulated results
                total_sections = len(self.accumulated_volume_sections)
                total_points = sum(len(section['points']) for section in self.accumulated_volume_sections)
                total_volume = sum(section['volume'] for section in self.accumulated_volume_sections)

                # Show measurement text based on mode
                if is_branch_mode:
                    avg_radius = last_section_data.get('avg_radius') if last_section_data else None
                    diameter_cm = (avg_radius * 2 * 100) if avg_radius else None
                    dbh_text = f"\nLast Diameter (section avg): {diameter_cm:.1f} cm" if diameter_cm else "\nLast Diameter (section avg): N/A"
                else:
                    dbh_at_1_3m = last_section_data.get('dbh_at_1_3m') if last_section_data else None
                    dbh_text = f"\nLast DBH @1.3m: {dbh_at_1_3m*100:.1f} cm" if dbh_at_1_3m else "\nLast DBH @1.3m: N/A"

                metric_summary_text = ""
                if section_metric_values_cm:
                    metric_name = "Diameter (all sections)" if is_branch_mode else "DBH @1.3m (all sections)"
                    metric_summary_text = (
                        f"\n{metric_name}: min {np.min(section_metric_values_cm):.1f}, "
                        f"max {np.max(section_metric_values_cm):.1f}, avg {np.mean(section_metric_values_cm):.1f} cm"
                    )

                mode_text = "Mode: Branch-wise" if is_branch_mode else "Mode: Standard"

                info_text = (f"Accumulated Volume Calculation\n"
                            f"{mode_text}\n"
                            f"Sections: {total_sections}\n"
                            f"Total Points: {total_points}\n"
                            f"Total Volume: {total_volume:.4f} m³"
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

                # Ensure plotter updates to show all accumulated sections
                self.plotter.update()
                # NOTE: Don't reset_camera() here - preserve user's current view of the tree

            # Enable clear button now that we have results
            self.clear_volume_button.setEnabled(True)
            self.save_volume_button.setEnabled(True)

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
            return default_group, False

        return grouped, True

    def clear_accumulated_volume(self):
        """
        Clear all accumulated volume calculation results and reset the visualization.
        """
        try:
            # Clear accumulated data
            self.accumulated_volume_sections = []
            self.trees_with_volume_data.clear()
            
            # Refresh tree list colors
            self._refresh_tree_list_colors()
            
            # Clear volume-related actors from plotter
            if self.plotter is not None:
                # Remove all volume-related and DBH-related meshes and actors
                actors_to_remove = []
                for actor_name in self.plotter.actors:
                    if ('volume' in actor_name.lower() or 
                        'dbh_' in actor_name.lower() or 
                        'trajectory' in actor_name.lower() or 
                        'circle' in actor_name.lower()):
                        actors_to_remove.append(actor_name)
                
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
                
                self.plotter.update()
            
            # Disable clear button
            self.clear_volume_button.setEnabled(False)
            
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
                
                section_data = {
                    'section_id': section['section_id'],
                    'branch_id': section.get('branch_id'),
                    'volume': section['volume'],
                    'point_color': section['point_color'],
                    'circle_color': section['circle_color'],
                    'num_points': len(section['points']),
                    'circle_data': section['circle_data']
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

            # Get save folder - use volume folder if set, otherwise ask user
            if self.volume_folder_path:
                folder = self.volume_folder_path
                self.log_to_console(f"💾 Using configured volume folder: {folder}")
            else:
                folder = QFileDialog.getExistingDirectory(
                    self, "Select Folder to Save Tree Data",
                    ""  # Default directory
                )

            if folder:
                import json
                import os
                
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
            # Get folder containing tree files
            folder = QFileDialog.getExistingDirectory(
                self, "Select Folder Containing Tree Data Files",
                ""  # Default directory
            )

            if not folder:
                return

            import json
            import os
            import glob

            # Find all tree_*.json files in the folder
            tree_files = sorted(glob.glob(os.path.join(folder, "tree_*.json")))
            
            if not tree_files:
                QMessageBox.warning(self, "No Tree Files", f"No tree_*.json files found in {folder}")
                return

            self.log_to_console(f"📂 Found {len(tree_files)} tree files in selected folder. Loading all files...")

            # Clear existing volume data if any
            if self.accumulated_volume_sections:
                reply = QMessageBox.question(self, "Clear Existing Data",
                                           "Loading new volume data will clear existing calculations. Continue?",
                                           QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    return
                self.clear_accumulated_volume()

            # Load data from all tree files
            self.accumulated_volume_sections = []
            loaded_trees = 0
            total_sections = 0

            for tree_file in tree_files:
                try:
                    with open(tree_file, 'r') as f:
                        tree_data = json.load(f)

                    # Extract tree_id from filename
                    filename = os.path.basename(tree_file)
                    tree_id = filename.replace('tree_', '').replace('.json', '')

                    # Validate data structure
                    if 'sections' not in tree_data:
                        self.log_to_console(f"⚠️ Skipping {filename}: no sections data")
                        continue

                    # Load sections for this tree
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
                                'branch_id': section_data.get('branch_id'),
                                'volume': section_data['volume'],
                                'point_color': section_data['point_color'],
                                'circle_color': section_data['circle_color'],
                                'points': np.array([]),  # Empty array since we don't save point data
                                'circle_data': section_data['circle_data']
                            }
                            self.accumulated_volume_sections.append(section_info)
                            total_sections += 1
                        except (ValueError, TypeError) as e:
                            self.log_to_console(f"⚠️ Skipping section with invalid section_id '{section_data.get('section_id', 'unknown')}': {e}")
                            continue

                    loaded_trees += 1
                    self.log_to_console(f"✅ Loaded tree {tree_id} with {len(tree_data['sections'])} sections")

                except Exception as e:
                    self.log_to_console(f"⚠️ Error loading {tree_file}: {e}")
                    continue

            # Track which trees have volume data for UI coloring
            self.trees_with_volume_data = set(s['tree_id'] for s in self.accumulated_volume_sections)
            
            # DEBUG: Print summary of loaded trees
            self.log_to_console(f"🔍 DEBUG: Found {len(self.trees_with_volume_data)} trees with volume data: {sorted(self.trees_with_volume_data)}")
            
            # Refresh tree list colors to show which trees have volume data
            self._refresh_tree_list_colors()
            
            # Update UI
            self.clear_volume_button.setEnabled(True)
            self.save_volume_button.setEnabled(True)

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
            for section_info in self.accumulated_volume_sections:
                self._restore_section_visualization(section_info)
            self.log_to_console(f"✅ Visualization restoration complete")
            
            QMessageBox.information(self, "Load Successful",
                                  f"Volume data loaded from {len(tree_files)} files in {folder}\n"
                                  f"Trees: {total_trees}\n"
                                  f"Sections: {total_sections}\n"
                                  f"Total volume: {total_volume:.4f} m³")

        except Exception as e:
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

                # Create individual circles and merge into single mesh for better performance
                if len(circle_data['circles']) > 0:
                    individual_circles = []
                    for center, radius in circle_data['circles']:
                        circle = pv.Circle(radius=radius, resolution=32)
                        circle.translate([center[0], center[1], center[2]], inplace=True)
                        individual_circles.append(circle)

                    # Merge all individual circles into single mesh
                    merged_individual = individual_circles[0].copy()
                    for circle in individual_circles[1:]:
                        merged_individual = merged_individual + circle

                    self.plotter.add_mesh(merged_individual, color=circle_color, style='wireframe', line_width=2, opacity=0.9,
                                        name=f'dbh_individual_circles_tree_{tree_id}_section_{section_id}',
                                        label=f'Tree {tree_id} - Section {section_id} Individual Circles ({len(circle_data["circles"])} circles)')

                # Recreate average circles if data available
                if 'avg_radius' in circle_data and 'avg_center' in circle_data and circle_data['avg_radius'] > 0:
                    avg_color = 'red'
                    avg_center = circle_data['avg_center']

                    # Create average circles and merge into single mesh for better performance
                    avg_circles = []
                    for center, _ in circle_data['circles']:
                        height_z = center[2]
                        avg_circle = pv.Circle(radius=circle_data['avg_radius'], resolution=32)
                        avg_circle.translate([center[0], center[1], height_z], inplace=True)
                        avg_circles.append(avg_circle)

                    # Merge all average circles into single mesh
                    merged_average = avg_circles[0].copy()
                    for circle in avg_circles[1:]:
                        merged_average = merged_average + circle

                    self.plotter.add_mesh(merged_average, color=avg_color, style='wireframe', line_width=3, opacity=0.9,
                                        name=f'dbh_avg_circles_tree_{tree_id}_section_{section_id}',
                                        label=f'Tree {tree_id} - Section {section_id} Avg Circles ({len(circle_data["circles"])} circles)')

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

    def get_visualized_tree_ids(self):
        """Get the tree IDs that are currently being visualized.
        
        Returns:
            Set of tree IDs currently visualized, or empty set if none.
        """
        if not hasattr(self, 'current_tree_id') or self.current_tree_id is None:
            return set()
        
        tree_id_str = str(self.current_tree_id)
        
        # Handle single tree case (just a number)
        try:
            # Try to convert directly to int
            tree_id = int(tree_id_str)
            return {str(tree_id)}
        except ValueError:
            pass
        
        # Handle multiple trees case: "Multiple (1, 3, 4)" or "Multiple (1)"
        if tree_id_str.startswith("Multiple (") and tree_id_str.endswith(")"):
            # Extract the part between parentheses
            ids_part = tree_id_str[10:-1]  # Remove "Multiple (" and ")"
            if ids_part:
                # Split by comma and strip whitespace
                id_strings = [id_str.strip() for id_str in ids_part.split(",")]
                # Convert to set of strings
                return set(id_strings)
        
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
                                name='dbh_trajectory', label=f'DBH Trajectory ({len(circle_centers)} pts)')

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
                                    name=f'dbh_circle_{i}', label=f'DBH Circle Z={center[2]:.1f}m')

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
                                    name=f'dbh_avg_circle_{i}', label=f'DBH Avg Circle Z={height_z:.1f}m')

            # Add a single center marker for the average center trajectory
            centers_array = np.array([[avg_center[0], avg_center[1], center[2]] for center in circle_centers])
            avg_centers_cloud = pv.PolyData(centers_array)
            self.plotter.add_mesh(avg_centers_cloud, color='red', point_size=6,
                                render_points_as_spheres=True, opacity=1.0,
                                name='dbh_avg_trajectory', label=f'DBH Avg Trajectory ({len(circle_centers)} pts)')

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


    def select_volume_folder(self):
        """Open folder selection dialog for volume data folder."""
        try:
            # Open folder selection dialog
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Volume Data Folder",
                self.volume_folder_path if hasattr(self, 'volume_folder_path') and self.volume_folder_path else ""
            )

            if folder_path:  # User selected a folder
                self.volume_folder_path = folder_path
                self.volume_folder_label.setText(f"Volume Folder: {os.path.basename(folder_path)}")
                self.log_to_console(f"📁 Selected volume folder: {folder_path}")

                # Scan the folder for volume data files
                self.scan_volume_folder_for_trees()

                # Update tree list colors based on volume data availability
                self.check_volume_folder_for_trees()
                self._refresh_tree_list_colors()

            else:  # User cancelled
                self.log_to_console("📁 Volume folder selection cancelled")

        except Exception as e:
            QMessageBox.warning(self, "Folder Selection Error", f"Error selecting volume folder: {str(e)}")
            self.log_to_console(f"❌ Error selecting volume folder: {str(e)}")


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
