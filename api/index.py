import sys
from pathlib import Path

ATLAS_DATA = Path(__file__).resolve().parents[1] / "atlas-data"
sys.path.insert(0, str(ATLAS_DATA))

from main import app  # noqa: E402
