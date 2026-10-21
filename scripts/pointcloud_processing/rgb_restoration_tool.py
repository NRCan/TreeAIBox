#!/usr/bin/env python3
"""
RGB Value Restoration Tool - Restore RGB values from original LAS to processed LAS
Matches points from processed LAS file to original LAS file and copies RGB values
"""

import sys
import os
import laspy
import numpy as np
from pathlib import Path
from scipy.spatial import KDTree

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
    QMessageBox, QLineEdit, QGroupBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor


class ModernButton(QPushButton):
    """Custom button with modern styling."""
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 10px 20px;
                text-align: center;
                font-size: 14px;
                border-radius: 6px;
                min-width: 100px;
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


class RGBRestorationWorker(QThread):
    """Worker thread for restoring RGB values from original to processed LAS file."""
    
    progress = pyqtSignal(str)  # Signal to send progress messages
    progress_update = pyqtSignal(int)  # Signal for progress bar
    finished = pyqtSignal(dict)  # Signal to send results
    error = pyqtSignal(str)  # Signal to send error messages
    
    def __init__(self, original_las_path, processed_las_path, output_las_path, max_distance):
        super().__init__()
        self.original_las_path = original_las_path
        self.processed_las_path = processed_las_path
        self.output_las_path = output_las_path
        self.max_distance = max_distance
        self.direct_mapping = False
        
    def run(self):
        """Restore RGB values from original to processed LAS file."""
        try:
            self.progress.emit(f"Opening original LAS file: {self.original_las_path}")
            
            # Open original LAS file
            with laspy.open(self.original_las_path) as original_file:
                original_data = original_file.read()
                
                # Check if original has RGB
                if not (hasattr(original_data, 'red') and hasattr(original_data, 'green') and hasattr(original_data, 'blue')):
                    self.error.emit("Original LAS file does not have RGB channels!")
                    return
                
                self.progress.emit(f"Original file: {len(original_data.points):,} points")
                
                # Get original RGB values
                original_rgb = np.column_stack([
                    np.asarray(original_data.red),
                    np.asarray(original_data.green),
                    np.asarray(original_data.blue)
                ])
                self.progress.emit(f"Extracted RGB from original file")
            
            self.progress.emit(f"\nOpening processed LAS file: {self.processed_las_path}")
            
            # Open processed LAS file
            with laspy.open(self.processed_las_path) as processed_file:
                processed_data = processed_file.read()
                self.progress.emit(f"Processed file: {len(processed_data.points):,} points")
                
                # Get XYZ coordinates
                original_xyz = np.column_stack([
                    np.asarray(original_data.x),
                    np.asarray(original_data.y),
                    np.asarray(original_data.z)
                ])
                
                processed_xyz = np.column_stack([
                    np.asarray(processed_data.x),
                    np.asarray(processed_data.y),
                    np.asarray(processed_data.z)
                ])
                
                # If direct mapping requested and point counts match, perform 1:1 copy
                if getattr(self, 'direct_mapping', False) and len(original_xyz) == len(processed_xyz):
                    self.progress.emit("Direct mapping requested and point counts match. Performing direct 1:1 mapping...")
                    distances = None
                    indices = np.arange(len(processed_xyz), dtype=int)
                    valid_mask = np.ones(len(processed_xyz), dtype=bool)
                    matched_count = len(processed_xyz)
                    # No distance statistics for direct mapping
                else:
                    self.progress.emit(f"\nBuilding spatial index on original points...")
                    # Build KDTree for fast nearest neighbor search
                    kdtree = KDTree(original_xyz)
                    
                    self.progress.emit(f"Finding nearest neighbors for processed points...")
                    # Find nearest neighbor for each processed point
                    distances, indices = kdtree.query(processed_xyz)
                    
                    # Filter by max distance
                    valid_mask = distances <= self.max_distance
                    matched_count = np.sum(valid_mask)
                    
                    self.progress.emit(f"Matched {matched_count:,} / {len(processed_xyz):,} points (within {self.max_distance}m)")
                    
                    if matched_count == 0:
                        self.error.emit("No points matched within maximum distance!")
                        return
                    
                    # Show distance statistics
                    matched_distances = distances[valid_mask]
                    self.progress.emit(f"Distance statistics:")
                    self.progress.emit(f"  Mean: {np.mean(matched_distances):.6f}m")
                    self.progress.emit(f"  Median: {np.median(matched_distances):.6f}m")
                    self.progress.emit(f"  Max: {np.max(matched_distances):.6f}m")
                
                # Create output LAS file (copy of processed)
                self.progress.emit(f"\nCreating output LAS file...")
                output_data = laspy.create(point_format=processed_data.header.point_format)
                
                # Copy all point data from processed file
                output_data.x = processed_data.x
                output_data.y = processed_data.y
                output_data.z = processed_data.z
                
                # Copy other attributes if they exist
                for dim_name in processed_data.point_format.dimension_names:
                    if dim_name not in ['x', 'y', 'z', 'red', 'green', 'blue']:
                        try:
                            setattr(output_data, dim_name, getattr(processed_data, dim_name))
                        except:
                            pass
                
                # Initialize RGB to 0
                output_data.red = np.zeros(len(processed_data.points), dtype=np.uint16)
                output_data.green = np.zeros(len(processed_data.points), dtype=np.uint16)
                output_data.blue = np.zeros(len(processed_data.points), dtype=np.uint16)
                
                # Copy RGB values from original to output for matched points
                self.progress.emit(f"Copying RGB values...")
                # Ensure indices is an integer array we can iterate
                indices_arr = np.asarray(indices, dtype=int)
                indices_list = indices_arr.tolist()
                for i, original_idx in enumerate(indices_list):
                    if valid_mask[i]:
                        output_data.red[i] = original_rgb[original_idx, 0]
                        output_data.green[i] = original_rgb[original_idx, 1]
                        output_data.blue[i] = original_rgb[original_idx, 2]
                    
                    if (i + 1) % 50000 == 0:
                        self.progress_update.emit(int((i + 1) / len(processed_xyz) * 100))
                
                self.progress_update.emit(100)
                
                # Write output LAS file
                self.progress.emit(f"\nWriting output LAS file: {self.output_las_path}")
                output_data.write(self.output_las_path)
                
                # Verify output
                with laspy.open(self.output_las_path) as output_file:
                    output_read = output_file.read()
                    colored_points = np.sum((np.asarray(output_read.red) > 0) | 
                                          (np.asarray(output_read.green) > 0) | 
                                          (np.asarray(output_read.blue) > 0))
                    
                    self.progress.emit(f"\n✓ Output file created successfully!")
                    self.progress.emit(f"  Total points: {len(output_read.points):,}")
                    self.progress.emit(f"  Points with color: {colored_points:,} ({colored_points/len(output_read.points)*100:.2f}%)")
                
                results = {
                    'output_file': self.output_las_path,
                    'original_points': len(original_data.points),
                    'processed_points': len(processed_data.points),
                    'matched_points': matched_count,
                    'colored_points': colored_points,
                    'success': True
                }
                
                self.finished.emit(results)
                
        except Exception as e:
            error_msg = f"Error restoring RGB values: {str(e)}"
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            self.error.emit(error_msg)


