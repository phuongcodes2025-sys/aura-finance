import os

os.environ.setdefault("DATABASE_PATH", "/tmp/aura.sqlite3")  # Vercel is read-only except /tmp

from app.main import app  # noqa: E402,F401
