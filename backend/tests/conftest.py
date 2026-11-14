import sys
from pathlib import Path

# Make the backend package importable when running pytest from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROTOCOLS_DIR = Path(__file__).resolve().parents[2] / "protocols"
