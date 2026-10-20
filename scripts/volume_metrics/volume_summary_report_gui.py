#!/usr/bin/env python3
"""
Volume Data Summary Report GUI for TreeAIBox Enhancer

A PyQt6 GUI for processing tree volume data JSON files and generating
comprehensive summary reports with DBH calculations and per-tree statistics.

Usage: python volume_summary_report_gui.py
"""

import sys
import os
import json
import glob
from pathlib import Path
from datetime import datetime
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar,
    QFrame, QSplitter, QMessageBox, QLineEdit, QGroupBox, QComboBox,
    QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon

class VolumeSummaryReport:
    def __init__(self):
        self.dbh_height = 1.37  # Standard DBH measurement height in meters

    def load_tree_data(self, json_file):
        """Load tree data from a JSON file."""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            error_msg = f"Error loading {json_file}: {e}"
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return None

    def calculate_dbh_from_circles(self, circles):
        """
        Calculate DBH from circle data.
        DBH is measured at 1.37m above ground.
        Returns diameter at DBH height.
        """
        if not circles:
            return None

        # Find circles closest to DBH height (1.37m)
        dbh_circles = []
        for center, radius in circles:
            height = center[2]  # Z coordinate is height
            if abs(height - self.dbh_height) <= 0.2:  # Within 20cm of DBH height
                dbh_circles.append((height, radius * 2))  # Convert radius to diameter

        if not dbh_circles:
            return None

        # Return average diameter at DBH height
        diameters = [d for h, d in dbh_circles]
        return np.mean(diameters)

    def process_tree_file(self, json_file):
        """Process a single tree JSON file and return summary data."""
        data = self.load_tree_data(json_file)
        if not data:
            return None

        tree_id = Path(json_file).stem.replace('tree_', '')

        # Extract sections data
        sections = data.get('sections', [])
        total_volume = data.get('total_volume', 0.0)
        total_sections = data.get('total_sections', 0)

        # Process each section
        section_summaries = []
        diameters = []
        heights = []

        for section in sections:
            section_id = section.get('section_id', 'unknown')
            volume = section.get('volume', 0.0)

            # Extract circle data
            circle_data = section.get('circle_data', {})
            circles = circle_data.get('circles', [])

            # Get diameters from circles
            section_diameters = []
            section_heights = []

            for center, radius in circles:
                height = center[2]
                diameter = radius * 2  # Convert radius to diameter
                section_diameters.append(diameter)
                section_heights.append(height)

            # Calculate average diameter for this section
            avg_diameter = np.mean(section_diameters) if section_diameters else 0.0

            # Store section info
            section_summaries.append({
                'section_id': section_id,
                'volume': volume,
                'avg_diameter': avg_diameter,
                'diameters': section_diameters,
                'heights': section_heights,
                'num_circles': len(circles),
                'extrapolated': section.get('extrapolated', False),
                'original_height_range': section.get('original_height_range'),
                'extrapolated_height_range': section.get('extrapolated_height_range'),
                'original_min_z': section.get('original_min_z'),
                'extrapolated_min_z': section.get('extrapolated_min_z'),
                'num_extrapolated_circles': section.get('num_extrapolated_circles'),
                'ground_level_used': section.get('ground_level_used')
            })

            diameters.extend(section_diameters)
            heights.extend(section_heights)

        # Calculate DBH
        all_circles = []
        for section in sections:
            circle_data = section.get('circle_data', {})
            circles = circle_data.get('circles', [])
            all_circles.extend(circles)

        dbh_diameter = self.calculate_dbh_from_circles(all_circles)

        return {
            'tree_id': tree_id,
            'total_volume': total_volume,
            'total_sections': total_sections,
            'dbh_diameter': dbh_diameter,
            'avg_diameter': np.mean(diameters) if diameters else 0.0,
            'min_diameter': np.min(diameters) if diameters else 0.0,
            'max_diameter': np.max(diameters) if diameters else 0.0,
            'height_range': f"{np.min(heights):.2f} - {np.max(heights):.2f}" if heights else "N/A",
            'sections': section_summaries
        }

    def generate_report_text(self, folder_path):
        """Generate a comprehensive summary report text for all tree files in the folder."""

        if not os.path.exists(folder_path):
            return f"Error: Folder {folder_path} does not exist."

        # Find all tree_*.json files
        tree_files = glob.glob(os.path.join(folder_path, "tree_*.json"))

        if not tree_files:
            return f"No tree_*.json files found in {folder_path}"

        # Process all tree files
        all_trees_data = []
        total_trees = 0
        total_volume = 0.0

        for json_file in sorted(tree_files):
            tree_data = self.process_tree_file(json_file)
            if tree_data:
                all_trees_data.append(tree_data)
                total_trees += 1
                total_volume += tree_data['total_volume']

        # Generate report
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("TREE VOLUME DATA SUMMARY REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Folder: {folder_path}")
        report_lines.append(f"Total Files Processed: {len(tree_files)}")
        report_lines.append(f"Total Trees: {total_trees}")
        report_lines.append(f"Total Volume: {total_volume:.4f} m³")
        report_lines.append("")

        # Overall statistics
        if all_trees_data:
            dbh_values = [t['dbh_diameter'] for t in all_trees_data if t['dbh_diameter'] is not None]
            avg_dbh = np.mean(dbh_values) if dbh_values else 0.0

            report_lines.append("OVERALL STATISTICS:")
            report_lines.append("-" * 40)
            report_lines.append(f"Average DBH: {avg_dbh:.3f} m" if dbh_values else "Average DBH: N/A")
            report_lines.append(f"Trees with DBH data: {len(dbh_values)}/{total_trees}")
            report_lines.append("")

        # Per-file summary
        report_lines.append("PER-TREE SUMMARY:")
        report_lines.append("-" * 40)

        for tree_data in all_trees_data:
            report_lines.append(f"Tree ID: {tree_data['tree_id']}")
            report_lines.append(f"  Total Volume: {tree_data['total_volume']:.4f} m³")
            report_lines.append(f"  Total Sections: {tree_data['total_sections']}")
            report_lines.append(f"  DBH Diameter: {tree_data['dbh_diameter']:.3f} m" if tree_data['dbh_diameter'] else "  DBH Diameter: N/A")
            report_lines.append(f"  Average Diameter: {tree_data['avg_diameter']:.3f} m")
            report_lines.append(f"  Diameter Range: {tree_data['min_diameter']:.3f} - {tree_data['max_diameter']:.3f} m")
            report_lines.append(f"  Height Range: {tree_data['height_range']} m")
            report_lines.append("  Sections:")

            for section in tree_data['sections']:
                report_lines.append(f"    Section {section['section_id']}:")
                report_lines.append(f"      Volume: {section['volume']:.4f} m³")
                report_lines.append(f"      Avg Diameter: {section['avg_diameter']:.3f} m")
                report_lines.append(f"      Circles: {section['num_circles']}")
                if section.get('extrapolated'):
                    report_lines.append(f"      ⚠️ EXTRAPOLATED to ground level")
                    if section.get('original_height_range') is not None:
                        report_lines.append(f"      Original height range: {section['original_height_range']:.2f}m")
                    if section.get('extrapolated_height_range') is not None:
                        report_lines.append(f"      Extrapolated height range: {section['extrapolated_height_range']:.2f}m")
                    if section.get('original_min_z') is not None:
                        report_lines.append(f"      Original lowest Z: {section['original_min_z']:.2f}m")
                    if section.get('extrapolated_min_z') is not None:
                        report_lines.append(f"      Extrapolated lowest Z: {section['extrapolated_min_z']:.2f}m")
                    if section.get('num_extrapolated_circles') is not None:
                        report_lines.append(f"      Extrapolated circles added: {section['num_extrapolated_circles']}")
                    if section.get('ground_level_used') is not None:
                        report_lines.append(f"      Ground level used: {section['ground_level_used']:.2f}m")
                report_lines.append("")

            report_lines.append("")

        return "\n".join(report_lines)

    def generate_csv_report(self, folder_path, include_sections=True):
        """Generate a CSV summary report for all tree files in the folder."""

        if not os.path.exists(folder_path):
            return None, f"Error: Folder {folder_path} does not exist."

        # Find all tree_*.json files
        tree_files = glob.glob(os.path.join(folder_path, "tree_*.json"))

        if not tree_files:
            return None, f"No tree_*.json files found in {folder_path}"

        # Process all tree files
        all_trees_data = []
        total_trees = 0
        total_volume = 0.0

        for json_file in sorted(tree_files):
            tree_data = self.process_tree_file(json_file)
            if tree_data:
                all_trees_data.append(tree_data)
                total_trees += 1
                total_volume += tree_data['total_volume']

        # Generate CSV data
        csv_lines = []
        if include_sections:
            csv_lines.append("Report_Type,Tree_ID,Section_ID,Volume_m3,DBH_Diameter_m,Avg_Diameter_m,Min_Diameter_m,Max_Diameter_m,Height_Range_m,Num_Circles,Individual_Diameters_m,Extrapolated,Original_Height_Range_m,Extrapolated_Height_Range_m,Original_Min_Z_m,Extrapolated_Min_Z_m,Num_Extrapolated_Circles,Ground_Level_Used_m")
        else:
            csv_lines.append("Report_Type,Tree_ID,Volume_m3,DBH_Diameter_m,Avg_Diameter_m,Min_Diameter_m,Max_Diameter_m,Height_Range_m,Total_Sections")

        # Overall summary row
        if include_sections:
            csv_lines.append(f"OVERALL_SUMMARY,ALL,{total_trees},{total_volume:.4f},,,,{total_trees} trees,{len(tree_files)} files,,{len(tree_files)} files processed")
        else:
            csv_lines.append(f"OVERALL_SUMMARY,ALL,{total_volume:.4f},,,,{total_trees} trees,{len(tree_files)} files,{total_trees}")

        # Per-tree summary rows
        for tree_data in all_trees_data:
            dbh_str = f"{tree_data['dbh_diameter']:.4f}" if tree_data['dbh_diameter'] else ""
            height_range = tree_data['height_range'].replace(" - ", "-") if tree_data['height_range'] != "N/A" else ""
            
            if include_sections:
                csv_lines.append(f"TREE_SUMMARY,{tree_data['tree_id']},,{tree_data['total_volume']:.4f},{dbh_str},{tree_data['avg_diameter']:.4f},{tree_data['min_diameter']:.4f},{tree_data['max_diameter']:.4f},{height_range},{tree_data['total_sections']},sections")

                # Per-section detail rows
                for section in tree_data['sections']:
                    diameters_str = "|".join([f"{d:.4f}" for d in section['diameters']])
                    min_diam = min(section['diameters']) if section['diameters'] else 0.0
                    max_diam = max(section['diameters']) if section['diameters'] else 0.0
                    csv_lines.append(f"SECTION_DETAIL,{tree_data['tree_id']},{section['section_id']},{section['volume']:.4f},,{section['avg_diameter']:.4f},{min_diam:.4f},{max_diam:.4f},,{section['num_circles']},{diameters_str},{section.get('extrapolated', False)},{section.get('original_height_range', '') if section.get('original_height_range') is not None else ''},{section.get('extrapolated_height_range', '') if section.get('extrapolated_height_range') is not None else ''},{section.get('original_min_z', '') if section.get('original_min_z') is not None else ''},{section.get('extrapolated_min_z', '') if section.get('extrapolated_min_z') is not None else ''},{section.get('num_extrapolated_circles', '') if section.get('num_extrapolated_circles') is not None else ''},{section.get('ground_level_used', '') if section.get('ground_level_used') is not None else ''}")
            else:
                csv_lines.append(f"TREE_SUMMARY,{tree_data['tree_id']},{tree_data['total_volume']:.4f},{dbh_str},{tree_data['avg_diameter']:.4f},{tree_data['min_diameter']:.4f},{tree_data['max_diameter']:.4f},{height_range},{tree_data['total_sections']}")

        csv_content = "\n".join(csv_lines)
        return csv_content, None


