#!/usr/bin/env python3
"""
LAS to LAZ (and LAZ to LAS) Converter Tool
=========================================
High-performance converter supporting single files and batch folder conversion.
Supports both native C++ laszip64 engine (LAStools) and Python streaming (laspy + lazrs).

Usage (CLI):
    # Convert a single file
    python las_to_laz.py -i input.las
    python las_to_laz.py -i input.las -o output.laz

    # Convert all LAS files in a folder
    python las_to_laz.py -i "D:/MyData/LAS_Files"
    python las_to_laz.py -i "D:/MyData/LAS_Files" -o "D:/MyData/LAZ_Files" --recursive

    # Multi-threaded batch conversion
    python las_to_laz.py -i "D:/MyData" --cores 8 --verify

    # Decompress LAZ to LAS
    python las_to_laz.py -i input.laz --decompress

    # Launch GUI
    python las_to_laz.py --gui
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Engine Detection
# ---------------------------------------------------------------------------

def find_laszip_binary() -> Optional[str]:
    """Find laszip64.exe or laszip.exe in repository LAStools or PATH."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        repo_root / "LAStools" / "bin" / "laszip64.exe",
        repo_root / "LAStools" / "bin" / "laszip.exe",
        Path("C:/LAStools/bin/laszip64.exe"),
        Path("C:/LAStools/bin/laszip.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    # Check system PATH
    for name in ["laszip64.exe", "laszip.exe", "laszip64", "laszip"]:
        p = shutil.which(name)
        if p:
            return p
    return None


def is_lazrs_available() -> bool:
    """Check if Python lazrs backend is installed."""
    try:
        import lazrs  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Conversion Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    input_path: str
    output_path: str
    success: bool
    orig_size: int
    new_size: int
    point_count: int
    duration_sec: float
    error_message: str = ""

    @property
    def ratio_percent(self) -> float:
        if self.orig_size <= 0:
            return 0.0
        return (self.new_size / self.orig_size) * 100.0

    @property
    def savings_percent(self) -> float:
        if self.orig_size <= 0:
            return 0.0
        return max(0.0, 100.0 - self.ratio_percent)


# ---------------------------------------------------------------------------
# Core Conversion Logic
# ---------------------------------------------------------------------------

def convert_file_laspy(
    input_path: str,
    output_path: str,
    chunk_size: int = 1_000_000,
    verify: bool = True
) -> ConversionResult:
    """Convert LAS/LAZ using streaming chunked laspy + lazrs."""
    import laspy

    t0 = time.perf_counter()
    orig_size = os.path.getsize(input_path)
    total_pts = 0

    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with laspy.open(input_path) as reader:
            header = reader.header
            total_pts = header.point_count
            with laspy.open(output_path, mode="w", header=header) as writer:
                for chunk in reader.chunk_iterator(chunk_size):
                    writer.write_points(chunk)

        new_size = os.path.getsize(output_path)
        duration = time.perf_counter() - t0

        if verify:
            with laspy.open(output_path) as out_reader:
                out_pts = out_reader.header.point_count
                if out_pts != total_pts:
                    raise ValueError(
                        f"Point count mismatch: expected {total_pts}, got {out_pts}"
                    )

        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            orig_size=orig_size,
            new_size=new_size,
            point_count=total_pts,
            duration_sec=duration,
        )

    except Exception as e:
        duration = time.perf_counter() - t0
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=False,
            orig_size=orig_size,
            new_size=0,
            point_count=total_pts,
            duration_sec=duration,
            error_message=str(e),
        )


def convert_file_laszip(
    input_path: str,
    output_path: str,
    laszip_bin: str,
    verify: bool = True
) -> ConversionResult:
    """Convert LAS/LAZ using external laszip executable."""
    import laspy

    t0 = time.perf_counter()
    orig_size = os.path.getsize(input_path)
    total_pts = 0

    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cmd = [laszip_bin, "-i", input_path, "-o", output_path]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            raise RuntimeError(f"laszip failed ({res.returncode}): {res.stderr or res.stdout}")

        if not os.path.exists(output_path):
            raise FileNotFoundError(f"laszip did not produce output: {output_path}")

        new_size = os.path.getsize(output_path)
        duration = time.perf_counter() - t0

        if verify:
            with laspy.open(output_path) as out_reader:
                total_pts = out_reader.header.point_count

        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            orig_size=orig_size,
            new_size=new_size,
            point_count=total_pts,
            duration_sec=duration,
        )

    except Exception as e:
        duration = time.perf_counter() - t0
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=False,
            orig_size=orig_size,
            new_size=0,
            point_count=total_pts,
            duration_sec=duration,
            error_message=str(e),
        )


