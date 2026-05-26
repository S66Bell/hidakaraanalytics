"""One-off: ingest 郡上市 CSVs (kifu + haiso)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import add_municipality, ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, ingest_csv


BASE = Path(r"C:\Users\info\ヒダカラ Dropbox\HIDAKARA ALL\17_本巣市ふるさと納税\99.分析用\郡上市")
FILES = [
    BASE / "gujohaiso.csv",
    BASE / "gujo_kifu.csv",
]


def main() -> None:
    conn = ensure_db()

    existing = [m for m in list_municipalities(conn) if m["name"] == "郡上市"]
    if existing:
        gujo = existing[0]
        print(f"Found existing: {gujo}")
    else:
        new_id = add_municipality(conn, "郡上市", "gujo")
        gujo = next(m for m in list_municipalities(conn) if m["id"] == new_id)
        print(f"Created: {gujo}")

    print()
    for csv_path in FILES:
        if not csv_path.exists():
            print(f"SKIP (not found): {csv_path}")
            continue
        with open(csv_path, "rb") as f:
            result = ingest_csv(conn, f, gujo["id"], file_name=csv_path.name)
        print(result.summary())

    print()
    print("=== Counts per municipality ===")
    print(get_counts_per_municipality(conn).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
