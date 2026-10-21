
"""
GroundFilter/DTM module: provides functions to run FUSION's GroundFilter and DTM generation tools programmatically.

Functions:
    run_groundfilter(...): Runs GroundFilter and returns the ground points LAS path.
    run_dtm_generation(...): Runs DTM generation and returns the DTM file path.

If run as a script, launches the GUI.
"""

import sys
import os
import sqlite3
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, QMessageBox, QSpinBox, QDoubleSpinBox, QProgressBar, QSizePolicy, QTabWidget, QCheckBox
)
from PySide6.QtCore import QThread, Signal, QObject, Slot
def run_groundfilter(fusion_dir, input_las, output_root, cell_size=10.0, gparam=None, wparam=None, iterations=8, overwrite=False):
    """
    Run FUSION GroundFilter and return the output ground points LAS path.
    Raises RuntimeError on failure.
    """
    if not os.path.isfile(input_las):
        raise FileNotFoundError(f"Input LAS file not found: {input_las}")
    exe_path = os.path.join(fusion_dir, 'GroundFilter64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'GroundFilter.exe')
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"GroundFilter.exe not found in Fusion folder: {fusion_dir}")
    # Use provided output_root or fall back to global default or CWD
    if not output_root:
        output_root = globals().get('output_root', os.getcwd())
    input_base = os.path.splitext(os.path.basename(input_las))[0]
    las_folder = os.path.join(output_root, input_base)
    ground_points_dir = os.path.join(las_folder, 'Ground Points')
    os.makedirs(ground_points_dir, exist_ok=True)
    out_path = os.path.join(ground_points_dir, f'{input_base}_ground.las')
    if os.path.isfile(out_path) and not overwrite:
        raise FileExistsError(f"Ground points LAS already exists: {out_path}")
    cmd = [exe_path]
    if gparam:
        cmd.append(f'/gparam:{gparam}')
    if wparam:
        cmd.append(f'/wparam:{wparam}')
    if iterations:
        cmd.append(f'/iterations:{iterations}')
    cmd.extend([out_path, str(cell_size), input_las])
    result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"GroundFilter failed: {result.stderr}")
    return out_path

def run_dtm_generation(fusion_dir, ground_las, output_root, cell_size=10.0, xyunits='M', zunits='M', coordsys=1, zone=20, horizdatum=2, vertdatum=2, extra_params=None, overwrite=False):
    """
    Run FUSION GridSurfaceCreate to generate DTM from ground points LAS. Returns DTM file path.
    Raises RuntimeError on failure.
    """
    if not os.path.isfile(ground_las):
        raise FileNotFoundError(f"Ground points LAS file not found: {ground_las}")
    exe_path = os.path.join(fusion_dir, "GridSurfaceCreate64.exe")
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, "GridSurfaceCreate.exe")
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"GridSurfaceCreate.exe not found in Fusion folder: {fusion_dir}")
    # Use provided output_root or fall back to global default or CWD
    if not output_root:
        output_root = globals().get('output_root', os.getcwd())
    input_base = os.path.splitext(os.path.basename(ground_las))[0].replace('_ground', '')
    las_folder = os.path.join(output_root, input_base)
    dtm_dir = os.path.join(las_folder, 'DTM')
    os.makedirs(dtm_dir, exist_ok=True)
    out_dtm = os.path.join(dtm_dir, f'{input_base}.dtm')
    if os.path.isfile(out_dtm) and not overwrite:
        raise FileExistsError(f"DTM file already exists: {out_dtm}")
    cmd = [exe_path]
    if extra_params:
        cmd.extend(extra_params.split())
    cmd.extend([
        out_dtm,
        str(cell_size),
        xyunits,
        zunits,
        str(coordsys),
        str(zone),
        str(horizdatum),
        str(vertdatum),
        ground_las
    ])
    result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"DTM generation failed: {result.stderr}")
    return out_dtm

class LasInfoWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, exe_path, las_path):
        super(LasInfoWorker, self).__init__()
        self.exe_path = exe_path
        self.las_path = las_path

    def run(self):
        cmd = [self.exe_path, self.las_path]
        self.log_signal.emit(f'Running command: {" ".join(cmd)}')
        try:
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
            self.log_signal.emit(f'STDOUT: {result.stdout[:5000]}')
            self.log_signal.emit(f'STDERR: {result.stderr[:500]}')
            self.log_signal.emit(f'Return code: {result.returncode}')
            self.finished_signal.emit(result.returncode == 0)
        except Exception as e:
            self.log_signal.emit(f'Error running lasinfo: {e}')
            self.finished_signal.emit(False)

class TIFWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, exe_path, dtm_path):
        super(TIFWorker, self).__init__()
        self.exe_path = exe_path
        self.dtm_path = dtm_path

    def run(self):
        cmd = [self.exe_path, self.dtm_path]
        self.log_signal.emit(f'Running command: {" ".join(cmd)}')
        try:
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
            self.log_signal.emit(f'STDOUT: {result.stdout[:500]}')
            self.log_signal.emit(f'STDERR: {result.stderr[:500]}')
            self.log_signal.emit(f'Return code: {result.returncode}')
            if result.returncode == 0:
                self.log_signal.emit('DTM to TIFF conversion complete.')
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit('DTM2TIF failed.')
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f'Error running DTM2TIF: {e}')
            self.finished_signal.emit(False)

