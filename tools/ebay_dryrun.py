"""Branch override for Task 14 Phase B: run Currys clearance probe (exactly 5 Browse calls)."""
import runpy
import sys
from pathlib import Path
sys.argv = [str(Path(__file__).resolve().parents[1] / "scripts" / "ebay_clearance_probe.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
