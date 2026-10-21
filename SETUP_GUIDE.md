# TreeAIBox Standalone Setup & Quickstart

This repository is configured on the **`TreeAIBox-Standalone`** branch with full **NVIDIA CUDA acceleration** on your NVIDIA GeForce RTX 3090.

---

## Environment Overview

- **Repository**: `arunbiju969/TreeAIBox`
- **Branch**: `TreeAIBox-Standalone`
- **Location**: `C:\Users\w0491597\Documents\Projects\TreeAIBox`
- **Python Version**: CPython 3.12 (managed in `.venv`)
- **PyTorch**: `2.6.0+cu124` (with CUDA 12.4 support)
- **GPU Detected**: `NVIDIA GeForce RTX 3090` (24 GB VRAM)
- **Key Installed Packages**:
  - `torch`, `torchvision`, `torchaudio` (CUDA 12.4 enabled)
  - `PyQt6`, `PyQt6-WebEngine`, `PySide6`
  - `pyvista`, `pyvistaqt`, `vtk`
  - `laspy`, `geopandas`, `pyogrio`, `shapely`, `pyshp`, `rasterio`
  - `scikit-learn`, `scikit-image`, `scipy`, `numpy`, `pandas`, `matplotlib`
  - `cut_pursuit_py`, `circle_fit`, `numpy_indexed`, `numpy_groupies`
  - `timm`, `litellm`, `requests`, `django`

---

## Launching Applications

### 1. Main Standalone Application (TreeAIBox GUI)
Run the batch file or PowerShell script:
- **Batch**: Double-click or run `run_treeaibox.bat`
- **PowerShell**:
  ```powershell
  .\run_treeaibox.ps1
  ```
- Or run directly:
  ```powershell
  .\.venv\Scripts\python.exe TreeAIBox.py
  ```

> In standalone mode, TreeAIBox operates independently without requiring CloudCompare. When started, it checks CUDA availability, detects your RTX 3090, and automatically checks the **"Use GPU (CUDA)"** option in the user interface.

### 2. Standalone Tree Visualizer GUI
Visualize individual tree point clouds and scalar fields (`itc`):
- **Batch**: Double-click or run `run_tree_visualizer.bat`
- **PowerShell**:
  ```powershell
  .\run_tree_visualizer.ps1
  ```
- Or modern variant:
  ```powershell
  .\run_modern_tree_visu.ps1
  ```

### 3. TreeAIBox Enhancer GUI (`treeAIbox_Enhancer.py`)
Advanced tree visualization, multi-layer LAS inspection, 2D polygon selection, trunk & branch reconstruction, volume estimation, GDB shapefile overlay, and AI quality evaluation:
- **Batch**: Double-click or run `run_treeaibox_enhancer.bat`
- **PowerShell**:
  ```powershell
  .\run_treeaibox_enhancer.ps1
  ```
- Or run directly:
  ```powershell
  .\.venv\Scripts\python.exe scripts\visualization\treeAIbox_Enhancer.py
  ```

### 4. Automated Segmentation Refiner (`refine_segmented_plots.py`)
Automated post-processor that cleans false stumps (< 2.5m, < 120 pts), disentangles overlapping trees with multiple stem cores, and updates inventory metrics:
- **Batch**: Double-click or run `run_refine_plots.bat`
- **PowerShell**:
  ```powershell
  .\run_refine_plots.ps1
  ```
- Or run directly:
  ```powershell
  .\.venv\Scripts\python.exe scripts\pointcloud_processing\refine_segmented_plots.py
  ```

### 5. Side-by-Side 3D Plot Comparison GUI (`compare_segmentation_gui.py`)
Synchronized 3D dual-viewport GUI to visually compare Original vs. Refined segmentations across all plots with linked camera rotation and metrics:
- **Batch**: Double-click or run `run_compare_plots.bat`
- **PowerShell**:
  ```powershell
  .\run_compare_plots.ps1
  ```
- Or run directly:
  ```powershell
  .\.venv\Scripts\python.exe scripts\visualization\compare_segmentation_gui.py
  ```
- Or open HTML Report:
  Double-click `D:\LLR DATA\Clipped_Plots\Segmented_Results\Refined\visual_comparison_report.html`

### 5. LAS to LAZ Converter (`las_to_laz.py`)
Lossless compression of LAS files to LAZ (70%+ space savings) with multi-core batch processing and integrity checks:
- **Batch**: Double-click or run `run_las_to_laz.bat`
- **PowerShell**:
  ```powershell
  .\run_las_to_laz.ps1
  ```
- Or run directly (CLI / GUI):
  ```powershell
  # Launch Interactive GUI:
  .\run_las_to_laz.ps1 --gui

  # Convert folder with multi-core acceleration:
  .\.venv\Scripts\python.exe scripts\pointcloud_processing\las_to_laz.py -i "D:\LLR DATA\Clipped_Plots" --cores 4
  ```


---

## Verifying CUDA Acceleration

You can verify CUDA status anytime by running:
```powershell
.\.venv\Scripts\python.exe -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0))"
```

Expected output:
```text
CUDA Available: True
Device: NVIDIA GeForce RTX 3090
```

---

## Model Zoo & Pretrained Weights

Pretrained model weights are stored in:
- Local Cache: `%LOCALAPPDATA%\CloudCompare\TreeAIBox\models`
- Repository: `models/`

The pretrained UAV and TreeIsoNet models (`treefiltering_uav`, `treeisonet_uav_mixedwood_crownoff`, `treeisonet_uav_mixedwood_stemcls`, `treeisonet_uav_mixedwood_treeloc`) have already been synced to the local model cache and verified for CUDA tensor inference. Additional models are automatically downloaded on demand when selected in the UI.
