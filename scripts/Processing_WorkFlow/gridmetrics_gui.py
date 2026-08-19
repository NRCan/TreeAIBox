import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QTextEdit, QFileDialog, QLineEdit, QProgressBar, QMessageBox
)

from PySide6.QtCore import Qt, QThread, Signal

class GridMetricsWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self, las_files, normalized_dir, gridmetrics_exe, output_dir, ground_model, height_break, cell_size):
        super().__init__()
        self.las_files = las_files
        self.normalized_dir = normalized_dir
        self.gridmetrics_exe = gridmetrics_exe
        self.output_dir = output_dir
        self.ground_model = ground_model
        self.height_break = height_break
        self.cell_size = cell_size
        self._is_running = True

    def run(self):
        total = len(self.las_files)
        for idx, las_file in enumerate(self.las_files):
            if not self._is_running:
                break
            stand_file_full_name = os.path.join(self.normalized_dir, las_file)
            stand_file_no_ext = os.path.splitext(las_file)[0]
            output_base_name = os.path.join(self.output_dir, f'{stand_file_no_ext}_gridmetrics')
            rel_gridmetrics_exe = os.path.relpath(self.gridmetrics_exe, start=os.getcwd())
            if not os.path.dirname(rel_gridmetrics_exe):
                rel_gridmetrics_exe = f'.\\{rel_gridmetrics_exe}'
            rel_output_base_name = os.path.relpath(output_base_name, start=os.getcwd())
            rel_stand_file_full_name = os.path.relpath(stand_file_full_name, start=os.getcwd())
            cmd_str = (
                f'& "{rel_gridmetrics_exe}" /raster:mean,cover,p90 /ascii /minht:{self.height_break} /verbose {self.ground_model} {self.height_break} {self.cell_size} '
                f'"{rel_output_base_name}" "{rel_stand_file_full_name}"'
            )
            self.log_signal.emit(f'\n[INFO] Running GridMetrics for: {las_file}\n')
            self.log_signal.emit(f'[DEBUG] Command: {cmd_str}\n')
            result = subprocess.run([
                'powershell',
                '-Command',
                cmd_str
            ], shell=True, capture_output=True, text=True)
            self.log_signal.emit(f'[STDOUT]\n{result.stdout[:500]}\n')
            self.log_signal.emit(f'[STDERR]\n{result.stderr}\n')
            if result.returncode != 0:
                self.log_signal.emit(f'[ERROR] GridMetrics failed for {stand_file_full_name} with error code {result.returncode}\n')
            else:
                self.log_signal.emit(f'[SUCCESS] GridMetrics completed for {stand_file_full_name}\n')
            self.progress_signal.emit(int((idx + 1) / total * 100))
        self.finished_signal.emit()

    def stop(self):
        self._is_running = False

class GridMetricsGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GridMetrics Batch Processor')
        self.resize(800, 600)
        self.init_ui()
        self.worker = None

    def init_ui(self):
        layout = QVBoxLayout()
        # Directory selection
        dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText('Select normalized LAS directory...')
        dir_btn = QPushButton('Browse')
        dir_btn.clicked.connect(self.browse_dir)
        dir_layout.addWidget(QLabel('Normalized LAS Dir:'))
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(dir_btn)
        layout.addLayout(dir_layout)
        # Output directory
        out_layout = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText('Select output directory...')
        out_btn = QPushButton('Browse')
        out_btn.clicked.connect(self.browse_out_dir)
        out_layout.addWidget(QLabel('Output Dir:'))
        out_layout.addWidget(self.out_edit)
        out_layout.addWidget(out_btn)
        layout.addLayout(out_layout)
        # Parameters
        param_layout = QHBoxLayout()
        self.cell_size_edit = QLineEdit('15.0')
        self.height_break_edit = QLineEdit('0.0')
        param_layout.addWidget(QLabel('Cell Size:'))
        param_layout.addWidget(self.cell_size_edit)
        param_layout.addWidget(QLabel('Height Break:'))
        param_layout.addWidget(self.height_break_edit)
        layout.addLayout(param_layout)
        # LAS file list
        self.las_list = QListWidget()
        layout.addWidget(QLabel('LAS Files:'))
        layout.addWidget(self.las_list)
        # Progress bar
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(QLabel('Log Output:'))
        layout.addWidget(self.log_output)
        # Run button
        run_btn = QPushButton('Run GridMetrics')
        run_btn.clicked.connect(self.run_gridmetrics)
        layout.addWidget(run_btn)
        self.setLayout(layout)

    def browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select Normalized LAS Directory')
        if dir_path:
            self.dir_edit.setText(dir_path)
            self.scan_las_files()

    def browse_out_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select Output Directory')
        if dir_path:
            self.out_edit.setText(dir_path)

    def scan_las_files(self):
        self.las_list.clear()
        dir_path = self.dir_edit.text()
        if not dir_path or not os.path.isdir(dir_path):
            return
        las_files = [f for f in os.listdir(dir_path) if f.lower().endswith('.las')]
        self.las_list.addItems(las_files)

    def run_gridmetrics(self):
        normalized_dir = self.dir_edit.text()
        output_dir = self.out_edit.text()
        if not normalized_dir or not os.path.isdir(normalized_dir):
            QMessageBox.warning(self, 'Error', 'Please select a valid normalized LAS directory.')
            return
        if not output_dir:
            output_dir = os.path.join(normalized_dir, 'gridmetrics')
            os.makedirs(output_dir, exist_ok=True)
            self.out_edit.setText(output_dir)
        las_files = [self.las_list.item(i).text() for i in range(self.las_list.count())]
        if not las_files:
            QMessageBox.warning(self, 'Error', 'No LAS files found.')
            return
        # Find GridMetrics.exe
        exe_candidates = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'Fusion', 'GridMetrics.exe'),
            os.path.join(os.path.dirname(__file__), '..', '..', 'Fusion', 'GridMetrics64.exe'),
        ]
        gridmetrics_exe = None
        for exe in exe_candidates:
            if os.path.isfile(exe):
                gridmetrics_exe = exe
                break
        if not gridmetrics_exe:
            QMessageBox.critical(self, 'Error', 'GridMetrics.exe not found in Fusion folder.')
            return
        ground_model = '*'
        height_break = self.height_break_edit.text().strip() or '0.0'
        cell_size = self.cell_size_edit.text().strip() or '15.0'
        self.progress.setValue(0)
        self.log_output.clear()
        self.worker = GridMetricsWorker(las_files, normalized_dir, gridmetrics_exe, output_dir, ground_model, height_break, cell_size)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self):
        self.progress.setValue(100)
        self.log_output.append('\n[INFO] Batch processing complete.')
        QMessageBox.information(self, 'Done', 'GridMetrics batch processing complete!')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = GridMetricsGUI()
    gui.show()
    sys.exit(app.exec())