def convert_file(
    input_path: str,
    output_path: Optional[str] = None,
    engine: str = "auto",
    decompress: bool = False,
    verify: bool = True,
    delete_original: bool = False,
    skip_existing: bool = False
) -> ConversionResult:
    """
    Main single-file conversion router.
    Detects extensions and dispatches to appropriate engine.
    """
    input_p = Path(input_path).resolve()
    if not input_p.is_file():
        return ConversionResult(
            input_path=str(input_p),
            output_path="",
            success=False,
            orig_size=0,
            new_size=0,
            point_count=0,
            duration_sec=0.0,
            error_message=f"Input file not found: {input_p}",
        )

    # Determine default output path
    target_ext = ".las" if decompress else ".laz"
    if output_path is None:
        out_p = input_p.with_suffix(target_ext)
    else:
        out_p = Path(output_path).resolve()
        if out_p.is_dir():
            out_p = out_p / (input_p.stem + target_ext)

    # Prevent overwriting source
    if out_p == input_p:
        return ConversionResult(
            input_path=str(input_p),
            output_path=str(out_p),
            success=False,
            orig_size=input_p.stat().st_size,
            new_size=0,
            point_count=0,
            duration_sec=0.0,
            error_message="Input and output paths are identical.",
        )

    if skip_existing and out_p.is_file() and out_p.stat().st_size > 0:
        return ConversionResult(
            input_path=str(input_p),
            output_path=str(out_p),
            success=True,
            orig_size=input_p.stat().st_size,
            new_size=out_p.stat().st_size,
            point_count=0,
            duration_sec=0.0,
            error_message="Skipped (already exists)",
        )

    laszip_bin = find_laszip_binary()
    selected_engine = engine.lower()

    if selected_engine == "auto":
        selected_engine = "laszip" if laszip_bin else "laspy"

    if selected_engine == "laszip" and laszip_bin:
        result = convert_file_laszip(str(input_p), str(out_p), laszip_bin, verify=verify)
    else:
        result = convert_file_laspy(str(input_p), str(out_p), verify=verify)

    if result.success and delete_original:
        try:
            os.remove(input_p)
        except OSError as e:
            result.error_message = f"Converted successfully, but could not delete original: {e}"

    return result


# ---------------------------------------------------------------------------
# Batch Conversion Engine
# ---------------------------------------------------------------------------

def find_files_to_convert(
    input_targets: str | List[str],
    decompress: bool = False,
    recursive: bool = False
) -> List[Path]:
    """Find all matching point cloud files from file path(s) or directory."""
    if isinstance(input_targets, (str, Path)):
        targets = [str(input_targets)]
    else:
        targets = [str(t) for t in input_targets]

    found: List[Path] = []
    pattern = "*.laz" if decompress else "*.las"

    for target in targets:
        p = Path(target).resolve()
        if p.is_file():
            if p not in found:
                found.append(p)
        elif p.is_dir():
            files = list(p.rglob(pattern)) if recursive else list(p.glob(pattern))
            for f in sorted(files):
                if f not in found:
                    found.append(f)
        else:
            parent = p.parent
            if parent.is_dir():
                for f in sorted(list(parent.glob(p.name))):
                    if f not in found:
                        found.append(f)
    return found


