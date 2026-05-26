"""One-off: add 飛騨市 municipality and ingest its CSVs."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import add_municipality, ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, ingest_csv


SHIPMENT_CSV = Path(r"C:\Users\info\Downloads\配送情報一覧(【分析用】配送情報)_202605261449.csv")
DONATION_CSV = Path(r"C:\Users\info\Downloads\寄附情報一覧(【分析用】寄附方法別)_202605261426.csv")


def main() -> None:
    conn = ensure_db()

    # Ensure 飛騨市 municipality exists
    existing = [m for m in list_municipalities(conn) if m["name"] == "飛騨市"]
    if existing:
        hida = existing[0]
        print(f"Found existing 飛騨市: {hida}")
    else:
        new_id = add_municipality(conn, "飛騨市", "hida")
        hida = next(m for m in list_municipalities(conn) if m["id"] == new_id)
        print(f"Created 飛騨市: {hida}")

    print()
    for csv_path in [SHIPMENT_CSV, DONATION_CSV]:
        with open(csv_path, "rb") as f:
            result = ingest_csv(conn, f, hida["id"], file_name=csv_path.name)
        print(result.summary())

    print()
    print("=== Counts per municipality ===")
    print(get_counts_per_municipality(conn).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
