"""
Backward-compatibility forwarder shim.
The Tree Visualizer GUI script has been relocated to scripts/visualization/tree_visualizer_gui.py.
"""
import runpy
from pathlib import Path

target = Path(__file__).resolve().parent / "visualization" / "tree_visualizer_gui.py"
runpy.run_path(str(target), run_name="__main__")
