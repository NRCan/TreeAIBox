"""
Backward-compatibility forwarder shim.
The Web Studio launcher has been relocated to scripts/field_assignment/run_web_app.py.
"""
import runpy
from pathlib import Path

target = Path(__file__).resolve().parent / "field_assignment" / "run_web_app.py"
runpy.run_path(str(target), run_name="__main__")
