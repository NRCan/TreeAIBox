"""
Backward-compatibility forwarder shim.
The modern Tree Visualizer script has been relocated to scripts/visualization/tree_visu.py.
"""
import runpy
from pathlib import Path

target = Path(__file__).resolve().parent / "visualization" / "tree_visu.py"
runpy.run_path(str(target), run_name="__main__")
