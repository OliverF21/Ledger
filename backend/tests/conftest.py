from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Some environments set DATABASE_URL to the literal "DATABASE_URL=sqlite:///...",
# which is not a SQLAlchemy URL and breaks any test that imports app.database.
_raw_db_url = os.environ.get("DATABASE_URL")
if _raw_db_url and _raw_db_url.startswith("DATABASE_URL="):
    os.environ["DATABASE_URL"] = _raw_db_url.split("=", 1)[1]