def batch_convert(
    input_files: List[Path],
    output_target: Optional[str] = None,
    engine: str = "auto",
    decompress: bool = False,
    cores: int = 4,
    verify: bool = True,
    delete_original: bool = False,
    skip_existing: bool = False,
    progress_callback: Optional[Callable[[int, int, ConversionResult], None]] = None,
    output_dir: Optional[str] = None,
) -> List[ConversionResult]:
    """Convert multiple files concurrently using process pool."""
    if output_target is None and output_dir is not None:
        output_target = output_dir
    results: List[ConversionResult] = []
    total = len(input_files)

    if total == 0:
        return results

    target_ext = ".las" if decompress else ".laz"
    tasks: List[Tuple[str, str]] = []

    # If single file and output_target has a matching point cloud file extension, treat as destination file
    single_file_target = (
        len(input_files) == 1
        and output_target is not None
        and Path(output_target).suffix.lower() in [".las", ".laz"]
    )

    if single_file_target:
        tasks.append((str(input_files[0]), str(Path(output_target).resolve())))
    else:
        out_dir = Path(output_target).resolve() if output_target else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
        for in_file in input_files:
            if out_dir:
                out_file = str(out_dir / (in_file.stem + target_ext))
            else:
                out_file = str(in_file.with_suffix(target_ext))
            tasks.append((str(in_file), out_file))

    num_workers = max(1, min(cores, total, os.cpu_count() or 4))

    if num_workers == 1:
        for idx, (in_f, out_f) in enumerate(tasks, start=1):
            res = convert_file(
                in_f, out_f, engine=engine, decompress=decompress,
                verify=verify, delete_original=delete_original,
                skip_existing=skip_existing
            )
            results.append(res)
            if progress_callback:
                progress_callback(idx, total, res)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_idx = {
                executor.submit(
                    convert_file, in_f, out_f, engine, decompress, verify, delete_original, skip_existing
                ): (idx, in_f)
                for idx, (in_f, out_f) in enumerate(tasks, start=1)
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_to_idx):
                completed += 1
                res = future.result()
                results.append(res)
                if progress_callback:
                    progress_callback(completed, total, res)

    return results


# ---------------------------------------------------------------------------
# CLI Formatting & Runner
# ---------------------------------------------------------------------------

