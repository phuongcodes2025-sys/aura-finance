import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_PATH", "/tmp/aura.sqlite3")  # Vercel is read-only except /tmp

from app.main import app  # noqa: E402,F401
