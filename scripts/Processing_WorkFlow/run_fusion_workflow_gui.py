import sys
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, QTabWidget, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar, QMessageBox, QComboBox, QListWidget
)
from PySide6.QtCore import QThread, Signal

class WorkflowWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        import run_fusion_workflow as wf
        try:
            for las_file in self.params['las_files']:
                self.log_signal.emit(f"Processing: {las_file}")
                wf.process_single_las(
                    las_file_path=las_file,
                    shapefile_path=self.params['shapefile_path'],
                    field_name=self.params['field_name'],
                    output_root=self.params['output_root'],
                    fusion_dir=self.params['fusion_dir'],
                    overwrite=self.params['overwrite']
                )
            self.log_signal.emit("Batch processing complete.")
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
        self.finished_signal.emit()

class WorkflowGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FUSION Batch Workflow GUI')
        self.resize(900, 700)
        self.init_ui()
        self.worker = None

    def init_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()

        # --- Batch Workflow Tab ---
        batch_tab = QWidget()
        batch_layout = QVBoxLayout()
        # Input LAS folder
        in_row = QHBoxLayout()
        self.in_edit = QLineEdit()
        in_btn = QPushButton('Browse...')
        in_btn.clicked.connect(self.pick_input_folder)
        in_row.addWidget(QLabel('Input LAS Folder:'))
        in_row.addWidget(self.in_edit)
        in_row.addWidget(in_btn)
        batch_layout.addLayout(in_row)
        # Output folder
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        out_btn = QPushButton('Browse...')
        out_btn.clicked.connect(self.pick_output_folder)
        out_row.addWidget(QLabel('Output Folder:'))
        out_row.addWidget(self.out_edit)
        out_row.addWidget(out_btn)
        batch_layout.addLayout(out_row)
        # Fusion folder
        fusion_row = QHBoxLayout()
        self.fusion_edit = QLineEdit()
        fusion_btn = QPushButton('Browse...')
        fusion_btn.clicked.connect(self.pick_fusion_folder)
        fusion_row.addWidget(QLabel('Fusion Folder:'))
        fusion_row.addWidget(self.fusion_edit)
        fusion_row.addWidget(fusion_btn)
        batch_layout.addLayout(fusion_row)
    # (No shapefile or field name controls in batch tab; use PolyClipData tab's controls)
        # Overwrite checkbox
        self.overwrite_cb = QCheckBox('Overwrite Existing Outputs')
        batch_layout.addWidget(self.overwrite_cb)
        # Run button
        self.run_btn = QPushButton('Run Batch Workflow')
        self.run_btn.clicked.connect(self.run_workflow)
        batch_layout.addWidget(self.run_btn)
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(0)
        self.progress.setVisible(False)
        batch_layout.addWidget(self.progress)
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        batch_layout.addWidget(QLabel('Log Output:'))
        batch_layout.addWidget(self.log_output)
        batch_tab.setLayout(batch_layout)

        # --- PolyClipData Tab ---
        polyclip_tab = QWidget()
        polyclip_layout = QVBoxLayout()
    # guidance for single-file usage
        polyclip_layout.addWidget(QLabel('Note: select an input LAS here only when running PolyClipData for a single LAS; use the Batch tab for folder processing.'))
        # LAS file
        las_row = QHBoxLayout()
        self.polyclip_las_edit = QLineEdit()
        self.polyclip_las_edit.setPlaceholderText('Select single LAS (only for individual PolyClip runs)')
        las_btn = QPushButton('Browse...')
        las_btn.setToolTip('Browse for a single LAS file (only when running PolyClipData for one file)')
        las_btn.clicked.connect(self.pick_polyclip_las)
        las_row.addWidget(QLabel('Input LAS File:'))
        las_row.addWidget(self.polyclip_las_edit)
        las_row.addWidget(las_btn)
        polyclip_layout.addLayout(las_row)
        # Shapefile
        polyclip_shp_row = QHBoxLayout()
        self.polyclip_shp_edit = QLineEdit()
        polyclip_shp_btn = QPushButton('Browse...')
        polyclip_shp_btn.clicked.connect(self.pick_polyclip_shapefile)
        polyclip_shp_row.addWidget(QLabel('Shapefile:'))
        polyclip_shp_row.addWidget(self.polyclip_shp_edit)
        polyclip_shp_row.addWidget(polyclip_shp_btn)
        polyclip_layout.addLayout(polyclip_shp_row)
        # Field name (dropdown)
        polyclip_field_row = QHBoxLayout()
        self.polyclip_field_combo = QComboBox()
        self.polyclip_field_combo.setEditable(False)
        polyclip_field_row.addWidget(QLabel('Field Name:'))
        polyclip_field_row.addWidget(self.polyclip_field_combo)
        polyclip_layout.addLayout(polyclip_field_row)
        # Multifile checkbox
        self.polyclip_multifile_cb = QCheckBox('Output one LAS per polygon (multifile)')
        self.polyclip_multifile_cb.setChecked(True)
        polyclip_layout.addWidget(self.polyclip_multifile_cb)
        # Run button
        self.polyclip_run_btn = QPushButton('Run PolyClipData')
        self.polyclip_run_btn.clicked.connect(self.run_polyclip)
        polyclip_layout.addWidget(self.polyclip_run_btn)
        # Log output
        self.polyclip_log_output = QTextEdit()
        self.polyclip_log_output.setReadOnly(True)
        polyclip_layout.addWidget(QLabel('Log Output:'))
        polyclip_layout.addWidget(self.polyclip_log_output)
        polyclip_tab.setLayout(polyclip_layout)
        self.tabs.addTab(polyclip_tab, '1. PolyClipData')

        # --- Ground Filter Tab ---
        ground_tab = QWidget()
        ground_layout = QVBoxLayout()
        # guidance for single-file usage
        ground_layout.addWidget(QLabel('Note: select an input LAS here only when running GroundFilter on a single LAS; use the Batch tab for folder processing.'))
        # Input LAS file for ground filter
        g_las_row = QHBoxLayout()
        self.ground_las_edit = QLineEdit()
        self.ground_las_edit.setPlaceholderText('Select single LAS (only for individual GroundFilter runs)')
        g_las_btn = QPushButton('Browse...')
        g_las_btn.setToolTip('Browse for a single LAS file (only when running GroundFilter for one file)')
        g_las_btn.clicked.connect(self.pick_ground_las)
        g_las_row.addWidget(QLabel('Input LAS File:'))
        g_las_row.addWidget(self.ground_las_edit)
        g_las_row.addWidget(g_las_btn)
        ground_layout.addLayout(g_las_row)
        # Parameters: cell size
        cell_row = QHBoxLayout()
        self.ground_cell_size = QDoubleSpinBox()
        self.ground_cell_size.setRange(0.1, 1000.0)
        self.ground_cell_size.setDecimals(2)
        self.ground_cell_size.setValue(5.0)
        cell_row.addWidget(QLabel('Cell Size:'))
        cell_row.addWidget(self.ground_cell_size)
        ground_layout.addLayout(cell_row)
        # Parameters: gparam and wparam
        gw_row = QHBoxLayout()
        self.ground_gparam = QLineEdit()
        self.ground_wparam = QLineEdit()
        gw_row.addWidget(QLabel('gparam:'))
        gw_row.addWidget(self.ground_gparam)
        gw_row.addWidget(QLabel('wparam:'))
        gw_row.addWidget(self.ground_wparam)
        ground_layout.addLayout(gw_row)
        # Iterations
        iter_row = QHBoxLayout()
        self.ground_iterations = QSpinBox()
        self.ground_iterations.setRange(1, 50)
        self.ground_iterations.setValue(8)
        iter_row.addWidget(QLabel('Iterations:'))
        iter_row.addWidget(self.ground_iterations)
        ground_layout.addLayout(iter_row)
        # Run button
        self.ground_run_btn = QPushButton('Run GroundFilter')
        self.ground_run_btn.clicked.connect(self.run_groundfilter)
        ground_layout.addWidget(self.ground_run_btn)
        # Log output
        self.ground_log_output = QTextEdit()
        self.ground_log_output.setReadOnly(True)
        ground_layout.addWidget(QLabel('Log Output:'))
        ground_layout.addWidget(self.ground_log_output)
        ground_tab.setLayout(ground_layout)
        self.tabs.addTab(ground_tab, '2. Ground Filter')
        # --- DTM Generation Tab ---
        dtm_tab = QWidget()
        dtm_layout = QVBoxLayout()
        # guidance
        dtm_layout.addWidget(QLabel('Generate a DTM from a ground-points LAS. Select a ground LAS and set options.'))
        # Ground LAS selector
        dtm_las_row = QHBoxLayout()
        self.dtm_ground_las_edit = QLineEdit()
        self.dtm_ground_las_edit.setPlaceholderText('Select ground-points LAS (e.g. *_ground.las)')
        dtm_las_btn = QPushButton('Browse...')
        dtm_las_btn.setToolTip('Select a ground points LAS file to generate a DTM')
        dtm_las_btn.clicked.connect(self.pick_dtm_ground_las)
        dtm_las_row.addWidget(QLabel('Ground LAS:'))
        dtm_las_row.addWidget(self.dtm_ground_las_edit)
        dtm_las_row.addWidget(dtm_las_btn)
        dtm_layout.addLayout(dtm_las_row)
        # Cell size
        dtm_cell_row = QHBoxLayout()
        self.dtm_cell_size = QDoubleSpinBox()
        self.dtm_cell_size.setRange(0.1, 1000.0)
        self.dtm_cell_size.setDecimals(2)
        self.dtm_cell_size.setValue(5.0)
        dtm_cell_row.addWidget(QLabel('Cell Size:'))
        dtm_cell_row.addWidget(self.dtm_cell_size)
        dtm_layout.addLayout(dtm_cell_row)
        # Generate TIF checkbox
        self.dtm_generate_tif_cb = QCheckBox('Generate GeoTIFF from DTM')
        self.dtm_generate_tif_cb.setChecked(True)
        dtm_layout.addWidget(self.dtm_generate_tif_cb)
        # Run button
        self.dtm_run_btn = QPushButton('Run DTM Generation')
        self.dtm_run_btn.clicked.connect(self.run_generate_dtm)
        dtm_layout.addWidget(self.dtm_run_btn)
        # Log output
        self.dtm_log_output = QTextEdit()
        self.dtm_log_output.setReadOnly(True)
        dtm_layout.addWidget(QLabel('Log Output:'))
        dtm_layout.addWidget(self.dtm_log_output)
        dtm_tab.setLayout(dtm_layout)
        self.tabs.addTab(dtm_tab, '3. DTM Generation')
        # --- Normalization Tab ---
        norm_tab = QWidget()
        norm_layout = QVBoxLayout()
        norm_layout.addWidget(QLabel('Normalize LAS files using a ground DTM. Select the folder containing LAS files and the ground DTM file.'))
        # Input LAS file for normalization (pick a single LAS; folder is derived)
        norm_in_row = QHBoxLayout()
        self.norm_las_edit = QLineEdit()
        norm_in_btn = QPushButton('Browse...')
        norm_in_btn.clicked.connect(self.pick_normalize_input_folder)
        norm_in_row.addWidget(QLabel('Input LAS File:'))
        norm_in_row.addWidget(self.norm_las_edit)
        norm_in_row.addWidget(norm_in_btn)
        norm_layout.addLayout(norm_in_row)
        # Ground DTM selector
        norm_dtm_row = QHBoxLayout()
        self.norm_ground_dtm_edit = QLineEdit()
        norm_dtm_btn = QPushButton('Browse...')
        norm_dtm_btn.clicked.connect(self.pick_ground_dtm)
        norm_dtm_row.addWidget(QLabel('Ground DTM (.dtm):'))
        norm_dtm_row.addWidget(self.norm_ground_dtm_edit)
        norm_dtm_row.addWidget(norm_dtm_btn)
        norm_layout.addLayout(norm_dtm_row)
        # Run button
        self.norm_run_btn = QPushButton('Run Normalization')
        self.norm_run_btn.clicked.connect(self.run_normalization)
        norm_layout.addWidget(self.norm_run_btn)
        # Log output
        self.norm_log_output = QTextEdit()
        self.norm_log_output.setReadOnly(True)
        norm_layout.addWidget(QLabel('Log Output:'))
        norm_layout.addWidget(self.norm_log_output)
        norm_tab.setLayout(norm_layout)
        self.tabs.addTab(norm_tab, '4. Normalization')

        # --- CloudMetrics Tab ---
        cloud_tab = QWidget()
        cloud_layout = QVBoxLayout()
        cloud_layout.addWidget(QLabel('Run CloudMetrics on a folder of normalized LAS files.'))
        # Normalized folder selector
        cloud_in_row = QHBoxLayout()
        self.cloud_in_edit = QLineEdit()
        cloud_in_btn = QPushButton('Browse...')
        cloud_in_btn.clicked.connect(self.pick_cloud_normalized_folder)
        cloud_in_row.addWidget(QLabel('Normalized LAS Folder:'))
        cloud_in_row.addWidget(self.cloud_in_edit)
        cloud_in_row.addWidget(cloud_in_btn)
        cloud_layout.addLayout(cloud_in_row)
        # Scan and list LAS files
        scan_row = QHBoxLayout()
        scan_btn = QPushButton('Scan for LAS files')
        scan_btn.clicked.connect(self.cloud_scan_las_files)
        scan_row.addWidget(scan_btn)
        cloud_layout.addLayout(scan_row)
        self.cloud_las_list = QListWidget()
        cloud_layout.addWidget(QLabel('LAS files to process:'))
        cloud_layout.addWidget(self.cloud_las_list)
        # Run button
        self.cloud_run_btn = QPushButton('Run CloudMetrics')
        self.cloud_run_btn.clicked.connect(self.run_cloudmetrics_tab)
        cloud_layout.addWidget(self.cloud_run_btn)
        # Progress bar
        self.cloud_progress = QProgressBar()
        self.cloud_progress.setMinimum(0)
        self.cloud_progress.setMaximum(100)
        self.cloud_progress.setValue(0)
        cloud_layout.addWidget(self.cloud_progress)
        # Log output
        self.cloud_log_output = QTextEdit()
        self.cloud_log_output.setReadOnly(True)
        cloud_layout.addWidget(QLabel('Log Output:'))
        cloud_layout.addWidget(self.cloud_log_output)
        cloud_tab.setLayout(cloud_layout)
        self.tabs.addTab(cloud_tab, '5. CloudMetrics')
        # --- GridMetrics Tab ---
        grid_tab = QWidget()
        grid_layout = QVBoxLayout()
        grid_layout.addWidget(QLabel('Run GridMetrics on a folder of normalized LAS files.'))
        # Normalized folder selector
        grid_in_row = QHBoxLayout()
        self.grid_in_edit = QLineEdit()
        grid_in_btn = QPushButton('Browse...')
        grid_in_btn.clicked.connect(self.pick_grid_normalized_folder)
        grid_in_row.addWidget(QLabel('Normalized LAS Folder:'))
        grid_in_row.addWidget(self.grid_in_edit)
        grid_in_row.addWidget(grid_in_btn)
        grid_layout.addLayout(grid_in_row)
        # Scan and list LAS files
        grid_scan_row = QHBoxLayout()
        grid_scan_btn = QPushButton('Scan for LAS files')
        grid_scan_btn.clicked.connect(self.grid_scan_las_files)
        grid_scan_row.addWidget(grid_scan_btn)
        grid_layout.addLayout(grid_scan_row)
        self.grid_las_list = QListWidget()
        grid_layout.addWidget(QLabel('LAS files to process:'))
        grid_layout.addWidget(self.grid_las_list)
        # Run button
        self.grid_run_btn = QPushButton('Run GridMetrics')
        self.grid_run_btn.clicked.connect(self.run_gridmetrics_tab)
        grid_layout.addWidget(self.grid_run_btn)
        # Checkbox for no raster flag
        self.grid_no_raster_cb = QCheckBox('Run without /raster flag (use defaults)')
        grid_layout.addWidget(self.grid_no_raster_cb)
        # Use DTM checkbox
        self.grid_use_dtm_cb = QCheckBox('Use DTM file for ground')
        grid_layout.addWidget(self.grid_use_dtm_cb)
        # DTM file selector
        grid_dtm_row = QHBoxLayout()
        self.grid_dtm_edit = QLineEdit()
        grid_dtm_btn = QPushButton('Browse...')
        grid_dtm_btn.clicked.connect(self.pick_grid_dtm)
        grid_dtm_row.addWidget(QLabel('Ground DTM (.dtm):'))
        grid_dtm_row.addWidget(self.grid_dtm_edit)
        grid_dtm_row.addWidget(grid_dtm_btn)
        grid_layout.addLayout(grid_dtm_row)
        self.grid_progress = QProgressBar()
        self.grid_progress.setMinimum(0)
        self.grid_progress.setMaximum(100)
        self.grid_progress.setValue(0)
        grid_layout.addWidget(self.grid_progress)
        # Log output
        self.grid_log_output = QTextEdit()
        self.grid_log_output.setReadOnly(True)
        grid_layout.addWidget(QLabel('Log Output:'))
        grid_layout.addWidget(self.grid_log_output)
        grid_tab.setLayout(grid_layout)
        self.tabs.addTab(grid_tab, '6. GridMetrics')
        # Add batch tab last so it appears as the final tab
        self.tabs.addTab(batch_tab, 'Batch Workflow')
        layout.addWidget(self.tabs)
        self.setLayout(layout)
        

    def pick_polyclip_las(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Input LAS File', '', 'LAS Files (*.las)')
        if path:
            self.polyclip_las_edit.setText(path)

    def pick_polyclip_shapefile(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Shapefile', '', 'Shapefiles (*.shp)')
        if path:
            self.polyclip_shp_edit.setText(path)
            # Populate field combo with shapefile fields
            try:
                import shapefile
                # pyshp: shapefile.Reader(path).fields -> list of (name, type, size, dec), first entry is DeletionFlag
                r = shapefile.Reader(path)
                fields = [f[0] for f in r.fields[1:]]
                self.polyclip_field_combo.clear()
                self.polyclip_field_combo.addItems(fields)
                if 'NAME' in fields:
                    self.polyclip_field_combo.setCurrentText('NAME')
            except Exception as e:
                self.polyclip_field_combo.clear()
                self.polyclip_field_combo.addItem('[Error reading fields]')
                QMessageBox.warning(self, 'Shapefile Error', f'Could not read fields: {e}')

    def run_polyclip(self):
        las_file = self.polyclip_las_edit.text().strip()
        shapefile = self.polyclip_shp_edit.text().strip()
        field_name = self.polyclip_field_combo.currentText().strip()
        multifile = self.polyclip_multifile_cb.isChecked()
        if not (las_file and shapefile and field_name and field_name != '[Error reading fields]'):
            QMessageBox.warning(self, 'Missing Input', 'Please fill in all required fields.')
            return
        try:
            import run_fusion_workflow as wf
            self.polyclip_log_output.clear()
            self.polyclip_log_output.append(f'Running PolyClipData...')
            # Ensure the workflow module uses GUI-specified fusion dir
            wf.fusion_dir = self.fusion_edit.text().strip() or wf.fusion_dir
            # Ensure an output folder is provided; prompt the user if the Batch-output field is empty
            if not self.out_edit.text().strip():
                folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
                if not folder:
                    QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                    return
                self.out_edit.setText(folder)
            wf.output_root = self.out_edit.text().strip() or wf.output_root
            wf.polyclip(
                las_file_path=las_file,
                shapefile_path=shapefile,
                field_name=field_name,
                multifile=multifile,
                verbose=True,
                print_info=True,
                overwrite=self.overwrite_cb.isChecked()
            )
            self.polyclip_log_output.append('PolyClipData finished.')
        except Exception as e:
            self.polyclip_log_output.append(f'[ERROR] {e}')

    def pick_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Input LAS Folder')
        if folder:
            self.in_edit.setText(folder)

    def pick_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
        if folder:
            self.out_edit.setText(folder)

    def pick_fusion_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Fusion Folder')
        if folder:
            self.fusion_edit.setText(folder)

    def pick_ground_las(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Input LAS File', '', 'LAS Files (*.las)')
        if path:
            self.ground_las_edit.setText(path)

    def run_groundfilter(self):
        las_file = self.ground_las_edit.text().strip()
        if not las_file:
            QMessageBox.warning(self, 'Missing Input', 'Please select an input LAS file for GroundFilter.')
            return
        cell_size = float(self.ground_cell_size.value())
        gparam = self.ground_gparam.text().strip() or None
        wparam = self.ground_wparam.text().strip() or None
        iterations = int(self.ground_iterations.value())
        try:
            import run_fusion_workflow as wf
            # Ensure workflow module uses GUI-specified fusion dir
            wf.fusion_dir = self.fusion_edit.text().strip() or wf.fusion_dir
            # Ensure an output folder is provided; prompt the user if the Batch-output field is empty
            if not self.out_edit.text().strip():
                folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
                if not folder:
                    QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                    return
                self.out_edit.setText(folder)
            wf.output_root = self.out_edit.text().strip() or wf.output_root
            self.ground_log_output.clear()
            self.ground_log_output.append(f'Running GroundFilter on: {las_file}')
            out = wf.groundfilter(
                las_file_path=las_file,
                cell_size=cell_size,
                gparam=gparam,
                wparam=wparam,
                iterations=iterations,
                print_info=True
            )
            if out:
                self.ground_log_output.append(f'GroundFilter finished. Output: {out}')
            else:
                self.ground_log_output.append('[ERROR] GroundFilter failed or returned no output.')
        except Exception as e:
            self.ground_log_output.append(f'[ERROR] {e}')

    def pick_shapefile(self):
        # This helper was removed because the Batch tab uses the PolyClipData tab's shapefile controls.
        return

    def pick_dtm_ground_las(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Ground LAS File', '', 'LAS Files (*.las)')
        if path:
            self.dtm_ground_las_edit.setText(path)

    def run_generate_dtm(self):
        las_file = self.dtm_ground_las_edit.text().strip()
        if not las_file:
            QMessageBox.warning(self, 'Missing Input', 'Please select a ground-points LAS file to generate a DTM.')
            return
        cell_size = float(self.dtm_cell_size.value())
        generate_tif = bool(self.dtm_generate_tif_cb.isChecked())
        try:
            import run_fusion_workflow as wf
            # Ensure workflow module uses GUI-specified fusion dir
            wf.fusion_dir = self.fusion_edit.text().strip() or wf.fusion_dir
            # Ensure an output folder is provided; prompt the user if the Batch-output field is empty
            if not self.out_edit.text().strip():
                folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
                if not folder:
                    QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                    return
                self.out_edit.setText(folder)
            wf.output_root = self.out_edit.text().strip() or wf.output_root
            self.dtm_log_output.clear()
            self.dtm_log_output.append(f'Generating DTM for: {las_file} (cell size: {cell_size})')
            out = wf.generate_dtm(
                ground_las_path=las_file,
                cell_size=cell_size,
                generate_tif=generate_tif,
                print_info=True,
                overwrite=self.overwrite_cb.isChecked()
            )
            if out:
                self.dtm_log_output.append(f'DTM generation finished. Output: {out}')
            else:
                self.dtm_log_output.append('[ERROR] DTM generation failed or returned no output.')
        except Exception as e:
            self.dtm_log_output.append(f'[ERROR] {e}')

    def pick_normalize_input_folder(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Input LAS File to derive folder', '', 'LAS Files (*.las)')
        if path:
            self.norm_las_edit.setText(path)

    def pick_ground_dtm(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Ground DTM File', '', 'DTM Files (*.dtm)')
        if path:
            self.norm_ground_dtm_edit.setText(path)

    def pick_grid_dtm(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Ground DTM File for GridMetrics', '', 'DTM Files (*.dtm)')
        if path:
            self.grid_dtm_edit.setText(path)

    def run_normalization(self):
        las_path = self.norm_las_edit.text().strip()
        ground_dtm = self.norm_ground_dtm_edit.text().strip()
        if not las_path:
            QMessageBox.warning(self, 'Missing Input', 'Please select an input LAS file to derive the folder containing LAS files to normalize.')
            return
        if not os.path.isfile(las_path):
            QMessageBox.warning(self, 'File Not Found', f'Selected LAS file not found: {las_path}')
            return
        input_folder = os.path.dirname(las_path)
        if not input_folder:
            QMessageBox.warning(self, 'Missing Input', 'Could not determine input folder from the selected LAS file.')
            return
        if not ground_dtm:
            QMessageBox.warning(self, 'Missing Input', 'Please select the ground DTM (.dtm) file to use for normalization.')
            return
        try:
            import run_fusion_workflow as wf
            # Ensure an output folder is provided; prompt if Batch-output field is empty
            if not self.out_edit.text().strip():
                folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
                if not folder:
                    QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                    return
                self.out_edit.setText(folder)
            wf.output_root = self.out_edit.text().strip() or wf.output_root
            self.norm_log_output.clear()
            self.norm_log_output.append(f'Normalizing LAS files in: {input_folder} using DTM: {ground_dtm}')
            results = wf.normalize_las_files(
                input_folder=input_folder,
                ground_dtm=ground_dtm,
                overwrite=self.overwrite_cb.isChecked(),
                print_info=True
            )
            if results:
                self.norm_log_output.append(f'Normalization finished. {len(results)} files processed.')
                for r in results:
                    self.norm_log_output.append(f'  {r}')
            else:
                self.norm_log_output.append('[ERROR] No files normalized or process failed.')
        except Exception as e:
            self.norm_log_output.append(f'[ERROR] {e}')

    def pick_cloud_normalized_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Normalized LAS Folder')
        if folder:
            self.cloud_in_edit.setText(folder)

    def cloud_scan_las_files(self):
        folder = self.cloud_in_edit.text().strip()
        self.cloud_las_list.clear()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, 'Missing Input', 'Please select a valid normalized LAS folder and try again.')
            return
        las_files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.las')])
        if not las_files:
            self.cloud_log_output.append('[INFO] No LAS files found in the selected folder.')
            return
        for f in las_files:
            self.cloud_las_list.addItem(f)
        self.cloud_log_output.append(f'[INFO] Found {len(las_files)} LAS files in {folder}.')
        # prepare progress
        self.cloud_progress.setMinimum(0)
        self.cloud_progress.setMaximum(len(las_files))
        self.cloud_progress.setValue(0)

    def run_cloudmetrics_tab(self):
        folder = self.cloud_in_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, 'Missing Input', 'Please select a valid normalized LAS folder to run CloudMetrics.')
            return
        # Ensure an output folder is provided; prompt the user if the Batch-output field is empty
        if not self.out_edit.text().strip():
            out_folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
            if not out_folder:
                QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                return
            self.out_edit.setText(out_folder)
        output_root = self.out_edit.text().strip()
        try:
            import run_fusion_workflow as wf
            # Ensure workflow module uses GUI-specified fusion dir
            wf.fusion_dir = self.fusion_edit.text().strip() or wf.fusion_dir
            wf.output_root = output_root or wf.output_root
            self.cloud_log_output.clear()
            self.cloud_log_output.append(f'Running CloudMetrics on folder: {folder}')
            # Set progress to busy state
            self.cloud_progress.setMaximum(0)
            results = wf.run_cloudmetrics(
                normalized_folder=folder,
                output_root=output_root,
                overwrite=self.overwrite_cb.isChecked(),
                print_info=True
            )
            # restore progress and show results
            if isinstance(results, list):
                self.cloud_progress.setMaximum(max(1, len(results)))
                self.cloud_progress.setValue(len(results))
                if results:
                    self.cloud_log_output.append(f'CloudMetrics finished. {len(results)} output files created:')
                    for r in results:
                        self.cloud_log_output.append(f'  {r}')
                else:
                    self.cloud_log_output.append('[INFO] CloudMetrics finished but no output files were returned.')
            else:
                self.cloud_log_output.append('[INFO] CloudMetrics finished.')
            self.cloud_progress.setMaximum(100)
            self.cloud_progress.setValue(100)
        except Exception as e:
            self.cloud_log_output.append(f'[ERROR] {e}')

    def pick_grid_normalized_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Normalized LAS Folder for GridMetrics')
        if folder:
            self.grid_in_edit.setText(folder)

    def grid_scan_las_files(self):
        folder = self.grid_in_edit.text().strip()
        self.grid_las_list.clear()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, 'Missing Input', 'Please select a valid normalized LAS folder and try again.')
            return
        las_files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.las')])
        if not las_files:
            self.grid_log_output.append('[INFO] No LAS files found in the selected folder.')
            return
        for f in las_files:
            self.grid_las_list.addItem(f)
        self.grid_log_output.append(f'[INFO] Found {len(las_files)} LAS files in {folder}.')
        # prepare progress
        self.grid_progress.setMinimum(0)
        self.grid_progress.setMaximum(len(las_files))
        self.grid_progress.setValue(0)

    def run_gridmetrics_tab(self):
        folder = self.grid_in_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, 'Missing Input', 'Please select a valid normalized LAS folder to run GridMetrics.')
            return
        # Ensure an output folder is provided; prompt the user if the Batch-output field is empty
        if not self.out_edit.text().strip():
            out_folder = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
            if not out_folder:
                QMessageBox.warning(self, 'Output Required', 'Please select an output folder to continue.')
                return
            self.out_edit.setText(out_folder)
        output_root = self.out_edit.text().strip()
        use_dtm = self.grid_use_dtm_cb.isChecked()
        ground_dtm = None
        if use_dtm:
            ground_dtm = self.grid_dtm_edit.text().strip()
            if not ground_dtm:
                QMessageBox.warning(self, 'Missing DTM', 'Please select a ground DTM file or uncheck "Use DTM file".')
                return
            if not os.path.isfile(ground_dtm):
                QMessageBox.warning(self, 'DTM File Not Found', f'Ground DTM file not found: {ground_dtm}')
                return
        try:
            import run_fusion_workflow as wf
            # Ensure workflow module uses GUI-specified fusion dir
            wf.fusion_dir = self.fusion_edit.text().strip() or wf.fusion_dir
            wf.output_root = output_root or wf.output_root
            self.grid_log_output.clear()
            self.grid_log_output.append(f'Running GridMetrics on folder: {folder}')
            # Set progress to busy state
            self.grid_progress.setMaximum(0)
            kwargs = {
                'normalized_folder': folder,
                'output_root': output_root,
                'raster_metrics': '' if self.grid_no_raster_cb.isChecked() else 'mean,cover,p90',
                'overwrite': self.overwrite_cb.isChecked(),
                'print_info': True
            }
            if ground_dtm:
                kwargs['ground_model'] = ground_dtm
            results = wf.run_gridmetrics(**kwargs)
            # restore progress and show results
            if isinstance(results, list):
                self.grid_progress.setMaximum(max(1, len(results)))
                self.grid_progress.setValue(len(results))
                if results:
                    self.grid_log_output.append(f'GridMetrics finished. {len(results)} output files created:')
                    for r in results:
                        self.grid_log_output.append(f'  {r}')
                else:
                    self.grid_log_output.append('[INFO] GridMetrics finished but no output files were returned.')
            else:
                self.grid_log_output.append('[INFO] GridMetrics finished.')
            self.grid_progress.setMaximum(100)
            self.grid_progress.setValue(100)
        except Exception as e:
            self.grid_log_output.append(f'[ERROR] {e}')

    def run_workflow(self):
        input_folder = self.in_edit.text().strip()
        output_folder = self.out_edit.text().strip()
        fusion_folder = self.fusion_edit.text().strip()
        # Use PolyClipData tab's controls for shapefile, field name, and multifile
        shapefile = self.polyclip_shp_edit.text().strip()
        field_name = self.polyclip_field_combo.currentText().strip()
        multifile = self.polyclip_multifile_cb.isChecked()
        overwrite = self.overwrite_cb.isChecked()
        if not (input_folder and output_folder and fusion_folder and shapefile and field_name and field_name != '[Error reading fields]'):
            QMessageBox.warning(self, 'Missing Input', 'Please fill in all required fields in both tabs.')
            return
        las_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.lower().endswith('.las')]
        if not las_files:
            QMessageBox.warning(self, 'No LAS Files', 'No LAS files found in the input folder.')
            return
        params = {
            'las_files': las_files,
            'shapefile_path': shapefile,
            'field_name': field_name,
            'output_root': output_folder,
            'fusion_dir': fusion_folder,
            'overwrite': overwrite,
            'multifile': multifile
        }
        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.log_output.clear()
        self.worker = WorkflowWorker(params)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.log_output.append('All processing complete.')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = WorkflowGUI()
    win.show()
    sys.exit(app.exec())