def format_size(bytes_val: int) -> str:
    """Format bytes to human readable string (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0 or unit == "TB":
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} B"


def run_cli(args: argparse.Namespace) -> int:
    """Handle command-line execution."""
    files = find_files_to_convert(args.input, decompress=args.decompress, recursive=args.recursive)
    if not files:
        print(f"[!] No matching {'LAZ' if args.decompress else 'LAS'} files found for: {args.input}")
        return 1

    action_label = "Decompressing (LAZ -> LAS)" if args.decompress else "Compressing (LAS -> LAZ)"
    print(f"\n=======================================================")
    print(f"  TreeAIBox Point Cloud Converter: {action_label}")
    print(f"=======================================================")
    print(f"Files to process: {len(files)}")
    print(f"Engine:           {args.engine} (laszip binary: {find_laszip_binary() is not None})")
    print(f"Cores:            {args.cores}")
    print(f"Output directory: {args.output or 'Same as input files'}")
    print(f"Verify integrity: {args.verify}")
    print(f"Delete original:  {args.delete_original}\n")

    t_start = time.perf_counter()

    def print_progress(done: int, total: int, res: ConversionResult):
        fname = Path(res.input_path).name
        if res.success:
            ratio_info = f"{format_size(res.orig_size)} -> {format_size(res.new_size)} (-{res.savings_percent:.1f}%)"
            print(f"[{done}/{total}] OK: {fname} | {ratio_info} in {res.duration_sec:.2f}s")
        else:
            print(f"[{done}/{total}] FAILED: {fname} | Error: {res.error_message}")

    results = batch_convert(
        input_files=files,
        output_dir=args.output,
        engine=args.engine,
        decompress=args.decompress,
        cores=args.cores,
        verify=args.verify,
        delete_original=args.delete_original,
        skip_existing=args.skip_existing,
        progress_callback=print_progress,
    )

    t_total = time.perf_counter() - t_start

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    total_orig = sum(r.orig_size for r in successful)
    total_new = sum(r.new_size for r in successful)
    saved_bytes = max(0, total_orig - total_new)
    saved_pct = (saved_bytes / total_orig * 100.0) if total_orig > 0 else 0.0

    print("\n" + "=" * 55)
    print("CONVERSION SUMMARY")
    print("=" * 55)
    print(f"Total files:      {len(results)} ({len(successful)} successful, {len(failed)} failed)")
    print(f"Total time:       {t_total:.2f} seconds")
    print(f"Original size:    {format_size(total_orig)}")
    print(f"Compressed size:  {format_size(total_new)}")
    print(f"Disk space saved: {format_size(saved_bytes)} ({saved_pct:.1f}% reduction)")

    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# Graphical User Interface (PyQt6 / PySide6)
# ---------------------------------------------------------------------------

def launch_gui():
    """Launch the interactive PyQt6/PySide6 desktop GUI."""
    try:
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QLabel, QPushButton, QFileDialog, QProgressBar, QTableWidget,
            QTableWidgetItem, QHeaderView, QCheckBox, QComboBox, QSpinBox,
            QGroupBox, QMessageBox, QFrame
        )
        from PyQt6.QtCore import Qt, QThread, pyqtSignal
        from PyQt6.QtGui import QFont, QIcon, QColor
    except ImportError:
        try:
            from PySide6.QtWidgets import (
                QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QLabel, QPushButton, QFileDialog, QProgressBar, QTableWidget,
                QTableWidgetItem, QHeaderView, QCheckBox, QComboBox, QSpinBox,
                QGroupBox, QMessageBox, QFrame
            )
            from PySide6.QtCore import Qt, QThread, Signal as pyqtSignal
            from PySide6.QtGui import QFont, QIcon, QColor
        except ImportError:
            print("[!] PyQt6 or PySide6 is required to run the GUI. Use CLI mode instead.")
            sys.exit(1)

    class ConversionWorker(QThread):
        progress_updated = pyqtSignal(int, int, object)
        finished_all = pyqtSignal(list)

        def __init__(self, files, output_dir, engine, decompress, cores, verify, delete_orig):
            super().__init__()
            self.files = files
            self.output_dir = output_dir
            self.engine = engine
            self.decompress = decompress
            self.cores = cores
            self.verify = verify
            self.delete_orig = delete_orig

        def run(self):
            def callback(done, total, res):
                self.progress_updated.emit(done, total, res)

            results = batch_convert(
                input_files=self.files,
                output_dir=self.output_dir,
                engine=self.engine,
                decompress=self.decompress,
                cores=self.cores,
                verify=self.verify,
                delete_original=self.delete_orig,
                progress_callback=callback,
            )
            self.finished_all.emit(results)

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("TreeAIBox - LAS to LAZ Converter")
            self.resize(950, 650)
            self.selected_files: List[Path] = []
            self.worker: Optional[ConversionWorker] = None
            self._init_ui()

        def _init_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)

            # Top Header Card
            header_box = QGroupBox("Input Selection")
            header_layout = QVBoxLayout(header_box)

            btn_row = QHBoxLayout()
            self.btn_add_files = QPushButton("Select LAS Files...")
            self.btn_add_files.clicked.connect(self._select_files)
            btn_row.addWidget(self.btn_add_files)

            self.btn_add_folder = QPushButton("Select Folder...")
            self.btn_add_folder.clicked.connect(self._select_folder)
            btn_row.addWidget(self.btn_add_folder)

            self.btn_clear = QPushButton("Clear List")
            self.btn_clear.clicked.connect(self._clear_files)
            btn_row.addWidget(self.btn_clear)

            header_layout.addLayout(btn_row)

            # Options Box
            opts_box = QGroupBox("Conversion Settings")
            opts_layout = QHBoxLayout(opts_box)

            opts_layout.addWidget(QLabel("Output Mode:"))
            self.mode_combo = QComboBox()
            self.mode_combo.addItems(["Compress (LAS -> LAZ)", "Decompress (LAZ -> LAS)"])
            self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
            opts_layout.addWidget(self.mode_combo)

            opts_layout.addWidget(QLabel("Engine:"))
            self.engine_combo = QComboBox()
            self.engine_combo.addItems(["auto", "laszip (fastest)", "laspy (lazrs)"])
            opts_layout.addWidget(self.engine_combo)

            opts_layout.addWidget(QLabel("Parallel Cores:"))
            self.spin_cores = QSpinBox()
            self.spin_cores.setRange(1, os.cpu_count() or 8)
            self.spin_cores.setValue(min(4, os.cpu_count() or 4))
            opts_layout.addWidget(self.spin_cores)

            self.chk_verify = QCheckBox("Verify Point Counts")
            self.chk_verify.setChecked(True)
            opts_layout.addWidget(self.chk_verify)

            self.chk_delete_orig = QCheckBox("Delete Originals")
            self.chk_delete_orig.setChecked(False)
            opts_layout.addWidget(self.chk_delete_orig)

            # Output folder row
            out_row = QHBoxLayout()
            out_row.addWidget(QLabel("Output Folder (Optional):"))
            self.lbl_out_dir = QLabel("<Same as original files>")
            self.lbl_out_dir.setStyleSheet("color: #666; font-style: italic;")
            out_row.addWidget(self.lbl_out_dir, 1)

            self.btn_set_out = QPushButton("Browse...")
            self.btn_set_out.clicked.connect(self._select_output_folder)
            out_row.addWidget(self.btn_set_out)

            self.btn_reset_out = QPushButton("Reset")
            self.btn_reset_out.clicked.connect(self._reset_output_folder)
            out_row.addWidget(self.btn_reset_out)

            header_layout.addLayout(out_row)

            layout.addWidget(header_box)
            layout.addWidget(opts_box)

            # File Table
            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels(["File Name", "Status", "Original Size", "Output Size", "Savings / Duration"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            layout.addWidget(self.table)

            # Progress Bar & Action Button
            action_row = QHBoxLayout()
            self.progress_bar = QProgressBar()
            self.progress_bar.setValue(0)
            action_row.addWidget(self.progress_bar, 1)

            self.btn_start = QPushButton("Start Conversion")
            self.btn_start.setStyleSheet("font-weight: bold; padding: 6px 15px; font-size: 13px;")
            self.btn_start.clicked.connect(self._start_conversion)
            action_row.addWidget(self.btn_start)

            layout.addLayout(action_row)

            # Summary Footer
            self.lbl_summary = QLabel("Ready. Select files or a folder to convert.")
            self.lbl_summary.setStyleSheet("font-weight: bold; color: #333;")
            layout.addWidget(self.lbl_summary)

            self.custom_output_dir: Optional[str] = None

        def _on_mode_change(self):
            decompress = self.mode_combo.currentIndex() == 1
            if decompress:
                self.btn_add_files.setText("Select LAZ Files...")
            else:
                self.btn_add_files.setText("Select LAS Files...")

        def _select_files(self):
            decompress = self.mode_combo.currentIndex() == 1
            filter_str = "LAZ Files (*.laz)" if decompress else "LAS Files (*.las)"
            files, _ = QFileDialog.getOpenFileNames(self, "Select Point Cloud Files", "", f"{filter_str};;All Files (*.*)")
            if files:
                for f in files:
                    p = Path(f)
                    if p not in self.selected_files:
                        self.selected_files.append(p)
                self._populate_table()

        def _select_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Point Clouds")
            if folder:
                decompress = self.mode_combo.currentIndex() == 1
                found = find_files_to_convert(folder, decompress=decompress, recursive=True)
                for p in found:
                    if p not in self.selected_files:
                        self.selected_files.append(p)
                self._populate_table()

        def _clear_files(self):
            self.selected_files.clear()
            self.table.setRowCount(0)
            self.progress_bar.setValue(0)
            self.lbl_summary.setText("List cleared.")

        def _select_output_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
            if folder:
                self.custom_output_dir = folder
                self.lbl_out_dir.setText(folder)
                self.lbl_out_dir.setStyleSheet("color: #000; font-weight: bold;")

        def _reset_output_folder(self):
            self.custom_output_dir = None
            self.lbl_out_dir.setText("<Same as original files>")
            self.lbl_out_dir.setStyleSheet("color: #666; font-style: italic;")

        def _populate_table(self):
            self.table.setRowCount(len(self.selected_files))
            total_size = 0
            for idx, p in enumerate(self.selected_files):
                size = p.stat().st_size if p.exists() else 0
                total_size += size
                self.table.setItem(idx, 0, QTableWidgetItem(p.name))
                self.table.setItem(idx, 1, QTableWidgetItem("Queued"))
                self.table.setItem(idx, 2, QTableWidgetItem(format_size(size)))
                self.table.setItem(idx, 3, QTableWidgetItem("-"))
                self.table.setItem(idx, 4, QTableWidgetItem("-"))
            self.lbl_summary.setText(f"{len(self.selected_files)} files selected ({format_size(total_size)} total)")

        def _start_conversion(self):
            if not self.selected_files:
                QMessageBox.warning(self, "No Files", "Please select at least one LAS/LAZ file to convert.")
                return

            delete_orig = self.chk_delete_orig.isChecked()
            if delete_orig:
                ans = QMessageBox.question(
                    self, "Confirm Delete",
                    "You have checked 'Delete Originals'. Source files will be deleted upon successful conversion.\n\nProceed?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return

            self.btn_start.setEnabled(False)
            self.progress_bar.setMaximum(len(self.selected_files))
            self.progress_bar.setValue(0)

            decompress = self.mode_combo.currentIndex() == 1
            engine = self.engine_combo.currentText().split()[0]
            cores = self.spin_cores.value()
            verify = self.chk_verify.isChecked()

            self.worker = ConversionWorker(
                files=list(self.selected_files),
                output_dir=self.custom_output_dir,
                engine=engine,
                decompress=decompress,
                cores=cores,
                verify=verify,
                delete_orig=delete_orig
            )
            self.worker.progress_updated.connect(self._on_file_done)
            self.worker.finished_all.connect(self._on_finished)
            self.worker.start()

        def _on_file_done(self, done: int, total: int, res: ConversionResult):
            self.progress_bar.setValue(done)
            p = Path(res.input_path)
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).text() == p.name:
                    if res.success:
                        self.table.setItem(row, 1, QTableWidgetItem("Completed"))
                        self.table.item(row, 1).setForeground(QColor("green"))
                        self.table.setItem(row, 3, QTableWidgetItem(format_size(res.new_size)))
                        savings_str = f"-{res.savings_percent:.1f}% ({res.duration_sec:.2f}s)"
                        self.table.setItem(row, 4, QTableWidgetItem(savings_str))
                    else:
                        self.table.setItem(row, 1, QTableWidgetItem("Failed"))
                        self.table.item(row, 1).setForeground(QColor("red"))
                        self.table.setItem(row, 4, QTableWidgetItem(res.error_message[:40]))
                    break

        def _on_finished(self, results: List[ConversionResult]):
            self.btn_start.setEnabled(True)
            success = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            orig_tot = sum(r.orig_size for r in success)
            new_tot = sum(r.new_size for r in success)
            saved = max(0, orig_tot - new_tot)
            saved_pct = (saved / orig_tot * 100.0) if orig_tot > 0 else 0.0

            msg = f"Done! {len(success)}/{len(results)} converted successfully. Saved: {format_size(saved)} ({saved_pct:.1f}%)."
            self.lbl_summary.setText(msg)
            QMessageBox.information(self, "Conversion Complete", msg)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert LAS point clouds to compressed LAZ (and vice versa).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        nargs="+",
        type=str,
        help="One or more input LAS/LAZ files, folders, or glob patterns.",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output file or output directory. If omitted, saves next to source files.",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively scan subdirectories when input is a folder.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files if target LAZ/LAS already exists.",
    )
    parser.add_argument(
        "-d", "--decompress",
        action="store_true",
        help="Decompress LAZ files to uncompressed LAS.",
    )
    parser.add_argument(
        "-c", "--cores",
        type=int,
        default=4,
        help="Number of concurrent worker threads/processes for batch conversion (default: 4).",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "laszip", "laspy"],
        default="auto",
        help="Compression engine: 'auto' (laszip binary if found, else laspy), 'laszip', or 'laspy'.",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="Skip point count verification after conversion.",
    )
    parser.add_argument(
        "--delete-original",
        action="store_true",
        help="Delete original files after successful conversion and verification.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the interactive desktop GUI.",
    )

    args = parser.parse_args()

    # If no input is specified or --gui flag is passed, launch GUI
    if args.gui or len(sys.argv) == 1 or args.input is None:
        launch_gui()
    else:
        sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
