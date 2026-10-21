# TreeAIBox Scripts

This directory contains modular utility scripts, visualization GUIs, processing pipelines, and data tools for the **TreeAIBox** ecosystem.

---

## Directory Organization

```
scripts/
├── visualization/                 # 3D interactive viewers & slice visualization tools
│   ├── treeAIbox_Enhancer.py     # Comprehensive PyQt6+PyVista tree enhancement GUI
│   ├── tree_visu.py              # Modern Tree Visualizer GUI (run_modern_tree_visu.ps1)
│   ├── tree_visualizer_gui.py    # Basic Tree Visualizer GUI (run_tree_visualizer.bat)
│   ├── plane_cut_visualization.py# Interactive horizontal plane cut with RANSAC fitting
│   ├── simple_plane_visualization.py # Basic plane slice viewer
│   └── branch_split_detection.py # 8m height plane DBSCAN clustering
│
├── stem_reconstruction/           # Tree component extraction & circle/cylinder fitting
│   ├── component_extraction_connectivity.py # Advanced connectivity-based trunk & branch extraction (v2)
│   ├── component_extraction.py   # Baseline trunk and branch extraction (v1)
│   ├── multi_height_circle_fitting.py       # Multi-height stem cross-section circle fitting
│   ├── circle_fitting_reconstruction.py     # Taubin / Pratt / Kåsa / RANSAC circle fitting
│   └── generate_sample_stem.py   # Synthetic stem point cloud generator
│
├── field_assignment/              # Ground truth matching & GIS integration
│   ├── semantic_field_assignment.py         # Hungarian matching engine (spatial + DBH + height)
│   ├── semantic_field_assignment_gui.py     # PySide6/PyQt6 graphical matching interface
│   └── run_web_app.py            # Launcher for Django TreeToolBox Web Studio
│
├── volume_metrics/                # Post-processing volume statistics & center calculations
│   ├── volume_summary_report_gui.py         # PyQt6 volume JSON report generator & DBH calculator
│   └── extract_tree_centers.py   # CLI tool to extract XY centers & DBH to CSV / GeoJSON
│
├── pointcloud_processing/         # Point cloud filtering, cleaning, RGB repair & vectorization
│   ├── las_to_laz.py             # High-performance LAS <-> LAZ converter (CLI & GUI)
│   ├── las_to_polygon_gui.py     # PyQt6 GUI for generating 2D boundary polygons (Shapefile/GeoJSON)
│   ├── las_rgb_checker.py        # Inspects LAS/LAZ files for valid RGB channels
│   ├── rgb_restoration_tool.py   # Restores RGB channels from raw LAS to processed LAS via KDTree
│   ├── filter_by_scalar_field.py # Filters LAS points by scalar field criteria
│   ├── remove_ground_points.py   # Dedicated ground point removal filter
│   ├── apply_scalar_field_rules.py # Rule-based scalar field modifier (JSON/YAML)
│   ├── inspect_las.py            # Quick CLI LAS header and scalar field inspector
│   └── inspect_scalar_fields.py  # GUI/CLI scalar field distribution analyzer
│
├── Processing_WorkFlow/           # USDA Forest Service FUSION LiDAR processing pipeline
│   ├── run_fusion_workflow_gui.py# PySide6 FUSION workflow GUI
│   ├── run_fusion_workflow.py    # FUSION workflow engine
│   ├── groundfilter_gui.py       # GroundFilter & DTM generation GUI
│   ├── clip_plots_gui.py         # PolyClipData GUI
│   ├── gridmetrics_gui.py        # GridMetrics GUI
│   ├── cloudmetrics_gui.py       # CloudMetrics GUI
│   ├── normalize_las_gui.py      # LAS elevation normalization GUI
│   ├── app_settings.db           # SQLite settings store for workflow GUIs
│   └── workflow_guide.md         # Guide for extending FUSION workflows
│
├── Batch Files/                   # Windows batch scripts for FUSION CLI tools
│   ├── clip_plots.bat
│   ├── generate_dtm.bat
│   ├── groundfilter.bat
│   ├── normalize_stands.bat
│   ├── process_single_stand_grid.bat
│   └── run_cloudmetrics.bat
│
├── test_data/                     # Sample and test point cloud datasets
│   ├── test_output_branch_1.csv
│   └── test_output_trunk.csv
│
├── utils/                         # Maintenance and diagnostic tools
│   └── find_empty_files.py       # Workspace empty file scanner
│
├── error_logs/                    # Runtime exception logs from treeAIbox_Enhancer
│
└── _archive/                      # Retired 0-byte orphan stubs & empty logs
    ├── batch_tree_component_gui.py (0 bytes)
    ├── las_to_poylgon.py           (0 bytes, typo in original name)
    ├── groundfilter_sample.bat     (0 bytes)
    ├── thin_overlap.bat            (0 bytes)
    └── empty_logs/                 (70 empty log files)
```

---

## Quick Launch Reference

### Tree Visualizers
```powershell
# Modern Tree Visualizer GUI:
.\run_modern_tree_visu.ps1

# Basic Tree Visualizer GUI:
.\run_tree_visualizer.ps1
# or batch:
.\run_tree_visualizer.bat

# TreeAIBox Enhancer:
.\.venv\Scripts\python.exe scripts\visualization\treeAIbox_Enhancer.py
```

### Field Assignment
```powershell
# GUI Application:
.\.venv\Scripts\python.exe scripts\field_assignment\semantic_field_assignment_gui.py

# CLI Hungarian Matcher:
.\.venv\Scripts\python.exe scripts\field_assignment\semantic_field_assignment.py --help

# Django Web Studio:
.\.venv\Scripts\python.exe scripts\field_assignment\run_web_app.py
```

### Volume Summary Report
```powershell
.\.venv\Scripts\python.exe scripts\volume_metrics\volume_summary_report_gui.py
```

### Point Cloud to Polygon GUI
```powershell
.\.venv\Scripts\python.exe scripts\pointcloud_processing\las_to_polygon_gui.py
```

### LAS to LAZ Converter
```powershell
# Interactive GUI:
.\run_las_to_laz.bat
# or PowerShell:
.\run_las_to_laz.ps1

# CLI single file or folder:
.\.venv\Scripts\python.exe scripts\pointcloud_processing\las_to_laz.py -i "path/to/file.las"
.\.venv\Scripts\python.exe scripts\pointcloud_processing\las_to_laz.py -i "path/to/folder" --recursive --cores 4
```
