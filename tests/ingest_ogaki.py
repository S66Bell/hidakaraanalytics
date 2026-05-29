"""One-off: add 大垣市 municipality and ingest its CSVs.

配送CSV は format_a（本巣市と同じ）、寄附CSV は standard 形式。
実行前に下の SHIPMENT_CSV / DONATION_CSV を実ファイルのパスに合わせること。

実行例:
    .\.venv\Scripts\python.exe tests\ingest_ogaki.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import add_municipality, ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, ingest_csv


# ↓↓↓ 実ファイルの場所に合わせて変更 ↓↓↓
SHIPMENT_CSV = Path(r"C:\Users\info\Downloads\Ogaki_haiso.csv")
DONATION_CSV = Path(r"C:\Users\info\Downloads\ogaki_kifu.csv")
# ↑↑↑ 実ファイルの場所に合わせて変更 ↑↑↑


def main() -> None:
    conn = ensure_db()

    existing = [m for m in list_municipalities(conn) if m["name"] == "大垣市"]
    if existing:
        ogaki = existing[0]
        print(f"Found existing 大垣市: {ogaki}")
    else:
        new_id = add_municipality(conn, "大垣市", "ogaki")
        ogaki = next(m for m in list_municipalities(conn) if m["id"] == new_id)
        print(f"Created 大垣市: {ogaki}")

    print()
    for csv_path in [SHIPMENT_CSV, DONATION_CSV]:
        if not csv_path.exists():
            print(f"WARNING: ファイルが見つかりません: {csv_path}")
            continue
        with open(csv_path, "rb") as f:
            result = ingest_csv(conn, f, ogaki["id"], file_name=csv_path.name)
        print(result.summary())

    print()
    print("=== Counts per municipality ===")
    print(get_counts_per_municipality(conn).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
