"""
Backward-compatibility forwarder shim.
The TreeAIBox Enhancer application has been relocated to scripts/visualization/treeAIbox_Enhancer.py.
"""
import runpy
from pathlib import Path

target = Path(__file__).resolve().parent / "visualization" / "treeAIbox_Enhancer.py"
runpy.run_path(str(target), run_name="__main__")
