"""
PolyClipData module: provides a function to run FUSION's PolyClipData programmatically.

Functions:
    run_polyclipdata(...): Runs PolyClipData and returns output file paths.

If run as a script, launches the GUI.
"""

import sys
import shapefile  # pyshp
import os
import sqlite3
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox
)
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QProcess

import glob
import subprocess

def run_polyclipdata(fusion_dir, shp_folder, las_file, output_prefix='clipped', multifile=True, field_name=None, verbose=True, overwrite=True, out_dir=None):
    """
    Run FUSION PolyClipData and return list of output LAS file paths.
    Raises RuntimeError on failure.
    out_dir: Optional custom output folder. If None, defaults to 'clipped_to_polygon' in shp_folder.
    """
    exe = os.path.join(fusion_dir, 'PolyClipData.exe')
    if not os.path.isfile(exe):
        raise FileNotFoundError(f"PolyClipData.exe not found in Fusion folder: {fusion_dir}")
    shp_files = glob.glob(os.path.join(shp_folder, '*.shp'))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in folder: {shp_folder}")
    shp = shp_files[0]
    if not os.path.isfile(las_file):
        raise FileNotFoundError(f"LAS file does not exist: {las_file}")
    if out_dir is None:
        out_dir = os.path.join(shp_folder, 'clipped_to_polygon')
    os.makedirs(out_dir, exist_ok=True)
    las_base = os.path.basename(las_file)
    if multifile:
        if not field_name:
            raise ValueError("field_name must be specified for multifile output.")
        # Find field index
        sf = shapefile.Reader(shp)
        fields = [f[0] for f in sf.fields[1:]]
        if field_name not in fields:
            raise ValueError(f"Field '{field_name}' not found in shapefile.")
        field_idx = fields.index(field_name) + 1
        out_base = os.path.join(out_dir, output_prefix)
        cmd = [exe]
        if verbose:
            cmd.append('/verbose')
        cmd.extend(['/multifile', f'/shape:{field_idx},*', shp, out_base, las_file])
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, cwd=fusion_dir)
        if result.returncode != 0:
            msg = f"PolyClipData failed.\nSTDOUT:\n{result.stdout.strip()}"
            if result.stderr and result.stderr.strip():
                msg += f"\nSTDERR:\n{result.stderr.strip()}"
            raise RuntimeError(msg)
        # Rename output files to prefix_fieldvalue_originalfilename.las
        field_values = [str(rec[fields.index(field_name)]) for rec in sf.records()]
        las_files = sorted(glob.glob(out_base + '*'))
        output_files = []
        import shutil
        if len(las_files) == len(field_values):
            for src, val in zip(las_files, field_values):
                ext = os.path.splitext(src)[1]
                dst = os.path.join(os.path.dirname(src), f'{output_prefix}_{val}_{las_base}')
                if os.path.isfile(dst) and not overwrite:
                    continue
                shutil.move(src, dst)
                output_files.append(dst)
        else:
            output_files = las_files  # fallback
        return output_files
    else:
        out_file = os.path.join(out_dir, f'{output_prefix}_{las_base}')
        cmd = [exe]
        if verbose:
            cmd.append('/verbose')
        cmd.extend([shp, out_file, las_file])
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, cwd=fusion_dir)
        if result.returncode != 0:
            msg = f"PolyClipData failed.\nSTDOUT:\n{result.stdout.strip()}"
            if result.stderr and result.stderr.strip():
                msg += f"\nSTDERR:\n{result.stderr.strip()}"
            raise RuntimeError(msg)
        return [out_file]

def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_settings.db')

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def save_setting(key, value):
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def load_setting(key):
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ''

class ClipPlotsApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Clip Plots - PolyClipData GUI')
        self.resize(600, 300)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout()
        from PySide6.QtWidgets import QComboBox, QCheckBox, QTextEdit

        # Fusion folder picker
        self.fusion_edit = QLineEdit()
        self.fusion_edit.setReadOnly(True)
        fusion_btn = QPushButton('Browse...')
        fusion_btn.clicked.connect(self.pick_fusion_folder)
        layout.addLayout(self._row('Fusion Folder:', self.fusion_edit, fusion_btn))

        # Shapefile folder picker
        self.shp_folder_edit = QLineEdit()
        self.shp_folder_edit.setReadOnly(True)
        shp_folder_btn = QPushButton('Browse...')
        shp_folder_btn.clicked.connect(self.pick_shapefile_folder)
        layout.addLayout(self._row('Shapefile Folder:', self.shp_folder_edit, shp_folder_btn))

        # Checkbox for multifile
        self.multifile_checkbox = QCheckBox('Save as multiple files (one per polygon)')
        self.multifile_checkbox.setChecked(True)
        self.multifile_checkbox.stateChanged.connect(self._on_multifile_changed)
        layout.addWidget(self.multifile_checkbox)

        # Field selection (dropdown)
        self.field_combo = QComboBox()
        self.field_combo.setEnabled(False)
        layout.addLayout(self._row('Field for Output:', self.field_combo, QLabel('')))

        # LAS input file
        self.las_edit = QLineEdit()
        las_btn = QPushButton('Browse...')
        las_btn.clicked.connect(self.pick_las_file)
        layout.addLayout(self._row('LAS File:', self.las_edit, las_btn))

        # Output prefix
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText('clipped')
        layout.addLayout(self._row('Output Prefix:', self.prefix_edit, QLabel('')))

        # Output folder (auto-set, not editable)
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        layout.addLayout(self._row('Output Folder:', self.out_edit, QLabel('')))

        # Run button
        run_btn = QPushButton('Run PolyClipData')
        run_btn.clicked.connect(self.run_polyclip)
        layout.addWidget(run_btn)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        layout.addWidget(QLabel('PolyClipData Log:'))
        layout.addWidget(self.log_output)
        self.setLayout(layout)

    def _on_multifile_changed(self):
        # Enable field selection only if multifile is checked
        self.field_combo.setEnabled(self.multifile_checkbox.isChecked())

    def _row(self, label, edit, btn):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit)
        row.addWidget(btn)
        return row


    def pick_fusion_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Fusion Folder')
        if path:
            self.fusion_edit.setText(path)
            save_setting('fusion_folder', path)

    def pick_shapefile_folder(self):
        import glob
        path = QFileDialog.getExistingDirectory(self, 'Select Folder Containing Shapefile')
        if path:
            self.shp_folder_edit.setText(path)
            save_setting('shapefile_folder', path)
            # Auto-detect .shp file
            shp_files = glob.glob(os.path.join(path, '*.shp'))
            if not shp_files:
                QMessageBox.warning(self, 'No Shapefile', 'No .shp file found in selected folder.')
                self.field_combo.clear()
                self.field_combo.setEnabled(False)
                return
            shp_path = shp_files[0]
            self._shapefile_path = shp_path
            # Read fields from shapefile
            try:
                sf = shapefile.Reader(shp_path)
                fields = [f[0] for f in sf.fields[1:]]  # skip DeletionFlag
                self.field_combo.clear()
                self.field_combo.addItems(fields)
                self.field_combo.setEnabled(True)
            except Exception as e:
                print('[ERROR] Could not read shapefile fields:', e)
                self.field_combo.clear()
                self.field_combo.setEnabled(False)
            # Set output folder to clipped_to_polygon subfolder
            clipped_folder = os.path.join(path, 'clipped_to_polygon')
            self.out_edit.setText(clipped_folder)
            save_setting('out_folder', clipped_folder)

    def pick_las_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select LAS File', '', 'LAS Files (*.las)')
        if path:
            self.las_edit.setText(path)
            save_setting('las_file', path)

    def pick_out_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
        if path:
            self.out_edit.setText(path)
            save_setting('out_folder', path)

    def load_settings(self):
        self.fusion_edit.setText(load_setting('fusion_folder'))
        self.shp_folder_edit.setText(load_setting('shapefile_folder'))
        self.las_edit.setText(load_setting('las_file'))
        self.out_edit.setText(load_setting('out_folder'))
        # Try to load fields if shapefile folder is set
        import glob
        shp_folder = self.shp_folder_edit.text().strip()
        if shp_folder and os.path.isdir(shp_folder):
            shp_files = glob.glob(os.path.join(shp_folder, '*.shp'))
            if shp_files:
                shp_path = shp_files[0]
                self._shapefile_path = shp_path
                try:
                    sf = shapefile.Reader(shp_path)
                    fields = [f[0] for f in sf.fields[1:]]
                    self.field_combo.clear()
                    self.field_combo.addItems(fields)
                    self.field_combo.setEnabled(self.multifile_checkbox.isChecked())
                except Exception as e:
                    print('[ERROR] Could not read shapefile fields:', e)
                    self.field_combo.clear()
                    self.field_combo.setEnabled(False)
                # Set output folder
                clipped_folder = os.path.join(shp_folder, 'clipped_to_polygon')
                self.out_edit.setText(clipped_folder)
            else:
                self.field_combo.clear()
                self.field_combo.setEnabled(False)
        else:
            self.field_combo.clear()
            self.field_combo.setEnabled(False)

    def run_polyclip(self):
        from PySide6.QtCore import QProcess
        import glob
        from collections import Counter
        fusion_dir = self.fusion_edit.text().strip()
        shp_folder = self.shp_folder_edit.text().strip()
        las_file = self.las_edit.text().strip()
        out_dir = self.out_edit.text().strip()
        multifile = self.multifile_checkbox.isChecked()
        field_idx = self.field_combo.currentIndex() + 1 if multifile and self.field_combo.isEnabled() else None
        prefix = self.prefix_edit.text().strip() or 'clipped'
        las_base = os.path.basename(las_file)
        # Find PolyClipData.exe in fusion_dir
        exe = os.path.join(fusion_dir, 'PolyClipData.exe')
        if not all([fusion_dir, shp_folder, las_file, out_dir]) or not os.path.isfile(exe):
            msg = 'Please select all paths and ensure PolyClipData.exe exists in the Fusion folder.'
            print('[ERROR]', msg)
            QMessageBox.warning(self, 'Missing Info', msg)
            return
        # Find .shp file in shapefile folder
        shp_files = glob.glob(os.path.join(shp_folder, '*.shp'))
        if not shp_files:
            msg = 'No .shp file found in the selected folder.'
            print('[ERROR]', msg)
            QMessageBox.warning(self, 'Missing Info', msg)
            return
        shp = shp_files[0]
        if multifile and (field_idx is None or field_idx < 1):
            msg = 'Please select a field for multifile output.'
            print('[ERROR]', msg)
            QMessageBox.warning(self, 'Missing Info', msg)
            return
        if not os.path.isfile(las_file):
            msg = 'Selected LAS file does not exist.'
            print('[ERROR]', msg)
            QMessageBox.warning(self, 'No LAS File', msg)
            return
        # Ensure output folder exists
        os.makedirs(out_dir, exist_ok=True)
        if multifile:
            # Check for duplicate field values before processing
            try:
                import shapefile as pyshp
                sf = pyshp.Reader(shp)
                field_name = self.field_combo.currentText()
                # Get field index (0-based relative to actual fields, not including DeletionFlag)
                field_names = [f[0] for f in sf.fields[1:]]
                if field_name not in field_names:
                    raise ValueError(f"Field '{field_name}' not found in shapefile")
                field_position = field_names.index(field_name)  # 0-based index in actual fields
                # sf.fields[0] is DeletionFlag, so field def is at field_position + 1
                # Each field def is [name, type, length, decimal_count]
                field_def = sf.fields[field_position + 1]
                field_decimal_count = field_def[3]  # Number of decimal places in DBF storage
                
                # Extract field values using proper indexing
                field_values = []
                for poly_idx, rec in enumerate(sf.records()):
                    val = rec[field_position]
                    field_values.append((poly_idx, val))
                
                self.log_output.clear()
                self.log_output.append(f'[INFO] Checking for duplicate IDs in field "{field_name}"...')
                
                # Count occurrences of each value
                value_counts = Counter([str(v[1]) for v in field_values])
                duplicates = {val: count for val, count in value_counts.items() if count > 1}
                
                if duplicates:
                    self.log_output.append(f'[ERROR] Duplicate IDs found:')
                    for val, count in duplicates.items():
                        self.log_output.append(f'  - "{val}": appears {count} times')
                    self.log_output.append('[ERROR] Please fix the shapefile to have unique IDs for all polygons.')
                    QMessageBox.warning(self, 'Duplicate IDs', f'Duplicate IDs found in field "{field_name}":\n' + '\n'.join([f'  - "{val}": {count} times' for val, count in duplicates.items()]))
                    return
                else:
                    self.log_output.append(f'[SUCCESS] All {len(field_values)} polygon IDs are unique.')
            except Exception as e:
                print('[ERROR] Could not check for duplicate IDs:', e)
                QMessageBox.warning(self, 'Error', f'Could not check for duplicate IDs: {e}')
                return
            # Process each polygon sequentially to avoid memory issues
            self.log_output.append(f'[INFO] Processing {len(field_values)} polygons sequentially...')
            # Store shapefile path, field position, and field values for later use
            self._field_name = field_name
            self._field_position = field_position
            self._field_decimal_count = field_decimal_count
            self._shp_path = shp
            self._polygons_to_process = [(poly_idx, val, field_idx, exe, shp, out_dir, las_file, prefix, las_base) for poly_idx, val in field_values]
            self._current_polygon_idx = 0
            self._process_next_polygon()
        else:
            out_file = os.path.join(out_dir, f'{prefix}_{las_base}')
            self._pending_rename = None
            cmd = [exe, '/verbose', shp, out_file, las_file]
            self.log_output.clear()
            self.log_output.append('[DEBUG] Running command: ' + ' '.join(cmd))
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._on_process_output)
            self.process.readyReadStandardError.connect(self._on_process_output)
            self.process.finished.connect(self._on_process_finished)
            self.process.start(cmd[0], cmd[1:])

    def _process_next_polygon(self):
        """Process the next polygon in the sequential queue."""
        if self._current_polygon_idx >= len(self._polygons_to_process):
            # All polygons processed successfully
            self.log_output.append('\n[SUCCESS] All polygons processed successfully.')
            QMessageBox.information(self, 'Done', 'All polygons clipped successfully.')
            return
        
        poly_idx, val, field_idx, exe, shp, out_dir, las_file, prefix, las_base = self._polygons_to_process[self._current_polygon_idx]
        self.log_output.append(f'\n[INFO] Processing polygon {self._current_polygon_idx + 1}/{len(self._polygons_to_process)} (ID: {val})...')
        
        # Re-read shapefile to get exact field value for this polygon
        import shapefile as pyshp
        try:
            sf = pyshp.Reader(shp)
            rec = sf.record(poly_idx)  # Get the specific polygon record
            exact_val = rec[self._field_position]  # Get exact value from shapefile
            # Format the value using the field's stored decimal precision to match
            # the exact DBF string that PolyClipData uses for comparison.
            # e.g. a field with 11 decimal places: 619.29284163 -> "619.29284163000"
            if isinstance(exact_val, float):
                val_str = f"{exact_val:.{self._field_decimal_count}f}"
            else:
                val_str = str(exact_val)
        except Exception as e:
            self.log_output.append(f'[ERROR] Could not read field value from shapefile: {e}')
            self._current_polygon_idx += 1
            self._process_next_polygon()
            return
        
        # Use individual polygon ID instead of wildcard
        out_temp = os.path.join(out_dir, f'{prefix}_{val}_{las_base}')
        cmd = [exe, '/verbose', f'/shape:{field_idx},{val_str}', shp, out_temp, las_file]
        self.log_output.append('[DEBUG] Running command: ' + ' '.join(cmd))
        
        self._current_polygon_val = val  # Store for later use in finish handler
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_process_output)
        self.process.readyReadStandardError.connect(self._on_process_output)
        self.process.finished.connect(self._on_polygon_process_finished)
        self.process.start(cmd[0], cmd[1:])

    def _on_process_output(self):
        from PySide6.QtWidgets import QApplication
        data = self.process.readAllStandardOutput().data().decode(errors='replace')
        if data:
            self.log_output.moveCursor(QTextCursor.End)
            self.log_output.insertPlainText(data)
            self.log_output.moveCursor(QTextCursor.End)
            QApplication.processEvents()  # Force GUI update

    def _on_polygon_process_finished(self, exitCode, exitStatus):
        """Handle completion of individual polygon processing."""
        if exitCode != 0:
            self.log_output.append(f'[ERROR] Failed processing polygon ID {self._current_polygon_val} (exit code {exitCode}).')
            reply = QMessageBox.question(self, 'Processing Error', 
                f'Polygon {self._current_polygon_val} failed. Continue with next polygon?', 
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                self.log_output.append('[ERROR] Processing cancelled by user.')
                return
        self._current_polygon_idx += 1
        self._process_next_polygon()

    def _on_process_finished(self, exitCode, exitStatus):
        import glob
        import shutil
        if exitCode == 0:
            # If multifile, rename output files to use prefix + field values and original LAS file name
            if getattr(self, '_pending_rename', None):
                out_base, field_values, prefix, las_base = self._pending_rename
                las_files = sorted(glob.glob(os.path.join(out_base + '*')))
                if len(las_files) == len(field_values):
                    for src, val in zip(las_files, field_values):
                        ext = os.path.splitext(src)[1]
                        # New name: prefix_fieldvalue_originalfilename.las
                        dst = os.path.join(os.path.dirname(src), f'{prefix}_{val}_{las_base}')
                        try:
                            shutil.move(src, dst)
                        except Exception as e:
                            self.log_output.append(f'\n[WARN] Could not rename {src} to {dst}: {e}')
                else:
                    self.log_output.append(f'\n[WARN] Output file count does not match field value count.')
            self.log_output.append('\n[SUCCESS] PolyClipData completed successfully.')
            QMessageBox.information(self, 'Done', 'PolyClipData completed successfully.')
        else:
            self.log_output.append(f'\n[ERROR] PolyClipData failed with exit code {exitCode}.')
            QMessageBox.warning(self, 'Error', f'PolyClipData failed with exit code {exitCode}.')

if __name__ == '__main__':
    init_db()
    app = QApplication(sys.argv)
    win = ClipPlotsApp()
    win.show()
    sys.exit(app.exec())