class ReportGenerator(QThread):
    """Worker thread for generating reports without blocking the UI."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, str, str)  # report_content, save_path, format
    error = pyqtSignal(str)

    def __init__(self, folder_path, output_file=None, format='text', include_sections=True):
        super().__init__()
        self.folder_path = folder_path
        self.output_file = output_file
        self.format = format  # 'text' or 'csv'
        self.include_sections = include_sections
        self.generator = VolumeSummaryReport()

    def run(self):
        try:
            self.progress.emit(10)
            if self.format == 'csv':
                report_content, error = self.generator.generate_csv_report(self.folder_path, self.include_sections)
                if error:
                    self.error.emit(error)
                    return
            else:
                report_content = self.generator.generate_report_text(self.folder_path)

            self.progress.emit(50)

            # Determine file extension and save path
            if self.output_file:
                save_path = self.output_file
                if not save_path.lower().endswith(f'.{self.format}'):
                    save_path += f'.{self.format}'
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(self.folder_path, f"volume_summary_report_{timestamp}.{self.format}")

            with open(save_path, 'w', newline='' if self.format == 'csv' else '') as f:
                if report_content is not None:
                    f.write(report_content)

            self.progress.emit(100)
            self.finished.emit(report_content, save_path, self.format)

        except Exception as e:
            self.error.emit(str(e))


class BatchPlotProcessor(QThread):
    """Worker thread for processing multiple plot folders."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, list)  # summary_text, saved_files
    error = pyqtSignal(str)

    def __init__(self, plot_folders, format_type='csv', include_sections=True):
        super().__init__()
        self.plot_folders = plot_folders
        self.format_type = format_type
        self.include_sections = include_sections
        self.generator = VolumeSummaryReport()

    def run(self):
        try:
            saved_files = []
            summary_lines = []
            summary_lines.append("=" * 80)
            summary_lines.append("MULTI-PLOT VOLUME SUMMARY REPORT")
            summary_lines.append("=" * 80)
            summary_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            summary_lines.append(f"Total Plots Processed: {len(self.plot_folders)}")
            summary_lines.append("")

            total_all_plots = 0
            total_volume_all_plots = 0.0
            plot_summaries = []

            for i, plot_folder in enumerate(self.plot_folders):
                plot_name = os.path.basename(plot_folder)
                self.progress.emit(int((i / len(self.plot_folders)) * 100))

                # Generate report for this plot
                if self.format_type == 'csv':
                    report_content, error = self.generator.generate_csv_report(plot_folder, self.include_sections)
                    if error:
                        self.error.emit(f"Error processing {plot_name}: {error}")
                        continue
                else:
                    report_content = self.generator.generate_report_text(plot_folder)

                # Save individual plot report
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = 'csv' if self.format_type == 'csv' else 'txt'
                filename = f"{plot_name}_volume_summary_{timestamp}.{ext}"
                filepath = os.path.join(plot_folder, filename)

                with open(filepath, 'w', newline='' if self.format_type == 'csv' else '') as f:
                    if report_content is not None:
                        f.write(report_content)

                saved_files.append(filepath)

                # Extract summary stats for overall report
                tree_files = glob.glob(os.path.join(plot_folder, "tree_*.json"))
                plot_trees = len(tree_files)
                plot_volume = 0.0

                for json_file in tree_files:
                    data = self.generator.load_tree_data(json_file)
                    if data:
                        plot_volume += data.get('total_volume', 0.0)

                total_all_plots += plot_trees
                total_volume_all_plots += plot_volume

                plot_summaries.append({
                    'name': plot_name,
                    'trees': plot_trees,
                    'volume': plot_volume,
                    'filepath': filepath
                })

                summary_lines.append(f"Plot: {plot_name}")
                summary_lines.append(f"  Trees: {plot_trees}")
                summary_lines.append(f"  Volume: {plot_volume:.4f} m³")
                summary_lines.append(f"  Report: {filename}")
                summary_lines.append("")

            # Overall summary
            summary_lines.append("OVERALL SUMMARY ACROSS ALL PLOTS:")
            summary_lines.append("-" * 40)
            summary_lines.append(f"Total Plots: {len(self.plot_folders)}")
            summary_lines.append(f"Total Trees: {total_all_plots}")
            summary_lines.append(f"Total Volume: {total_volume_all_plots:.4f} m³")
            summary_lines.append(".2f")
            summary_lines.append("")
            summary_lines.append("INDIVIDUAL PLOT DETAILS:")
            summary_lines.append("-" * 40)

            for summary in plot_summaries:
                summary_lines.append(f"{summary['name']}: {summary['trees']} trees, {summary['volume']:.4f} m³")

            self.progress.emit(100)
            self.finished.emit("\n".join(summary_lines), saved_files)

        except Exception as e:
            error_msg = str(e)
            print(f"ERROR: BatchPlotProcessor failed - {error_msg}")
            import traceback
            traceback.print_exc()
            self.error.emit(error_msg)


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


