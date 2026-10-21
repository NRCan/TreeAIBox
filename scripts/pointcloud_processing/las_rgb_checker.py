#!/usr/bin/env python3
"""
LAS RGB Checker - Check if LAS files have RGB values for points
A PyQt6 GUI application to analyze LAS files and determine if they contain RGB point data.
"""

import sys
import os
import laspy
import numpy as np
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
    QMessageBox, QLineEdit, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon


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


class RGBCheckWorker(QThread):
    """Worker thread for checking LAS file RGB values."""
    
    progress = pyqtSignal(str)  # Signal to send progress messages
    finished = pyqtSignal(dict)  # Signal to send results
    error = pyqtSignal(str)  # Signal to send error messages
    
    def __init__(self, las_file_path):
        super().__init__()
        self.las_file_path = las_file_path
        
    def run(self):
        """Check LAS file for RGB values."""
        try:
            self.progress.emit(f"Opening LAS file: {self.las_file_path}")
            
            # Open the LAS file
            with laspy.open(self.las_file_path) as las_file:
                las_data = las_file.read()
                
                # Get basic information
                num_points = len(las_data.points)
                las_version = f"{las_file.header.version.major}.{las_file.header.version.minor}"
                point_format = las_file.header.point_format.id
                
                self.progress.emit(f"LAS Version: {las_version}")
                self.progress.emit(f"Point Format: {point_format}")
                self.progress.emit(f"Total Points: {num_points:,}")
                
                # Check for RGB values
                has_rgb = False
                rgb_info = {}
                
                # Check for standard RGB fields
                if hasattr(las_data, 'red') and hasattr(las_data, 'green') and hasattr(las_data, 'blue'):
                    # Convert to numpy arrays for operations
                    red = np.asarray(las_data.red)
                    green = np.asarray(las_data.green)
                    blue = np.asarray(las_data.blue)
                    
                    # Check if RGB values are all zeros
                    has_color = np.any(red > 0) or np.any(green > 0) or np.any(blue > 0)
                    
                    # Count colored points
                    colored_points = np.sum((red > 0) | (green > 0) | (blue > 0))
                    
                    if has_color and colored_points > 0:
                        # RGB channels have actual color data
                        has_rgb = True
                        self.progress.emit(f"✓ RGB channels found WITH COLOR VALUES")
                        self.progress.emit(f"  Red values: min={np.min(red)}, max={np.max(red)}, mean={np.mean(red):.2f}")
                        self.progress.emit(f"  Green values: min={np.min(green)}, max={np.max(green)}, mean={np.mean(green):.2f}")
                        self.progress.emit(f"  Blue values: min={np.min(blue)}, max={np.max(blue)}, mean={np.mean(blue):.2f}")
                        self.progress.emit(f"  Colored points: {colored_points:,} ({colored_points/num_points*100:.2f}%)")
                        
                        rgb_info['red'] = {'min': int(np.min(red)), 'max': int(np.max(red)), 'mean': float(np.mean(red))}
                        rgb_info['green'] = {'min': int(np.min(green)), 'max': int(np.max(green)), 'mean': float(np.mean(green))}
                        rgb_info['blue'] = {'min': int(np.min(blue)), 'max': int(np.max(blue)), 'mean': float(np.mean(blue))}
                        rgb_info['colored_points'] = colored_points
                        rgb_info['has_color'] = True
                    else:
                        # RGB channels exist but no color data
                        has_rgb = False
                        self.progress.emit(f"⚠ RGB channels found BUT NO COLOR VALUES")
                        self.progress.emit(f"  Red values: all zeros (min=0, max=0)")
                        self.progress.emit(f"  Green values: all zeros (min=0, max=0)")
                        self.progress.emit(f"  Blue values: all zeros (min=0, max=0)")
                        self.progress.emit(f"  Colored points: 0 (0.00%)")
                        self.progress.emit(f"\n  ⚠ Note: RGB dimensions exist but contain no actual color data")
                        
                        rgb_info['has_color'] = False
                        rgb_info['colored_points'] = 0
                else:
                    has_rgb = False
                    self.progress.emit("✗ RGB channels NOT found (no red, green, or blue dimensions)")
                
                # Check for NIR (Near Infrared) if available
                has_nir = False
                if hasattr(las_data, 'nir'):
                    has_nir = True
                    nir = np.asarray(las_data.nir)
                    self.progress.emit(f"✓ NIR channel found")
                    self.progress.emit(f"  NIR values: min={np.min(nir)}, max={np.max(nir)}, mean={np.mean(nir):.2f}")
                    rgb_info['nir'] = {'min': int(np.min(nir)), 'max': int(np.max(nir)), 'mean': float(np.mean(nir))}
                else:
                    self.progress.emit("✗ NIR channel NOT found")
                
                # Check available dimensions
                self.progress.emit(f"\nAvailable dimensions:")
                available_dims = las_data.point_format.dimension_names
                for dim in sorted(available_dims):
                    self.progress.emit(f"  - {dim}")
                
                # Prepare results
                results = {
                    'file_path': self.las_file_path,
                    'num_points': num_points,
                    'las_version': las_version,
                    'point_format': point_format,
                    'has_rgb': has_rgb,
                    'has_nir': has_nir,
                    'rgb_info': rgb_info,
                    'available_dimensions': list(available_dims),
                    'success': True
                }
                
                self.progress.emit(f"\n✓ Analysis completed successfully!")
                self.finished.emit(results)
                
        except Exception as e:
            error_msg = f"Error analyzing LAS file: {str(e)}"
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            self.error.emit(error_msg)


