#!/usr/bin/env python3
"""
Tree Visualization GUI using PyQt6 and PyVista.
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
    QMessageBox, QProgressBar, QSplitter, QFrame, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


class TreeVisualizerGUI(QMainWindow):
    """Main window for tree visualization GUI."""

    def __init__(self):
        super().__init__()
        self.las_data = None
        self.unique_itc_values = []
        self.current_tree_points = None
        self.current_tree_id = None
        self.plotter = None
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Tree Visualizer - TreeAIBox")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)

        # Create sidebar
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar, 1)  # Fixed width

        # Create main content area - 3D visualization
        plotter_frame = QFrame()
        plotter_frame.setFrameStyle(QFrame.Shape.Box)
        plotter_frame.setLineWidth(2)
        plotter_frame.setMidLineWidth(1)
        plotter_frame.setFrameShadow(QFrame.Shadow.Sunken)
        plotter_frame.setStyleSheet("QFrame { border: 2px dashed #888; border-radius: 4px; }")

        plotter_layout = QVBoxLayout(plotter_frame)
        self.plotter = QtInteractor()
        self.plotter.set_background('dimgray')
        plotter_layout.addWidget(self.plotter.interactor)

        main_layout.addWidget(plotter_frame, 3)

        # Initialize empty plot
        self.clear_plot()

    def create_sidebar(self):
        """Create the sidebar with file loading and visualization controls."""
        sidebar = QWidget()
        sidebar.setMaximumWidth(300)
        sidebar.setMinimumWidth(250)
        layout = QVBoxLayout(sidebar)

        # File loading section
        file_group = QFrame()
        file_group.setFrameStyle(QFrame.Shape.Box)
        file_layout = QVBoxLayout(file_group)

        file_title = QLabel("File Management")
        file_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        file_layout.addWidget(file_title)

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(self.file_label)

        self.load_button = QPushButton("Load LAS File")
        self.load_button.clicked.connect(self.load_las_file)
        file_layout.addWidget(self.load_button)

        layout.addWidget(file_group)

        # Visualization controls section
        viz_group = QFrame()
        viz_group.setFrameStyle(QFrame.Shape.Box)
        viz_layout = QVBoxLayout(viz_group)

        viz_title = QLabel("Visualization Controls")
        viz_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        viz_layout.addWidget(viz_title)

        # Tree ID selection (always based on 'itc' field)
        id_layout = QHBoxLayout()
        id_label = QLabel("Tree ID:")
        self.id_combo = QComboBox()
        self.id_combo.addItem("Select tree...")
        id_layout.addWidget(id_label)
        id_layout.addWidget(self.id_combo)
        viz_layout.addLayout(id_layout)

        # Scalar field for coloring (after tree is visualized)
        color_layout = QHBoxLayout()
        color_label = QLabel("Color by:")
        self.color_combo = QComboBox()
        self.color_combo.addItem("Default (green)")
        self.color_combo.currentTextChanged.connect(self.update_tree_colors)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        viz_layout.addLayout(color_layout)

        # Filter option
        self.filter_checkbox = QCheckBox("Filter tree points (treefilter=1)")
        self.filter_checkbox.setChecked(True)  # Default to filter
        viz_layout.addWidget(self.filter_checkbox)

        # Control buttons
        self.visualize_button = QPushButton("Visualize Tree")
        self.visualize_button.clicked.connect(self.visualize_tree)
        self.visualize_button.setEnabled(False)
        viz_layout.addWidget(self.visualize_button)

        self.clear_button = QPushButton("Clear View")
        self.clear_button.clicked.connect(self.clear_plot)
        viz_layout.addWidget(self.clear_button)

        self.reset_view_button = QPushButton("Reset View")
        self.reset_view_button.clicked.connect(self.reset_view)
        viz_layout.addWidget(self.reset_view_button)

        layout.addWidget(viz_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        return sidebar

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

            QMessageBox.information(self, "Success",
                                  f"Loaded {len(self.unique_itc_values)} unique tree IDs from {len(self.las_data.points)} points.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load LAS file:\n{str(e)}")
            self.las_data = None
        finally:
            self.progress_bar.setVisible(False)

    def on_tree_selected(self, item):
        """Handle double-click on tree ID in list (deprecated)."""
        pass  # No longer used

    def update_tree_colors(self, color_field):
        """Update the coloring of the currently visualized tree."""
        if self.current_tree_points is None or self.current_tree_id is None or not self.plotter or not self.las_data:
            return

        if color_field == "Default (green)":
            # Use default green color
            self.plotter.clear()
            point_cloud = pv.PolyData(self.current_tree_points)
            self.plotter.add_points(point_cloud, color='green', point_size=3, render_points_as_spheres=True)
        else:
            # Color by the selected scalar field
            try:
                # Get the mask for the current tree
                itc_values = np.array(self.las_data['itc'])
                mask = itc_values == self.current_tree_id

                # Apply treefilter if enabled
                if self.filter_checkbox.isChecked() and 'treefilter' in self.las_data.point_format.dimension_names:
                    treefilter_values = np.array(self.las_data['treefilter'])
                    mask = mask & (treefilter_values == 2)

                # Get the color values
                color_values = np.array(self.las_data[color_field])[mask]

                self.plotter.clear()
                point_cloud = pv.PolyData(self.current_tree_points)
                self.plotter.add_points(point_cloud, scalars=color_values, point_size=3, render_points_as_spheres=True, cmap='viridis')
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Failed to color by field '{color_field}': {str(e)}")
                return

        # Reset camera and add title
        self.plotter.reset_camera()
        num_points = len(self.current_tree_points)
        self.plotter.add_text(f"Tree ID: {self.current_tree_id} ({num_points} points) - Color: {color_field}",
                             position='upper_left', font_size=12)
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

        # Visualize with current color field
        self.update_tree_colors(self.color_combo.currentText())

    def clear_plot(self):
        """Clear the 3D visualization."""
        if self.plotter:
            self.plotter.clear()
            self.plotter.update()

    def reset_view(self):
        """Reset the camera view."""
        if self.plotter:
            self.plotter.reset_camera()
            self.plotter.update()


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