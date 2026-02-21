#!/usr/bin/env python3
"""
Modern Tree Visualization GUI using PyQt6 and PyVista.
Allows loading LAS files, selecting tree IDs from 'itc' scalar field, and visualizing individual trees.
"""

import sys
import os
import numpy as np
import laspy
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLineEdit, QLabel, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QFrame, QComboBox, QCheckBox,
    QGroupBox, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
from sklearn.cluster import DBSCAN


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
                font-size: 14px;
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


class TreeVisualizerGUI(QMainWindow):
    """Main window for tree visualization GUI."""

    def __init__(self):
        super().__init__()
        self.las_data = None
        self.unique_itc_values = []
        self.current_tree_points = None
        self.current_tree_id = None
        self.current_mask = None
        self.plotter = None
        self.init_ui()
        self.apply_stylesheet()

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
        self.setWindowTitle("Tree Visualizer - TreeAIBox")
        self.setGeometry(100, 100, 1400, 900)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Create sidebar
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar, 1)

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
        
        self.plotter = QtInteractor()
        self.plotter.set_background('#2e2e2e')  # Lighter background color
        plotter_layout.addWidget(self.plotter.interactor)

        main_layout.addWidget(plotter_frame, 4)

        # Initialize empty plot
        self.clear_plot()

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

        # Visualization controls section
        viz_group = QGroupBox("Visualization Controls")
        viz_layout = QVBoxLayout(viz_group)
        viz_layout.setSpacing(12)

        # Tree ID selection
        id_layout = QVBoxLayout()
        id_label = QLabel("Tree ID:")
        id_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        self.id_combo = QComboBox()
        self.id_combo.addItem("Select tree...")
        self.id_combo.setMinimumHeight(30)
        id_layout.addWidget(id_label)
        id_layout.addWidget(self.id_combo)
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

        # Filter option
        self.filter_checkbox = QCheckBox("Filter tree points (treefilter=2)")
        self.filter_checkbox.setChecked(True)
        self.filter_checkbox.setStyleSheet("margin-top: 5px;")
        viz_layout.addWidget(self.filter_checkbox)

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

        self.split_button = ModernButton("Split Detection")
        self.split_button.clicked.connect(self.analyze_splits)
        self.split_button.setEnabled(False)
        button_layout.addWidget(self.split_button)

        self.clear_button = ModernButton("Clear View")
        self.clear_button.clicked.connect(self.clear_plot)
        button_layout.addWidget(self.clear_button)

        # Remove the reset view button since clear_plot already resets the camera
        # self.reset_view_button = ModernButton("Reset View")
        # self.reset_view_button.clicked.connect(self.reset_view)
        # button_layout.addWidget(self.reset_view_button)
        
        viz_layout.addLayout(button_layout)

        layout.addWidget(viz_group)

        # Progress bar
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
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress

            # Load LAS file
            self.las_data = laspy.read(file_path)
            self.file_label.setText(f"Loaded: {os.path.basename(file_path)}")

            # Check for ITC field
            if 'itc' not in self.las_data.point_format.dimension_names:
                QMessageBox.warning(self, "Warning",
                                  "No 'itc' scalar field found in the LAS file.")
                self.las_data = None
                return

            # Check for stemoff field for trunk visualization
            has_stemoff = 'stemoff' in self.las_data.point_format.dimension_names

            # Extract unique ITC values
            itc_values = np.array(self.las_data['itc'])
            self.unique_itc_values = np.unique(itc_values[itc_values > 0]).astype(int)  # Exclude 0 (likely unassigned) and convert to int

            # Populate tree combo box
            self.id_combo.clear()
            self.id_combo.addItem("Select tree...")
            for value in sorted(self.unique_itc_values):
                self.id_combo.addItem(str(value))

            # Populate color field combo box
            available_fields = list(self.las_data.point_format.dimension_names)
            color_fields = [field for field in available_fields
                           if field not in ['x', 'y', 'z'] and field != 'itc']  # Exclude coordinates and itc

            self.color_combo.clear()
            self.color_combo.addItem("Default (green)")
            for field in sorted(color_fields):
                self.color_combo.addItem(field)

            self.visualize_button.setEnabled(True)
            self.trunk_button.setEnabled(has_stemoff)

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
            return

        if color_field == "Default (green)":
            # Use default green color
            self.plotter.clear()
            point_cloud = pv.PolyData(self.current_tree_points)
            self.plotter.add_points(point_cloud, color='#4CAF50', point_size=2, render_points_as_spheres=False)
        else:
            # Color by the selected scalar field
            try:
                # Get the color values using the current mask
                color_values = np.array(self.las_data[color_field])[self.current_mask]

                self.plotter.clear()
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, scalars=color_values, point_size=2, render_points_as_spheres=False, cmap='viridis')
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Failed to color by field '{color_field}': {str(e)}")
                return

        # Reset camera and add title
        self.plotter.reset_camera()
        num_points = len(self.current_tree_points)
        self.plotter.add_text(f"Tree ID: {self.current_tree_id} ({num_points} points) - Color: {color_field}",
                             position='upper_left', font_size=12, color='#FFFFFF')
        self.plotter.update()

    def visualize_tree(self):
        """Visualize the selected tree using PyVista."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if not self.plotter:
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        tree_id_text = self.id_combo.currentText()
        if tree_id_text == "Select tree...":
            QMessageBox.warning(self, "Warning", "Please select a tree ID from the dropdown.")
            return

        try:
            tree_id = int(tree_id_text)
        except ValueError:
            QMessageBox.warning(self, "Warning", "Invalid tree ID selected.")
            return

        if tree_id not in self.unique_itc_values:
            QMessageBox.warning(self, "Warning", f"Tree ID {tree_id} not found in the data.")
            return

        # Extract points for this tree
        itc_values = np.array(self.las_data['itc'])
        mask = itc_values == tree_id

        # Apply treefilter if enabled
        if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
            treefilter_values = np.array(self.las_data['treefilter'])
            mask = mask & (treefilter_values == 2)

        if not np.any(mask):
            QMessageBox.warning(self, "Warning", f"No points found for tree ID {tree_id}.")
            return

        points = np.column_stack([
            np.array(self.las_data.x)[mask],
            np.array(self.las_data.y)[mask],
            np.array(self.las_data.z)[mask]
        ])

        # Store current tree data for recoloring
        self.current_tree_points = points
        self.current_tree_id = tree_id
        self.current_mask = mask

        # Visualize with current color field
        self.update_tree_colors(self.color_combo.currentText())

        # Disable split detection for full tree visualization
        self.split_button.setEnabled(False)

    def visualize_trunk(self):
        """Visualize the trunk of the selected tree using PyVista (stemoff != 0)."""
        if self.las_data is None:
            QMessageBox.warning(self, "Warning", "No LAS file loaded.")
            return

        if not self.plotter:
            QMessageBox.warning(self, "Warning", "3D viewer not initialized.")
            return

        tree_id_text = self.id_combo.currentText()
        if tree_id_text == "Select tree...":
            QMessageBox.warning(self, "Warning", "Please select a tree ID from the dropdown.")
            return

        try:
            tree_id = int(tree_id_text)
        except ValueError:
            QMessageBox.warning(self, "Warning", "Invalid tree ID selected.")
            return

        if tree_id not in self.unique_itc_values:
            QMessageBox.warning(self, "Warning", f"Tree ID {tree_id} not found in the data.")
            return

        # Check if stemoff field exists
        if 'stemoff' not in self.las_data.point_format.dimension_names:
            QMessageBox.warning(self, "Warning", "No 'stemoff' scalar field found in the LAS file.")
            return

        # Extract points for this tree where stemoff != 0
        itc_values = np.array(self.las_data['itc'])
        stemoff_values = np.array(self.las_data['stemoff'])
        mask = (itc_values == tree_id) & (stemoff_values != 0)

        # Apply treefilter if enabled
        if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
            treefilter_values = np.array(self.las_data['treefilter'])
            mask = mask & (treefilter_values == 2)

        if not np.any(mask):
            QMessageBox.warning(self, "Warning", f"No trunk points found for tree ID {tree_id}.")
            return

        points = np.column_stack([
            np.array(self.las_data.x)[mask],
            np.array(self.las_data.y)[mask],
            np.array(self.las_data.z)[mask]
        ])

        # Calculate bounding box height and set max height input
        z_coords = points[:, 2]  # Z coordinates
        trunk_height = np.max(z_coords) - np.min(z_coords)
        self.max_height_input.setText(f"{trunk_height:.2f}")

        # Store current tree data for recoloring
        self.current_tree_points = points
        self.current_tree_id = tree_id
        self.current_mask = mask

        # Switch to default green for trunk visualization
        self.color_combo.setCurrentText("Default (green)")
        # Visualize with current color field
        self.update_tree_colors(self.color_combo.currentText())

        # Enable split detection button
        self.split_button.setEnabled(True)

    def analyze_splits(self):
        """Analyze split detection on the currently visualized trunk points."""
        if self.current_tree_points is None or len(self.current_tree_points) == 0:
            QMessageBox.warning(self, "Warning", "No trunk points available for split analysis.")
            return

        try:
            # Run split detection analysis on trunk points
            results = self.analyze_trunk_splits(self.current_tree_points)

            # Visualize split planes
            self.visualize_split_planes(results)

            # Display results in a message box
            self.show_split_results(results)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Split analysis failed: {str(e)}")

    def analyze_trunk_splits(self, trunk_points: np.ndarray):
        """
        Analyze split detection on trunk points using height-wise clustering.

        Args:
            trunk_points: Nx3 array of trunk points

        Returns:
            List of analysis results for each height
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
            QMessageBox.warning(self, "Invalid Parameters", 
                              f"Please enter valid values for split detection parameters.\nError: {e}")
            return

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
                    'cluster_sizes': []
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

            # Get cluster sizes
            cluster_sizes = []
            for label in set(labels):
                if label != -1:
                    cluster_sizes.append(np.sum(labels == label))

            results.append({
                'height': height,
                'n_points': len(plane_points),
                'n_clusters': n_clusters,
                'n_noise': n_noise,
                'cluster_sizes': cluster_sizes
            })

        return results

    def show_split_results(self, results):
        """Display split analysis results in a dialog."""
        if not results:
            QMessageBox.information(self, "Split Analysis", "No analysis results available.")
            return

        # Find branching height (first height where clusters >= 2)
        branching_height = None
        for i, result in enumerate(results):
            if result['n_clusters'] >= 2 and (i == 0 or results[i-1]['n_clusters'] < 2):
                branching_height = result['height']
                break

        # Create results text
        result_text = "Trunk Split Detection Results\n"
        result_text += "=" * 40 + "\n\n"

        # Add parameters used
        result_text += "Parameters Used:\n"
        result_text += f"  Max Height: {self.max_height_input.text()}m\n"
        result_text += f"  Step: {self.step_input.text()}m\n"
        result_text += f"  Thickness: {self.thickness_input.text()}m\n"
        result_text += f"  Min Points: {self.min_points_input.text()}\n"
        result_text += f"  DBSCAN eps: 0.2m\n\n"

        if branching_height is not None:
            result_text += f"🔍 BRANCHING DETECTED at {branching_height:.1f}m above base!\n\n"
        else:
            result_text += "✅ No branching detected within analyzed height range.\n\n"

        result_text += "Height Analysis:\n"
        result_text += "-" * 40 + "\n"
        result_text += f"{'Height':<8} {'Points':<8} {'Clusters':<10} {'Noise':<8} {'Sizes'}\n"
        result_text += "-" * 40 + "\n"

        for result in results:
            sizes_str = str(result.get('cluster_sizes', [])) if result.get('cluster_sizes') else 'N/A'
            result_text += f"{result['height']:<8.1f} {result['n_points']:<8} {result['n_clusters']:<10} {result['n_noise']:<8} {sizes_str}\n"

        # Show results in message box
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Trunk Split Analysis")
        msg_box.setText(result_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

        # Make the message box wider to accommodate the table
        msg_box.setStyleSheet("QLabel{min-width: 500px;}")

        msg_box.exec()

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

                # Add plane to plotter with semi-transparent red color
                color = '#FF4444' if i % 2 == 0 else '#FF8844'  # Alternate colors for multiple splits
                self.plotter.add_mesh(plane, color=color, opacity=0.7,
                                    label=f'Split at {height:.1f}m')

                # Add height label
                self.plotter.add_point_labels([(center_x + radius + 0.1, center_y, plane_z)],
                                            [f'{height:.1f}m'], font_size=10, text_color='white',
                                            point_color=color, point_size=5)

        # Update the plot
        self.plotter.update()

    def clear_plot(self):
        """Clear the 3D visualization and reset camera."""
        if self.plotter:
            self.plotter.clear()
            self.plotter.reset_camera()
            self.plotter.update()
        
        # Disable split detection when clearing
        self.split_button.setEnabled(False)


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("Tree Visualizer")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("TreeAIBox")

    # Create and show main window
    window = TreeVisualizerGUI()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