def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_settings.db')

def ns_key(key):
    return f'groundfilter_gui:{key}'

def save_setting(key, value):
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (ns_key(key), value))
    conn.commit()
    conn.close()

def load_setting(key):
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('SELECT value FROM settings WHERE key=?', (ns_key(key),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ''

class DTMWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, exe_path, ground_las, out_dtm, cell_size, xyunits, zunits, coordsys, zone, horizdatum, vertdatum, extra_params):
        super(DTMWorker, self).__init__()
        self.exe_path = exe_path
        self.ground_las = ground_las
        self.out_dtm = out_dtm
        self.cell_size = cell_size
        self.xyunits = xyunits
        self.zunits = zunits
        self.coordsys = coordsys
        self.zone = zone
        self.horizdatum = horizdatum
        self.vertdatum = vertdatum
        self.extra_params = extra_params

    def run(self):
        cmd = [self.exe_path]
        if self.extra_params:
            cmd.extend(self.extra_params.split())
        cmd.extend([
            self.out_dtm,
            str(self.cell_size),
            self.xyunits,
            self.zunits,
            str(self.coordsys),
            str(self.zone),
            str(self.horizdatum),
            str(self.vertdatum),
            self.ground_las
        ])
        self.log_signal.emit(f'Running command: {" ".join(cmd)}')
        try:
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
            self.log_signal.emit(f'STDOUT: {result.stdout[:500]}')
            self.log_signal.emit(f'STDERR: {result.stderr[:500]}')
            self.log_signal.emit(f'Return code: {result.returncode}')
            if result.returncode == 0:
                self.log_signal.emit('DTM generation complete.')
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit('DTM generation failed.')
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f'Error running GridSurfaceCreate: {e}')
            self.finished_signal.emit(False)

class GroundFilterWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, exe_path, in_path, out_path, cell_size, gparam, wparam, iterations):
        super(GroundFilterWorker, self).__init__()
        self.exe_path = exe_path
        self.in_path = in_path
        self.out_path = out_path
        self.cell_size = cell_size
        self.gparam = gparam
        self.wparam = wparam
        self.iterations = iterations

    def run(self):
        cmd = [self.exe_path]
        if self.gparam:
            cmd.append(f'/gparam:{self.gparam}')
        if self.wparam:
            cmd.append(f'/wparam:{self.wparam}')
        if self.iterations:
            cmd.append(f'/iterations:{self.iterations}')
        cmd.extend([self.out_path, str(self.cell_size), self.in_path])
        self.log_signal.emit(f'Running command: {" ".join(cmd)}')
        try:
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
            self.log_signal.emit(f'STDOUT: {result.stdout[:500]}')
            self.log_signal.emit(f'STDERR: {result.stderr[:500]}')
            self.log_signal.emit(f'Return code: {result.returncode}')
            if result.returncode == 0:
                self.log_signal.emit('Ground points file generation complete.')
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit('GroundFilter failed.')
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f'Error running GroundFilter: {e}')
            self.finished_signal.emit(False)



