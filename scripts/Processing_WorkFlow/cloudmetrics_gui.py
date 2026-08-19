import sys
import os
import glob
import shutil
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, QProgressBar, QListWidget, QMessageBox
)
from PySide6.QtCore import QThread, Signal

class CloudMetricsWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    finished_signal = Signal()

    def __init__(self, exe_path, las_files, output_dir):
        super().__init__()
        self.exe_path = exe_path
        self.las_files = las_files
        self.output_dir = output_dir

    def run(self):
        total = len(self.las_files)
        for idx, las_file in enumerate(self.las_files):
            metrics_csv_individual = os.path.join(self.output_dir, os.path.basename(las_file).replace('.las', '_metrics.csv'))
            cmd = [self.exe_path, '/new', '/id', '/verbose', las_file, metrics_csv_individual]
            self.log_signal.emit(f'Running: {" ".join(cmd)}')
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
            self.log_signal.emit(f'STDOUT: {result.stdout}')
            self.log_signal.emit(f'STDERR: {result.stderr}')
            self.log_signal.emit(f'Return code: {result.returncode}')
            if result.returncode != 0:
                self.log_signal.emit(f'CloudMetrics failed for {las_file} with error code {result.returncode}.')
            else:
                self.log_signal.emit(f'CloudMetrics completed successfully for {las_file}.')
            self.progress_signal.emit(idx + 1, total)
        self.finished_signal.emit()

class CloudMetricsApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('CloudMetrics Batch GUI')
        self.resize(700, 500)
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        # Executable
        exe_row = QHBoxLayout()
        self.exe_edit = QLineEdit()
        exe_btn = QPushButton('Browse...')
        exe_btn.clicked.connect(self.pick_exe)
        exe_row.addWidget(QLabel('CloudMetrics.exe:'))
        exe_row.addWidget(self.exe_edit)
        exe_row.addWidget(exe_btn)
        layout.addLayout(exe_row)
        # Input folder
        in_row = QHBoxLayout()
        self.in_edit = QLineEdit()
        in_btn = QPushButton('Browse...')
        in_btn.clicked.connect(self.pick_input)
        in_row.addWidget(QLabel('Normalized LAS Folder:'))
        in_row.addWidget(self.in_edit)
        in_row.addWidget(in_btn)
        layout.addLayout(in_row)
        # Output folder
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        out_btn = QPushButton('Browse...')
        out_btn.clicked.connect(self.pick_output)
        out_row.addWidget(QLabel('Output Folder:'))
        out_row.addWidget(self.out_edit)
        out_row.addWidget(out_btn)
        layout.addLayout(out_row)
        # List of LAS files
        self.las_list = QListWidget()
        layout.addWidget(QLabel('LAS files to process:'))
        layout.addWidget(self.las_list)
        # Scan button
        scan_btn = QPushButton('Scan for LAS files')
        scan_btn.clicked.connect(self.scan_las_files)
        layout.addWidget(scan_btn)
        # Run button
        self.run_btn = QPushButton('Run CloudMetrics')
        self.run_btn.clicked.connect(self.run_cloudmetrics)
        layout.addWidget(self.run_btn)
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(QLabel('Log Output:'))
        layout.addWidget(self.log_output)
        self.setLayout(layout)

    def pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select CloudMetrics.exe', '', 'Executables (*.exe)')
        if path:
            self.exe_edit.setText(path)

    def pick_input(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Normalized LAS Folder')
        if path:
            self.in_edit.setText(path)

    def pick_output(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
        if path:
            self.out_edit.setText(path)

    def scan_las_files(self):
        folder = self.in_edit.text().strip()
        if not os.path.isdir(folder):
            QMessageBox.warning(self, 'Invalid Folder', 'Please select a valid normalized LAS folder.')
            return
        las_files = glob.glob(os.path.join(folder, '*.las'))
        self.las_list.clear()
        for f in las_files:
            self.las_list.addItem(f)
        self.log_output.append(f'Found {len(las_files)} LAS files.')

    def run_cloudmetrics(self):
        exe_path = self.exe_edit.text().strip()
        in_folder = self.in_edit.text().strip()
        out_folder = self.out_edit.text().strip()
        if not os.path.isfile(exe_path):
            QMessageBox.warning(self, 'Missing Executable', 'CloudMetrics.exe not found.')
            return
        if not os.path.isdir(in_folder):
            QMessageBox.warning(self, 'Missing Input', 'Normalized LAS folder not found.')
            return
        if not os.path.isdir(out_folder):
            QMessageBox.warning(self, 'Missing Output', 'Output folder not found.')
            return
        las_files = [self.las_list.item(i).text() for i in range(self.las_list.count())]
        if not las_files:
            QMessageBox.warning(self, 'No LAS Files', 'No LAS files to process.')
            return
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log_output.append('Starting CloudMetrics batch processing...')
        self.worker = CloudMetricsWorker(exe_path, las_files, out_folder)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, done, total):
        if total > 0:
            self.progress.setValue(int(100 * done / total))
        else:
            self.progress.setValue(0)

    def on_finished(self):
        self.run_btn.setEnabled(True)
        self.progress.setValue(100)
        self.log_output.append('All CloudMetrics processing complete.')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = CloudMetricsApp()
    win.show()
    sys.exit(app.exec())