class LASRGBCheckerGUI(QMainWindow):
    """Main GUI for LAS RGB Checker."""
    
    def __init__(self):
        super().__init__()
        self.las_file_path = None
        self.check_worker = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the GUI."""
        self.setWindowTitle("LAS RGB Checker - Check RGB Values in LAS Files")
        self.setGeometry(100, 100, 900, 700)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Title
        title_label = QLabel("LAS RGB Checker")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4CAF50; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # File selection group
        file_group = QGroupBox("File Selection")
        file_layout = QHBoxLayout()
        
        self.file_path_label = QLineEdit()
        self.file_path_label.setReadOnly(True)
        self.file_path_label.setPlaceholderText("No file selected...")
        file_layout.addWidget(QLabel("LAS File:"))
        file_layout.addWidget(self.file_path_label)
        
        self.browse_button = ModernButton("Browse...")
        self.browse_button.clicked.connect(self.browse_las_file)
        file_layout.addWidget(self.browse_button)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Action buttons group
        action_group = QGroupBox("Analysis")
        action_layout = QHBoxLayout()
        
        self.check_button = ModernButton("Check RGB Values")
        self.check_button.clicked.connect(self.check_rgb_values)
        self.check_button.setEnabled(False)
        action_layout.addWidget(self.check_button)
        
        self.clear_button = ModernButton("Clear Results")
        self.clear_button.clicked.connect(self.clear_results)
        action_layout.addWidget(self.clear_button)
        
        action_layout.addStretch()
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Results display
        results_group = QGroupBox("Analysis Results")
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
        
    def browse_las_file(self):
        """Open file browser to select LAS file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select LAS File",
            "",
            "LAS Files (*.las);;LAZ Files (*.laz);;All Files (*)"
        )
        
        if file_path:
            self.las_file_path = file_path
            self.file_path_label.setText(file_path)
            self.check_button.setEnabled(True)
            self.status_label.setText(f"File selected: {Path(file_path).name}")
            
    def check_rgb_values(self):
        """Start checking RGB values in the LAS file."""
        if not self.las_file_path:
            QMessageBox.warning(self, "Warning", "Please select a LAS file first.")
            return
            
        # Disable buttons during processing
        self.check_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate progress
        self.results_text.clear()
        self.status_label.setText("Analyzing file...")
        
        # Create and start worker thread
        self.check_worker = RGBCheckWorker(self.las_file_path)
        self.check_worker.progress.connect(self.on_progress)
        self.check_worker.finished.connect(self.on_finished)
        self.check_worker.error.connect(self.on_error)
        self.check_worker.start()
        
    def on_progress(self, message):
        """Handle progress message from worker thread."""
        self.results_text.append(message)
        
    def on_finished(self, results):
        """Handle worker thread completion."""
        self.progress_bar.setVisible(False)
        self.check_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        
        if results['has_rgb']:
            self.status_label.setText("✓ RGB values FOUND")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        else:
            self.status_label.setText("✗ No RGB values found")
            self.status_label.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
            
    def on_error(self, error_msg):
        """Handle error from worker thread."""
        self.progress_bar.setVisible(False)
        self.check_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.status_label.setText("Error occurred")
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
        
        print(f"ERROR: {error_msg}")
        self.results_text.append(f"\n❌ ERROR: {error_msg}")
        QMessageBox.critical(self, "Error", f"Failed to analyze LAS file:\n\n{error_msg}")
        
    def clear_results(self):
        """Clear the results display."""
        self.results_text.clear()
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.progress_bar.setVisible(False)


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = LASRGBCheckerGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