class GroundFilterApp(QWidget):
    def run_dtm_process(self):
        # Run DTM Generation from the DTM tab (independent of full workflow)
        output_root = self.output_root_edit.text().strip()
        fusion_dir = self.fusion_dir_edit.text().strip()
        # Use the auto-detected ground points LAS path
        in_path = self.in_edit.text().strip()
        if not in_path or not os.path.isfile(in_path):
            self.dtm_log('ERROR: Input LAS file not found. Please run GroundFilter first.')
            QMessageBox.warning(self, 'Missing Input', 'Input LAS file not found. Please run GroundFilter first.')
            return
        if not output_root:
            self.dtm_log('ERROR: Output root folder not specified.')
            QMessageBox.warning(self, 'Missing Output Root', 'Please select the Output Root Folder.')
            return
        if not fusion_dir:
            self.dtm_log('ERROR: Fusion folder not specified.')
            QMessageBox.warning(self, 'Missing Fusion Folder', 'Please select the Fusion folder.')
            return
        input_base = os.path.splitext(os.path.basename(in_path))[0]
        las_folder = os.path.join(output_root, input_base)
        ground_points_dir = os.path.join(las_folder, 'Ground Points')
        ground_las = os.path.join(ground_points_dir, f'{input_base}_ground.las')
        if not os.path.isfile(ground_las):
            self.dtm_log(f'ERROR: Ground points LAS file not found: {ground_las}')
            QMessageBox.warning(self, 'Missing Input', f'Ground points LAS file not found: {ground_las}')
            return
        dtm_dir = os.path.join(las_folder, 'DTM')
        os.makedirs(dtm_dir, exist_ok=True)
        out_dtm = os.path.join(dtm_dir, f'{input_base}.dtm')
        # Save paths to UI for user visibility
        self.dtm_ground_edit.setText(ground_las)
        self.dtm_out_edit.setText(out_dtm)
        exe_path = os.path.join(fusion_dir, "GridSurfaceCreate64.exe")
        if not os.path.isfile(exe_path):
            exe_path = os.path.join(fusion_dir, "GridSurfaceCreate.exe")
            if not os.path.isfile(exe_path):
                self.dtm_log("ERROR: GridSurfaceCreate executable not found in Fusion folder.")
                QMessageBox.warning(self, 'Missing Executable', 'GridSurfaceCreate.exe not found in Fusion folder.')
                return
        cell_size = self.dtm_cellsize_edit.value()
        xyunits = self.dtm_xyunits_edit.text().strip() or 'M'
        zunits = self.dtm_zunits_edit.text().strip() or 'M'
        coordsys = self.dtm_coordsys_edit.value()
        zone = self.dtm_zone_edit.value()
        horizdatum = self.dtm_horizdatum_edit.value()
        vertdatum = self.dtm_vertdatum_edit.value()
        extra_params = self.dtm_extra_edit.text().strip()
        tif_checked = self.dtm_tif_checkbox.isChecked()
        tif_exe_path = os.path.join(fusion_dir, "DTM2TIF64.exe")
        if not os.path.isfile(tif_exe_path):
            tif_exe_path = os.path.join(fusion_dir, "DTM2TIF.exe")
            if not os.path.isfile(tif_exe_path):
                self.dtm_log("ERROR: DTM2TIF executable not found in Fusion folder.")
                QMessageBox.warning(self, 'Missing Executable', 'DTM2TIF.exe not found in Fusion folder.')
                return
        self.dtm_log(f'Running DTM Generation: {exe_path} {ground_las} -> {out_dtm}')
        self.dtm_run_btn.setEnabled(False)
        self.dtm_progress_bar.setVisible(True)
        self.dtm_worker = DTMWorker(
            exe_path, ground_las, out_dtm, cell_size, xyunits, zunits, coordsys, zone, horizdatum, vertdatum, extra_params
        )
        self.dtm_worker.log_signal.connect(self.dtm_log)
        self.dtm_worker.finished_signal.connect(lambda success: self.on_dtm_tab_finished(success, tif_checked, tif_exe_path, out_dtm))
        self.dtm_worker.start()

    def on_dtm_tab_finished(self, success, tif_checked, tif_exe_path, out_dtm):
        self.dtm_run_btn.setEnabled(True)
        self.dtm_progress_bar.setVisible(False)
        if not success:
            self.dtm_log('DTM Generation failed.')
            return
        self.dtm_log('DTM Generation finished successfully.')
        if tif_checked:
            self.dtm_log('Starting DTM to TIFF conversion...')
            self.dtm_progress_bar.setVisible(True)
            self.tif_worker = TIFWorker(tif_exe_path, out_dtm)
            self.tif_worker.log_signal.connect(self.dtm_log)
            self.tif_worker.finished_signal.connect(self.on_dtm_tab_tif_finished)
            self.tif_worker.start()
        else:
            self.dtm_log('--- DTM Tab Workflow Complete ---')

    def on_dtm_tab_tif_finished(self, success):
        self.dtm_progress_bar.setVisible(False)
        if success:
            self.dtm_log('DTM to TIFF process finished successfully.')
            self.dtm_log('--- DTM Tab Workflow Complete ---')
        else:
            self.dtm_log('DTM to TIFF process finished with errors.')

    def dtm_log(self, msg):
        self.dtm_log_output.append(msg)
        print('[DTM]', msg)
    def pick_output_root_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Output Root Folder', '', QFileDialog.ShowDirsOnly)
        if folder:
            self.output_root_edit.setText(folder)
            save_setting('output_root_folder', folder)

    def pick_lasinfo_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select LAS file', '', 'LAS Files (*.las);;All Files (*)')
        if path:
            self.lasinfo_las_edit.setText(path)
            save_setting('lasinfo_las_path', path)

    def pick_lasinfo_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select lasinfo.exe', '', 'Executables (*.exe)')
        if path:
            self.lasinfo_exe_edit.setText(path)
            save_setting('lasinfo_exe_path', path)

    def run_lasinfo(self):
        las_path = self.lasinfo_las_edit.text().strip()
        exe_path = self.lasinfo_exe_edit.text().strip()
        save_setting('lasinfo_las_path', las_path)
        save_setting('lasinfo_exe_path', exe_path)
        if not os.path.isfile(las_path):
            QMessageBox.warning(self, 'Missing Input', f'LAS file not found: {las_path}')
            self.lasinfo_log(f'LAS file not found: {las_path}')
            return
        if not exe_path or not os.path.isfile(exe_path):
            QMessageBox.warning(self, 'Missing Executable', f'lasinfo.exe not found: {exe_path}')
            self.lasinfo_log(f'lasinfo.exe not found: {exe_path}')
            return
        self.lasinfo_run_btn.setEnabled(False)
        self.lasinfo_progress.setVisible(True)
        self.lasinfo_log('Starting lasinfo...')
        self.lasinfo_worker = LasInfoWorker(exe_path, las_path)
        self.lasinfo_worker.log_signal.connect(self.lasinfo_log)
        self.lasinfo_worker.finished_signal.connect(self.on_lasinfo_finished)
        self.lasinfo_worker.start()

    def lasinfo_log(self, msg):
        self.lasinfo_log_output.append(msg)
        print('[LASINFO]', msg)

    def on_lasinfo_finished(self, success):
        self.lasinfo_run_btn.setEnabled(True)
        self.lasinfo_progress.setVisible(False)
        if success:
            self.lasinfo_log('lasinfo finished successfully.')
        else:
            self.lasinfo_log('lasinfo finished with errors.')
    # Removed pick_dtm_tif_exe_file; exe path is set automatically
    def pick_dtm_ground_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Ground Points LAS', '', 'LAS Files (*.las);;All Files (*)')
        if path:
            self.dtm_ground_edit.setText(path)
            save_setting('dtm_ground_las', path)
    def __init__(self):
        super(GroundFilterApp, self).__init__()
        self.setWindowTitle('GroundFilter & DTM Generator')
        self.resize(750, 500)
        self.worker = None
        self.dtm_worker = None
        self.fusion_dir = ''
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout()
        # Fusion folder picker
        fusion_row = QHBoxLayout()
        self.fusion_dir_edit = QLineEdit()
        self.fusion_dir_edit.setReadOnly(True)
        fusion_btn = QPushButton('Browse...')
        fusion_btn.clicked.connect(self.pick_fusion_folder)
        fusion_row.addWidget(QLabel('Fusion Folder:'))
        fusion_row.addWidget(self.fusion_dir_edit)
        fusion_row.addWidget(fusion_btn)
        main_layout.addLayout(fusion_row)

        # Output root folder picker
        output_row = QHBoxLayout()
        self.output_root_edit = QLineEdit()
        self.output_root_edit.setReadOnly(True)
        output_btn = QPushButton('Browse...')
        output_btn.clicked.connect(self.pick_output_root_folder)
        output_row.addWidget(QLabel('Output Root Folder:'))
        output_row.addWidget(self.output_root_edit)
        output_row.addWidget(output_btn)
        main_layout.addLayout(output_row)

        # Add Run Full Workflow button
        self.run_full_btn = QPushButton('Run Full Workflow (GroundFilter + DTM)')
        self.run_full_btn.clicked.connect(self.run_full_workflow)
        main_layout.addWidget(self.run_full_btn)

        self.tabs = QTabWidget()
        # --- LAS Info Tab ---
        self.lasinfo_tab = QWidget()
        self.lasinfo_layout = QVBoxLayout()
        self.lasinfo_las_edit = QLineEdit()
        lasinfo_las_btn = QPushButton('Browse...')
        lasinfo_las_btn.clicked.connect(self.pick_lasinfo_file)
        self.lasinfo_layout.addLayout(self._row('LAS file:', self.lasinfo_las_edit, lasinfo_las_btn))
        self.lasinfo_exe_edit = QLineEdit()
        lasinfo_exe_btn = QPushButton('Browse...')
        lasinfo_exe_btn.clicked.connect(self.pick_lasinfo_exe)
        self.lasinfo_layout.addLayout(self._row('lasinfo.exe:', self.lasinfo_exe_edit, lasinfo_exe_btn))
        self.lasinfo_run_btn = QPushButton('Run lasinfo')
        self.lasinfo_run_btn.clicked.connect(self.run_lasinfo)
        self.lasinfo_layout.addWidget(self.lasinfo_run_btn)
        self.lasinfo_progress = QProgressBar()
        self.lasinfo_progress.setMinimum(0)
        self.lasinfo_progress.setMaximum(0)
        self.lasinfo_progress.setVisible(False)
        self.lasinfo_progress.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lasinfo_layout.addWidget(self.lasinfo_progress)
        self.lasinfo_log_output = QTextEdit()
        self.lasinfo_log_output.setReadOnly(True)
        self.lasinfo_log_output.setMinimumHeight(100)
        self.lasinfo_layout.addWidget(QLabel('Log Output:'))
        self.lasinfo_layout.addWidget(self.lasinfo_log_output)
        self.lasinfo_tab.setLayout(self.lasinfo_layout)

        # --- GroundFilter Tab ---
        self.gf_tab = QWidget()
        self.gf_layout = QVBoxLayout()
        self.in_edit = QLineEdit()
        in_btn = QPushButton('Browse...')
        in_btn.clicked.connect(self.pick_input_file)
        self.gf_layout.addLayout(self._row('Input LAS:', self.in_edit, in_btn))
    # Output LAS field removed; output is auto-generated in Ground Point subfolder
        self.cellsize_edit = QDoubleSpinBox()
        self.cellsize_edit.setDecimals(2)
        self.cellsize_edit.setRange(0.01, 1000.0)
        self.cellsize_edit.setValue(10.0)
        self.gf_layout.addLayout(self._row('Cell Size:', self.cellsize_edit, None))
        self.gparam_edit = QLineEdit()
        self.gparam_edit.setPlaceholderText('e.g. 0')
        self.gf_layout.addLayout(self._row('gparam (optional):', self.gparam_edit, None))
        self.wparam_edit = QLineEdit()
        self.wparam_edit.setPlaceholderText('e.g. 0.5')
        self.gf_layout.addLayout(self._row('wparam (optional):', self.wparam_edit, None))
        self.iter_edit = QSpinBox()
        self.iter_edit.setRange(1, 100)
        self.iter_edit.setValue(8)
        self.gf_layout.addLayout(self._row('iterations (optional):', self.iter_edit, None))
        self.run_btn = QPushButton('Run GroundFilter')
        self.run_btn.clicked.connect(self.run_process)
        self.gf_layout.addWidget(self.run_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.gf_layout.addWidget(self.progress_bar)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(100)
        self.gf_layout.addWidget(QLabel('Log Output:'))
        self.gf_layout.addWidget(self.log_output)
        self.gf_tab.setLayout(self.gf_layout)

        # --- DTM Generation Tab ---
        self.dtm_tab = QWidget()
        self.dtm_layout = QVBoxLayout()
        # Remove manual ground points LAS picker, use auto-detected path
        self.dtm_ground_edit = QLineEdit()
        self.dtm_ground_edit.setReadOnly(True)
        self.dtm_layout.addLayout(self._row('Ground Points LAS:', self.dtm_ground_edit, None))
        # Remove output DTM picker, auto-generate path
        self.dtm_out_edit = QLineEdit()
        self.dtm_out_edit.setReadOnly(True)
        self.dtm_layout.addLayout(self._row('Output DTM:', self.dtm_out_edit, None))
        self.dtm_tif_checkbox = QCheckBox('Also generate GeoTIFF (.tif) from DTM')
        self.dtm_tif_checkbox.stateChanged.connect(lambda: save_setting('dtm_tif_checked', str(self.dtm_tif_checkbox.isChecked())))
        self.dtm_layout.addWidget(self.dtm_tif_checkbox)
        self.dtm_cellsize_edit = QDoubleSpinBox()
        self.dtm_cellsize_edit.setDecimals(2)
        self.dtm_cellsize_edit.setRange(0.01, 1000.0)
        self.dtm_cellsize_edit.setValue(10.0)
        self.dtm_layout.addLayout(self._row('Cell Size:', self.dtm_cellsize_edit, None))
        # XY units
        self.dtm_xyunits_edit = QLineEdit()
        self.dtm_xyunits_edit.setText('M')
        self.dtm_layout.addLayout(self._row('XY Units (M/F):', self.dtm_xyunits_edit, None))
        # Z units
        self.dtm_zunits_edit = QLineEdit()
        self.dtm_zunits_edit.setText('M')
        self.dtm_layout.addLayout(self._row('Z Units (M/F):', self.dtm_zunits_edit, None))
        # Coordinate system
        self.dtm_coordsys_edit = QSpinBox()
        self.dtm_coordsys_edit.setRange(0, 2)
        self.dtm_coordsys_edit.setValue(1)  # 1 = UTM
        self.dtm_layout.addLayout(self._row('CoordSys (0=Unknown,1=UTM,2=State Plane):', self.dtm_coordsys_edit, None))
        # Zone
        self.dtm_zone_edit = QSpinBox()
        self.dtm_zone_edit.setRange(0, 60)
        self.dtm_zone_edit.setValue(20)
        self.dtm_layout.addLayout(self._row('Zone:', self.dtm_zone_edit, None))
        # Horizontal datum
        self.dtm_horizdatum_edit = QSpinBox()
        self.dtm_horizdatum_edit.setRange(0, 2)
        self.dtm_horizdatum_edit.setValue(2)  # 2 = NAD83
        self.dtm_layout.addLayout(self._row('HorizDatum (0=Unknown,1=NAD27,2=NAD83):', self.dtm_horizdatum_edit, None))
        # Vertical datum
        self.dtm_vertdatum_edit = QSpinBox()
        self.dtm_vertdatum_edit.setRange(0, 3)
        self.dtm_vertdatum_edit.setValue(2)  # 2 = NAVD88
        self.dtm_vertdatum_edit.setToolTip(
            'FUSION only supports: 0=Unknown, 1=NGVD29, 2=NAVD88, 3=GRS80.\n'
            'If your vertical datum is CGVD2013, select 0 (Unknown) and document the actual datum elsewhere.'
        )
        self.dtm_layout.addLayout(self._row('VertDatum (0=Unknown,1=NGVD29,2=NAVD88,3=GRS80):', self.dtm_vertdatum_edit, None))
        self.dtm_extra_edit = QLineEdit()
        self.dtm_extra_edit.setPlaceholderText('Extra params (optional)')
        self.dtm_layout.addLayout(self._row('Extra Params:', self.dtm_extra_edit, None))
        self.dtm_run_btn = QPushButton('Run DTM Generation')
        self.dtm_run_btn.clicked.connect(self.run_dtm_process)
        self.dtm_layout.addWidget(self.dtm_run_btn)
        self.dtm_progress_bar = QProgressBar()
        self.dtm_progress_bar.setMinimum(0)
        self.dtm_progress_bar.setMaximum(0)
        self.dtm_progress_bar.setVisible(False)
        self.dtm_progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.dtm_layout.addWidget(self.dtm_progress_bar)
        self.dtm_log_output = QTextEdit()
        self.dtm_log_output.setReadOnly(True)
        self.dtm_log_output.setMinimumHeight(100)
        self.dtm_layout.addWidget(QLabel('Log Output:'))
        self.dtm_layout.addWidget(self.dtm_log_output)
        self.dtm_tab.setLayout(self.dtm_layout)
        self.tabs.addTab(self.gf_tab, 'GroundFilter')
        self.tabs.addTab(self.dtm_tab, 'DTM Generation')
        self.tabs.addTab(self.lasinfo_tab, 'LAS Info')
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
    def pick_fusion_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Fusion Folder', '', QFileDialog.ShowDirsOnly)
        if folder:
            self.fusion_dir = folder
            self.fusion_dir_edit.setText(folder)
            save_setting('fusion_folder', folder)
    def run_full_workflow(self):
        # Disable the button to prevent double runs
        self.run_full_btn.setEnabled(False)
        self.log('--- Starting Full Workflow: GroundFilter + DTM Generation ---')
        # Step 1: Run GroundFilter with checks
        in_path = self.in_edit.text().strip()
        output_root = self.output_root_edit.text().strip()
        fusion_dir = self.fusion_dir_edit.text().strip()
        if not in_path or not os.path.isfile(in_path):
            self.log('ERROR: Input LAS file not found.')
            QMessageBox.warning(self, 'Missing Input', 'Input LAS file not found.')
            self.run_full_btn.setEnabled(True)
            return
        if not output_root:
            self.log('ERROR: Output root folder not specified.')
            QMessageBox.warning(self, 'Missing Output Root', 'Please select the Output Root Folder.')
            self.run_full_btn.setEnabled(True)
            return
        if not fusion_dir:
            self.log('ERROR: Fusion folder not specified.')
            QMessageBox.warning(self, 'Missing Fusion Folder', 'Please select the Fusion folder.')
            self.run_full_btn.setEnabled(True)
            return
        exe_path = os.path.join(fusion_dir, 'GroundFilter64.exe')
        if not os.path.isfile(exe_path):
            exe_path = os.path.join(fusion_dir, 'GroundFilter.exe')
        if not exe_path or not os.path.isfile(exe_path):
            self.log('ERROR: GroundFilter executable not found in Fusion folder.')
            QMessageBox.warning(self, 'Missing Executable', 'GroundFilter.exe not found in Fusion folder.')
            self.run_full_btn.setEnabled(True)
            return
        cell_size = self.cellsize_edit.value()
        gparam = self.gparam_edit.text().strip()
        wparam = self.wparam_edit.text().strip()
        iterations = self.iter_edit.value()
        input_base = os.path.splitext(os.path.basename(in_path))[0]
        las_folder = os.path.join(output_root, input_base)
        ground_points_dir = os.path.join(las_folder, 'Ground Points')
        os.makedirs(ground_points_dir, exist_ok=True)
        out_path = os.path.join(ground_points_dir, f'{input_base}_ground.las')
        # Check if ground points LAS exists
        if os.path.isfile(out_path):
            reply = QMessageBox.question(self, 'File Exists', f'Ground points LAS already exists:\n{out_path}\nOverwrite?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                self.log('User chose to skip GroundFilter step (file exists). Proceeding to DTM Generation...')
                self.on_full_groundfilter_finished(True, output_root, input_base, skip_groundfilter=True)
                return
            else:
                self.log('User chose to overwrite existing ground points LAS.')
        self.log(f'Running GroundFilter: {exe_path} {in_path} -> {out_path}')
        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        # Start GroundFilter worker
        self.worker = GroundFilterWorker(
            exe_path, in_path, out_path, cell_size, gparam, wparam, iterations
        )
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(lambda success: self.on_full_groundfilter_finished(success, output_root, input_base))
        self.worker.start()

    def on_full_groundfilter_finished(self, success, output_root, input_base, skip_groundfilter=False):
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if not success and not skip_groundfilter:
            self.log('GroundFilter failed. Aborting workflow.')
            self.run_full_btn.setEnabled(True)
            return
        if skip_groundfilter:
            self.log('Skipping GroundFilter step as per user request.')
        else:
            self.log('GroundFilter finished successfully. Proceeding to DTM Generation...')
        # Step 2: Run DTM Generation
        fusion_dir = self.fusion_dir_edit.text().strip()
        exe_path = os.path.join(fusion_dir, "GridSurfaceCreate64.exe")
        if not os.path.isfile(exe_path):
            exe_path = os.path.join(fusion_dir, "GridSurfaceCreate.exe")
            if not os.path.isfile(exe_path):
                self.log("ERROR: GridSurfaceCreate executable not found in Fusion folder.")
                QMessageBox.warning(self, 'Missing Executable', 'GridSurfaceCreate.exe not found in Fusion folder.')
                self.run_full_btn.setEnabled(True)
                return
        las_folder = os.path.join(output_root, input_base)
        ground_points_dir = os.path.join(las_folder, 'Ground Points')
        ground_las = os.path.join(ground_points_dir, f'{input_base}_ground.las')
        dtm_dir = os.path.join(las_folder, 'DTM')
        os.makedirs(dtm_dir, exist_ok=True)
        out_dtm = os.path.join(dtm_dir, f'{input_base}.dtm')
        # Check if DTM exists
        if os.path.isfile(out_dtm):
            reply = QMessageBox.question(self, 'File Exists', f'DTM file already exists:\n{out_dtm}\nOverwrite?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                self.log('User chose to skip DTM Generation step (file exists). Proceeding to TIF conversion if requested...')
                self.on_full_dtm_finished(True, self.dtm_tif_checkbox.isChecked(), os.path.join(fusion_dir, "DTM2TIF64.exe"), out_dtm, skip_dtm=True)
                return
            else:
                self.log('User chose to overwrite existing DTM file.')
        cell_size = self.dtm_cellsize_edit.value()
        xyunits = self.dtm_xyunits_edit.text().strip() or 'M'
        zunits = self.dtm_zunits_edit.text().strip() or 'M'
        coordsys = self.dtm_coordsys_edit.value()
        zone = self.dtm_zone_edit.value()
        horizdatum = self.dtm_horizdatum_edit.value()
        vertdatum = self.dtm_vertdatum_edit.value()
        extra_params = self.dtm_extra_edit.text().strip()
        tif_checked = self.dtm_tif_checkbox.isChecked()
        tif_exe_path = os.path.join(fusion_dir, "DTM2TIF64.exe")
        if not os.path.isfile(tif_exe_path):
            tif_exe_path = os.path.join(fusion_dir, "DTM2TIF.exe")
            if not os.path.isfile(tif_exe_path):
                self.log("ERROR: DTM2TIF executable not found in Fusion folder.")
                QMessageBox.warning(self, 'Missing Executable', 'DTM2TIF.exe not found in Fusion folder.')
                self.run_full_btn.setEnabled(True)
                return
        if not os.path.isfile(ground_las):
            self.log(f'ERROR: Ground points LAS file not found: {ground_las}')
            QMessageBox.warning(self, 'Missing Input', f'Ground points LAS file not found: {ground_las}')
            self.run_full_btn.setEnabled(True)
            return
        self.log(f'Running DTM Generation: {exe_path} {ground_las} -> {out_dtm}')
        self.dtm_run_btn.setEnabled(False)
        self.dtm_progress_bar.setVisible(True)
        self.dtm_worker = DTMWorker(
            exe_path, ground_las, out_dtm, cell_size, xyunits, zunits, coordsys, zone, horizdatum, vertdatum, extra_params
        )
        self.dtm_worker.log_signal.connect(self.dtm_log)
        self.dtm_worker.finished_signal.connect(lambda success: self.on_full_dtm_finished(success, tif_checked, tif_exe_path, out_dtm))
        self.dtm_worker.start()

    def on_full_dtm_finished(self, success, tif_checked, tif_exe_path, out_dtm, skip_dtm=False):
        self.dtm_run_btn.setEnabled(True)
        self.dtm_progress_bar.setVisible(False)
        if not success and not skip_dtm:
            self.log('DTM Generation failed. Workflow stopped.')
            self.run_full_btn.setEnabled(True)
            return
        if skip_dtm:
            self.log('Skipping DTM Generation step as per user request.')
        else:
            self.log('DTM Generation finished successfully.')
        # Check if TIF exists (if requested)
        tif_file = out_dtm.replace('.dtm', '.tif')
        if tif_checked and os.path.isfile(tif_file):
            reply = QMessageBox.question(self, 'File Exists', f'TIF file already exists:\n{tif_file}\nOverwrite?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                self.log('User chose to skip TIF conversion step (file exists).')
                self.log('--- Full Workflow Complete ---')
                self.run_full_btn.setEnabled(True)
                return
            else:
                self.log('User chose to overwrite existing TIF file.')
        if tif_checked:
            self.log('Starting DTM to TIFF conversion...')
            self.dtm_progress_bar.setVisible(True)
            self.tif_worker = TIFWorker(tif_exe_path, out_dtm)
            self.tif_worker.log_signal.connect(self.dtm_log)
            self.tif_worker.finished_signal.connect(lambda tif_success: self.on_full_tif_finished(tif_success))
            self.tif_worker.start()
        else:
            self.log('--- Full Workflow Complete ---')
            self.run_full_btn.setEnabled(True)

    def on_full_tif_finished(self, success):
        self.dtm_progress_bar.setVisible(False)
        if success:
            self.log('DTM to TIFF process finished successfully.')
            self.log('--- Full Workflow Complete ---')
        else:
            self.log('DTM to TIFF process finished with errors.')
        self.run_full_btn.setEnabled(True)

    def _row(self, label, edit, btn):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit)
        if btn:
            row.addWidget(btn)
        return row

    def pick_input_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Input LAS', '', 'LAS Files (*.las);;All Files (*)')
        if path:
            self.in_edit.setText(path)
            save_setting('input_las', path)


    # Output LAS field and picker removed; output is auto-generated

    # Removed pick_exe_file; exe path is set automatically

    def load_settings(self):
        # DTM tab - GeoTIFF
        self.dtm_tif_checkbox.setChecked(load_setting('dtm_tif_checked') == 'True')
    # No need to load dtm_tif_exe_path, it's auto-detected
        # GroundFilter tab
        self.in_edit.setText(load_setting('input_las'))
    # Output LAS field removed; no need to load output_las
        # No need to load exe_path, it's auto-detected from Fusion folder
        try:
            self.cellsize_edit.setValue(float(load_setting('cell_size') or 10.0))
        except Exception:
            self.cellsize_edit.setValue(10.0)
        self.gparam_edit.setText(load_setting('gparam'))
        self.wparam_edit.setText(load_setting('wparam'))
        try:
            self.iter_edit.setValue(int(load_setting('iterations') or 8))
        except Exception:
            self.iter_edit.setValue(8)
        # DTM tab
        self.dtm_ground_edit.setText(load_setting('dtm_ground_las'))
        self.dtm_out_edit.setText(load_setting('dtm_output_dtm'))
    # No need to load dtm_exe_path, it's auto-detected
        try:
            self.dtm_cellsize_edit.setValue(float(load_setting('dtm_cell_size') or 10.0))
        except Exception:
            self.dtm_cellsize_edit.setValue(10.0)
        self.dtm_xyunits_edit.setText(load_setting('dtm_xyunits') or 'M')
        self.dtm_zunits_edit.setText(load_setting('dtm_zunits') or 'M')
        try:
            self.dtm_coordsys_edit.setValue(int(load_setting('dtm_coordsys') or 1))
        except Exception:
            self.dtm_coordsys_edit.setValue(1)
        try:
            self.dtm_zone_edit.setValue(int(load_setting('dtm_zone') or 20))
        except Exception:
            self.dtm_zone_edit.setValue(20)
        try:
            self.dtm_horizdatum_edit.setValue(int(load_setting('dtm_horizdatum') or 2))
        except Exception:
            self.dtm_horizdatum_edit.setValue(2)
        try:
            self.dtm_vertdatum_edit.setValue(int(load_setting('dtm_vertdatum') or 2))
        except Exception:
            self.dtm_vertdatum_edit.setValue(2)
        self.dtm_extra_edit.setText(load_setting('dtm_extra'))
        # LAS Info tab
        if hasattr(self, 'lasinfo_las_edit'):
            self.lasinfo_las_edit.setText(load_setting('lasinfo_las_path'))
        if hasattr(self, 'lasinfo_exe_edit'):
            self.lasinfo_exe_edit.setText(load_setting('lasinfo_exe_path'))

    def log(self, msg):
        self.log_output.append(msg)
        print(msg)

    def run_process(self):
        in_path = self.in_edit.text().strip()
        cell_size = self.cellsize_edit.value()
        gparam = self.gparam_edit.text().strip()
        wparam = self.wparam_edit.text().strip()
        iterations = self.iter_edit.value()
        # Save settings
        save_setting('input_las', in_path)
        save_setting('cell_size', str(cell_size))
        save_setting('gparam', gparam)
        save_setting('wparam', wparam)
        save_setting('iterations', str(iterations))
        # Check input file
        if not os.path.isfile(in_path):
            QMessageBox.warning(self, 'Missing Input', f'Input LAS file not found: {in_path}')
            self.log(f'Input LAS file not found: {in_path}')
            return
        # Detect GroundFilter exe from selected Fusion folder
        fusion_dir = self.fusion_dir_edit.text().strip()
        if not fusion_dir:
            QMessageBox.warning(self, 'Missing Fusion Folder', 'Please select the Fusion folder.')
            self.log('Fusion folder not specified.')
            return
        exe_path = os.path.join(fusion_dir, 'GroundFilter64.exe')
        if not os.path.isfile(exe_path):
            exe_path = os.path.join(fusion_dir, 'GroundFilter.exe')
        if not exe_path or not os.path.isfile(exe_path):
            QMessageBox.warning(self, 'Missing Executable', f'GroundFilter.exe not found in Fusion folder: {fusion_dir}')
            self.log(f'GroundFilter.exe not found in Fusion folder: {fusion_dir}')
            return
        # Output root folder logic
        output_root = self.output_root_edit.text().strip()
        if not output_root:
            QMessageBox.warning(self, 'Missing Output Root', 'Please select the Output Root Folder.')
            self.log('Output root folder not specified.')
            return
        input_base = os.path.splitext(os.path.basename(in_path))[0]
        las_folder = os.path.join(output_root, input_base)
        ground_points_dir = os.path.join(las_folder, 'Ground Points')
        os.makedirs(ground_points_dir, exist_ok=True)
        out_path = os.path.join(ground_points_dir, f'{input_base}_ground.las')
        save_setting('output_las', out_path)
        # Disable run button and show progress bar
        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log('Starting GroundFilter process...')
        # Start worker thread
        try:
            self.worker = GroundFilterWorker(
                exe_path, in_path, out_path, cell_size, gparam, wparam, iterations
            )
            self.worker.log_signal.connect(self.log)
            self.worker.finished_signal.connect(self.on_worker_finished)
            self.worker.start()
        except Exception as e:
            print(f"Error creating or connecting worker: {e}")
            import traceback
            traceback.print_exc()
            return

    def on_worker_finished(self, success):
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            self.log('Process finished successfully.')
        else:
            self.log('Process finished with errors.')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = GroundFilterApp()
    win.show()
    sys.exit(app.exec())