"""
Backward-compatibility forwarder shim.
The LAS to LAZ converter script is located at scripts/pointcloud_processing/las_to_laz.py.
"""
import runpy
from pathlib import Path

target = Path(__file__).resolve().parent / "pointcloud_processing" / "las_to_laz.py"
runpy.run_path(str(target), run_name="__main__")
