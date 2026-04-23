import sys
from pathlib import Path

ATLAS_DATA = Path(__file__).resolve().parents[1] / "atlas-data"
sys.path.insert(0, str(ATLAS_DATA))

from main import app as atlas_app  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http" and scope.get("path", "").startswith("/api"):
        scope = dict(scope)
        stripped_path = scope["path"][4:] or "/"
        scope["path"] = stripped_path
        scope["raw_path"] = stripped_path.encode("utf-8")
    await atlas_app(scope, receive, send)