class RGBRestorationGUI(QMainWindow):
    """Main GUI for RGB Restoration Tool."""
    
    def __init__(self):
        super().__init__()
        self.original_file = None
        self.processed_file = None
        self.output_file = None
        self.restoration_worker = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the GUI."""
        self.setWindowTitle("RGB Restoration Tool - Restore RGB to Processed Point Cloud")
        self.setGeometry(100, 100, 1000, 750)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Title
        title_label = QLabel("RGB Value Restoration Tool")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4CAF50; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Original file selection
        original_group = QGroupBox("Original LAS File (with RGB)")
        original_layout = QHBoxLayout()
        self.original_path_label = QLineEdit()
        self.original_path_label.setReadOnly(True)
        self.original_path_label.setPlaceholderText("No file selected...")
        original_layout.addWidget(QLabel("File:"))
        original_layout.addWidget(self.original_path_label)
        
        original_browse = ModernButton("Browse...")
        original_browse.clicked.connect(self.browse_original_file)
        original_layout.addWidget(original_browse)
        
        original_group.setLayout(original_layout)
        layout.addWidget(original_group)
        
        # Processed file selection
        processed_group = QGroupBox("Processed LAS File (to restore RGB)")
        processed_layout = QHBoxLayout()
        self.processed_path_label = QLineEdit()
        self.processed_path_label.setReadOnly(True)
        self.processed_path_label.setPlaceholderText("No file selected...")
        processed_layout.addWidget(QLabel("File:"))
        processed_layout.addWidget(self.processed_path_label)
        
        processed_browse = ModernButton("Browse...")
        processed_browse.clicked.connect(self.browse_processed_file)
        processed_layout.addWidget(processed_browse)
        
        processed_group.setLayout(processed_layout)
        layout.addWidget(processed_group)
        
        # Output file selection
        output_group = QGroupBox("Output LAS File (with restored RGB)")
        output_layout = QHBoxLayout()
        self.output_path_label = QLineEdit()
        self.output_path_label.setReadOnly(True)
        self.output_path_label.setPlaceholderText("Output file path...")
        output_layout.addWidget(QLabel("File:"))
        output_layout.addWidget(self.output_path_label)
        
        output_browse = ModernButton("Browse...")
        output_browse.clicked.connect(self.browse_output_file)
        output_layout.addWidget(output_browse)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # Parameters
        params_group = QGroupBox("Restoration Parameters")
        params_layout = QHBoxLayout()
        
        params_layout.addWidget(QLabel("Max Distance (m):"))
        self.max_distance_spin = QDoubleSpinBox()
        self.max_distance_spin.setMinimum(0.001)
        self.max_distance_spin.setMaximum(100.0)
        self.max_distance_spin.setValue(0.5)
        self.max_distance_spin.setDecimals(3)
        params_layout.addWidget(self.max_distance_spin)

        # Direct mapping option
        self.direct_map_checkbox = QCheckBox("Direct mapping (1:1) if point counts match")
        self.direct_map_checkbox.setToolTip("If checked and both LAS files have the same number of points, RGB will be copied by index instead of nearest-neighbor matching.")
        params_layout.addWidget(self.direct_map_checkbox)
        
        params_layout.addStretch()
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Action buttons
        action_group = QGroupBox("Actions")
        action_layout = QHBoxLayout()
        
        self.restore_button = ModernButton("Restore RGB Values")
        self.restore_button.clicked.connect(self.restore_rgb)
        self.restore_button.setEnabled(False)
        action_layout.addWidget(self.restore_button)
        
        self.clear_button = ModernButton("Clear")
        self.clear_button.clicked.connect(self.clear_all)
        action_layout.addWidget(self.clear_button)
        
        action_layout.addStretch()
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Results display
        results_group = QGroupBox("Progress & Results")
        results_layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QFont("Courier", 10))
        self.results_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        results_layout.addWidget(self.results_text)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)
        
    def apply_dark_theme(self):
        """Apply dark theme to the application."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(30, 30, 30))
        
        self.setPalette(palette)
        
    def browse_original_file(self):
        """Browse for original LAS file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Original LAS File (with RGB)",
            "",
            "LAS Files (*.las);;LAZ Files (*.laz);;All Files (*)"
        )
        
        if file_path:
            self.original_file = file_path
            self.original_path_label.setText(file_path)
            self.update_restore_button()
            
    def browse_processed_file(self):
        """Browse for processed LAS file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Processed LAS File (to restore RGB)",
            "",
            "LAS Files (*.las);;LAZ Files (*.laz);;All Files (*)"
        )
        
        if file_path:
            self.processed_file = file_path
            self.processed_path_label.setText(file_path)
            self.update_restore_button()
            
    def browse_output_file(self):
        """Browse for output file location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output LAS File",
            "",
            "LAS Files (*.las);;All Files (*)"
        )
        
        if file_path:
            self.output_file = file_path
            self.output_path_label.setText(file_path)
            self.update_restore_button()
            
    def update_restore_button(self):
        """Update restore button enabled state."""
        if self.original_file and self.processed_file and self.output_file:
            self.restore_button.setEnabled(True)
        else:
            self.restore_button.setEnabled(False)
            
    def restore_rgb(self):
        """Start RGB restoration process."""
        if not all([self.original_file, self.processed_file, self.output_file]):
            QMessageBox.warning(self, "Warning", "Please select all required files.")
            return
        
        # Disable buttons during processing
        self.restore_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.results_text.clear()
        self.status_label.setText("Processing...")
        
        # Create and start worker thread
        max_distance = self.max_distance_spin.value()
        self.restoration_worker = RGBRestorationWorker(
            self.original_file,
            self.processed_file,
            self.output_file,
            max_distance
        )
        # Configure direct mapping flag on worker
        try:
            self.restoration_worker.direct_mapping = bool(self.direct_map_checkbox.isChecked())
        except Exception:
            pass
        self.restoration_worker.progress.connect(self.on_progress)
        self.restoration_worker.progress_update.connect(self.on_progress_update)
        self.restoration_worker.finished.connect(self.on_finished)
        self.restoration_worker.error.connect(self.on_error)
        self.restoration_worker.start()
        
    def on_progress(self, message):
        """Handle progress message from worker thread."""
        self.results_text.append(message)
        
    def on_progress_update(self, value):
        """Handle progress bar update."""
        self.progress_bar.setValue(value)
        
    def on_finished(self, results):
        """Handle worker thread completion."""
        self.progress_bar.setVisible(False)
        self.restore_button.setEnabled(True)
        self.status_label.setText("✓ RGB restoration completed successfully!")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        
    def on_error(self, error_msg):
        """Handle error from worker thread."""
        self.progress_bar.setVisible(False)
        self.restore_button.setEnabled(True)
        self.status_label.setText("✗ Error occurred")
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
        
        self.results_text.append(f"\n❌ ERROR: {error_msg}")
        QMessageBox.critical(self, "Error", f"Failed to restore RGB values:\n\n{error_msg}")
        
    def clear_all(self):
        """Clear all fields."""
        self.original_file = None
        self.processed_file = None
        self.output_file = None
        self.original_path_label.clear()
        self.processed_path_label.clear()
        self.output_path_label.clear()
        self.results_text.clear()
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.update_restore_button()


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = RGBRestorationGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
