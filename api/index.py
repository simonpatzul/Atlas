import sys
from pathlib import Path

ATLAS_DATA = Path(__file__).resolve().parents[1] / "atlas-data"
sys.path.insert(0, str(ATLAS_DATA))

from main import app as atlas_app  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "/")
        # Strip /api prefix when present so FastAPI receives /context/..., /market/..., etc.
        if path.startswith("/api"):
            stripped = path[4:] or "/"
            scope = {**scope, "path": stripped, "raw_path": stripped.encode()}
    await atlas_app(scope, receive, send)
