import csv
import io
import sqlite3
import urllib.request

FRED_DGS3MO = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"

def trailing_rf(default=0.05) -> float:
    """Latest 3-month T-bill yield from FRED, as a decimal."""
    try:
        with urllib.request.urlopen(FRED_DGS3MO, timeout=10) as resp:
            text = resp.read().decode()
        latest = None
        for row in csv.DictReader(io.StringIO(text)):
            raw = row.get("DGS3MO", ".")
            if raw and raw != ".":
                latest = float(raw)
        return latest / 100.0 if latest is not None else default
    except Exception:
        return default

rf_rate = trailing_rf()
print(rf_rate)