class VolumeReportGUI(QMainWindow):
    """Main window for the Volume Summary Report GUI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TreeAIBox Volume Summary Report")
        self.setGeometry(100, 100, 1000, 800)

        # Initialize variables
        self.folder_path = None
        self.output_file = None
        self.report_thread = None

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Title
        title_label = QLabel("TreeAIBox Volume Summary Report Generator")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50; margin-bottom: 10px;")
        main_layout.addWidget(title_label)

        # Input section
        input_group = QGroupBox("Input Settings")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(12)

        # Folder selection
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Data Folder:")
        folder_label.setFixedWidth(100)
        folder_label.setStyleSheet("font-weight: bold;")
        self.folder_path_label = QLabel("No folder selected")
        self.folder_path_label.setStyleSheet("color: #666666; padding: 5px; background-color: #f5f5f5; border-radius: 3px;")
        self.select_folder_button = ModernButton("Select Folder")
        self.select_folder_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_path_label, 1)
        folder_layout.addWidget(self.select_folder_button)
        input_layout.addLayout(folder_layout)

        # Output file selection
        output_layout = QHBoxLayout()
        output_label = QLabel("Output File:")
        output_label.setFixedWidth(100)
        output_label.setStyleSheet("font-weight: bold;")
        self.output_file_edit = QLineEdit()
        self.output_file_edit.setPlaceholderText("Auto-generated if empty")
        self.output_file_edit.setStyleSheet("padding: 5px; border: 1px solid #ccc; border-radius: 3px;")
        self.select_output_button = ModernButton("Select File")
        self.select_output_button.clicked.connect(self.select_output_file)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_file_edit, 1)
        output_layout.addWidget(self.select_output_button)
        input_layout.addLayout(output_layout)

        # Format selection
        format_layout = QHBoxLayout()
        format_label = QLabel("Output Format:")
        format_label.setFixedWidth(100)
        format_label.setStyleSheet("font-weight: bold;")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Text (.txt)", "CSV (.csv)"])
        self.format_combo.setStyleSheet("padding: 5px; border: 1px solid #ccc; border-radius: 3px;")
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        input_layout.addLayout(format_layout)

        # Section details option
        section_layout = QHBoxLayout()
        section_label = QLabel("Include Sections:")
        section_label.setFixedWidth(100)
        section_label.setStyleSheet("font-weight: bold;")
        self.section_checkbox = QCheckBox("Include detailed section data")
        self.section_checkbox.setChecked(True)
        self.section_checkbox.setStyleSheet("margin-top: 5px;")
        section_layout.addWidget(section_label)
        section_layout.addWidget(self.section_checkbox)
        section_layout.addStretch()
        input_layout.addLayout(section_layout)

        main_layout.addWidget(input_group)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

        self.generate_button = ModernButton("Generate Report")
        self.generate_button.clicked.connect(self.generate_report)
        self.generate_button.setEnabled(False)
        button_layout.addWidget(self.generate_button)

        self.process_all_button = ModernButton("Process All Plots")
        self.process_all_button.clicked.connect(self.process_all_plots)
        self.process_all_button.setEnabled(False)
        button_layout.addWidget(self.process_all_button)

        self.clear_button = ModernButton("Clear Results")
        self.clear_button.clicked.connect(self.clear_results)
        button_layout.addWidget(self.clear_button)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #4CAF50;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        # Results section
        results_group = QGroupBox("Report Results")
        results_layout = QVBoxLayout(results_group)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Courier New', monospace;
                font-size: 10px;
                color: #000000;
                background-color: #f8f8f8;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        results_layout.addWidget(self.results_text)

        # Status label
        self.status_label = QLabel("Ready to generate report")
        self.status_label.setStyleSheet("color: #666666; font-style: italic; margin-top: 5px;")
        results_layout.addWidget(self.status_label)

        main_layout.addWidget(results_group)

    def apply_stylesheet(self):
        """Apply overall stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

    def select_folder(self):
        """Select the folder containing tree JSON files."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder Containing Tree Data Files",
            ""  # Default directory
        )

        if folder:
            self.folder_path = folder
            self.folder_path_label.setText(folder)
            self.generate_button.setEnabled(True)
            
            # Check if this is the Volume folder with Plot subfolders
            if os.path.basename(folder) == "Volume" and any(d.startswith("Plot_") for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))):
                self.process_all_button.setEnabled(True)
            else:
                self.process_all_button.setEnabled(False)
                
            self.status_label.setText("Folder selected. Ready to generate report.")

    def select_output_file(self):
        """Select the output file path."""
        format_text = self.format_combo.currentText()
        if "CSV" in format_text:
            file_filter = "CSV Files (*.csv);;All Files (*)"
            default_ext = ".csv"
        else:
            file_filter = "Text Files (*.txt);;All Files (*)"
            default_ext = ".txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Select Output File",
            self.folder_path or "",
            file_filter
        )

        if file_path:
            # Ensure correct extension
            if not file_path.lower().endswith(default_ext):
                file_path += default_ext
            self.output_file = file_path
            self.output_file_edit.setText(file_path)

    def generate_report(self):
        """Generate the volume summary report."""
        if not self.folder_path:
            QMessageBox.warning(self, "No Folder Selected", "Please select a folder containing tree data files first.")
            return

        # Disable buttons during processing
        self.generate_button.setEnabled(False)
        self.select_folder_button.setEnabled(False)
        self.select_output_button.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Generating report...")

        # Clear previous results
        self.results_text.clear()

        # Start report generation in background thread
        output_file = self.output_file_edit.text().strip() if self.output_file_edit.text().strip() else None
        format_type = 'csv' if 'CSV' in self.format_combo.currentText() else 'text'
        include_sections = self.section_checkbox.isChecked()
        self.report_thread = ReportGenerator(self.folder_path, output_file, format_type, include_sections)
        self.report_thread.progress.connect(self.progress_bar.setValue)
        self.report_thread.finished.connect(self.on_report_finished)
        self.report_thread.error.connect(self.on_report_error)
        self.report_thread.start()

    def on_report_finished(self, report_content, save_path, format_type):
        """Handle successful report generation."""
        # Hide progress bar
        self.progress_bar.setVisible(False)

        # Display results
        self.results_text.setPlainText(report_content)
        self.status_label.setText(f"Report generated successfully. Saved to: {save_path}")

        # Re-enable buttons
        self.generate_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.select_output_button.setEnabled(True)

        # Show success message
        QMessageBox.information(self, "Report Generated",
                              f"Volume summary report generated successfully!\n\nSaved to: {save_path}")

    def on_report_error(self, error_msg):
        """Handle report generation error."""
        # Print to console for debugging
        print(f"ERROR: Report generation failed - {error_msg}")
        import traceback
        traceback.print_exc()

        # Hide progress bar
        self.progress_bar.setVisible(False)

        # Show error
        self.status_label.setText(f"Error generating report: {error_msg}")
        QMessageBox.critical(self, "Report Generation Error", f"Failed to generate report:\n\n{error_msg}")

        # Re-enable buttons
        self.generate_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.select_output_button.setEnabled(True)

    def process_all_plots(self):
        """Process all plot folders and generate per-plot summaries."""
        if not self.folder_path:
            QMessageBox.warning(self, "No Folder Selected", "Please select the Volume folder first.")
            return

        # Find all Plot_ folders
        plot_folders = []
        for item in os.listdir(self.folder_path):
            item_path = os.path.join(self.folder_path, item)
            if os.path.isdir(item_path) and item.startswith("Plot_"):
                plot_folders.append(item_path)

        if not plot_folders:
            QMessageBox.warning(self, "No Plot Folders", "No Plot_ folders found in the selected directory.")
            return

        plot_folders.sort()

        # Disable buttons during processing
        self.generate_button.setEnabled(False)
        self.process_all_button.setEnabled(False)
        self.select_folder_button.setEnabled(False)
        self.select_output_button.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Processing {len(plot_folders)} plots...")

        # Clear previous results
        self.results_text.clear()

        # Start batch processing in background thread
        format_type = 'csv' if 'CSV' in self.format_combo.currentText() else 'text'
        include_sections = self.section_checkbox.isChecked()
        self.batch_thread = BatchPlotProcessor(plot_folders, format_type, include_sections)
        self.batch_thread.progress.connect(self.progress_bar.setValue)
        self.batch_thread.finished.connect(self.on_batch_finished)
        self.batch_thread.error.connect(self.on_batch_error)
        self.batch_thread.start()

    def on_batch_error(self, error_msg):
        """Handle batch processing error."""
        # Print to console for debugging
        print(f"ERROR: Batch processing failed - {error_msg}")
        import traceback
        traceback.print_exc()

        # Hide progress bar
        self.progress_bar.setVisible(False)

        # Show error
        self.status_label.setText(f"Error in batch processing: {error_msg}")
        QMessageBox.critical(self, "Batch Processing Error", f"Failed to complete batch processing:\n\n{error_msg}")

        # Re-enable buttons
        self.generate_button.setEnabled(True)
        self.process_all_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.select_output_button.setEnabled(True)

    def clear_results(self):
        """Clear the results display."""
        self.results_text.clear()
        self.status_label.setText("Results cleared. Ready to generate new report.")

    def on_batch_finished(self, summary_text, saved_files):
        """Handle successful batch processing."""
        # Hide progress bar
        self.progress_bar.setVisible(False)

        # Display results
        self.results_text.setPlainText(summary_text)
        self.status_label.setText(f"Batch processing completed. {len(saved_files)} reports generated.")

        # Re-enable buttons
        self.generate_button.setEnabled(True)
        self.process_all_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.select_output_button.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for better cross-platform appearance

    window = VolumeReportGUI()
    window.show()

    sys.exit(app.exec())
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for better cross-platform appearance

    window = VolumeReportGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()