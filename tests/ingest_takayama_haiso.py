"""One-off: ingest 高山市 shipment CSVs (4 files)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, ingest_csv


BASE = Path(r"C:\Users\info\ヒダカラ Dropbox\HIDAKARA ALL\17_本巣市ふるさと納税\99.分析用\高山市")
HAISO_FILES = [
    BASE / "Takayama_haiso①.csv",
    BASE / "Takayama_haiso②.csv",
    BASE / "Takayama_haiso③.csv",
    BASE / "Takayama_haiso④.csv",
]


def main() -> None:
    conn = ensure_db()

    takayama = next(m for m in list_municipalities(conn) if m["name"] == "高山市")
    print(f"Target: {takayama}")

    print()
    for csv_path in HAISO_FILES:
        if not csv_path.exists():
            print(f"SKIP (not found): {csv_path}")
            continue
        with open(csv_path, "rb") as f:
            result = ingest_csv(conn, f, takayama["id"], file_name=csv_path.name)
        print(result.summary())

    print()
    print("=== Counts per municipality ===")
    print(get_counts_per_municipality(conn).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
