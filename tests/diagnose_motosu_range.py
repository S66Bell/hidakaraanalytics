"""Check exact date range of motosu data."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db


conn = ensure_db()

print("=== 本巣市 shipments 日付範囲 ===")
df = conn.execute(
    """
    SELECT MIN(payment_date) AS min_date,
           MAX(payment_date) AS max_date,
           COUNT(*) AS total
    FROM shipments WHERE municipality_id = 1
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("=== 本巣市 donations 日付範囲 ===")
df = conn.execute(
    """
    SELECT MIN(payment_date) AS min_date,
           MAX(payment_date) AS max_date,
           COUNT(*) AS total
    FROM donations WHERE municipality_id = 1
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("=== 本巣市 2026年4月以降の日別件数 ===")
df = conn.execute(
    """
    SELECT payment_date, COUNT(*) AS ship_cnt, SUM(donation_amount) AS ship_revenue
    FROM shipments
    WHERE municipality_id = 1 AND payment_date >= '2026-04-01'
    GROUP BY 1 ORDER BY 1
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("=== 本巣市 donations 2026年4月以降の日別件数 ===")
df = conn.execute(
    """
    SELECT payment_date, COUNT(*) AS don_cnt, SUM(donation_amount) AS don_revenue
    FROM donations
    WHERE municipality_id = 1 AND payment_date >= '2026-04-01'
    GROUP BY 1 ORDER BY 1
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("=== もしかすると最初に取り込んだ別CSV（dates 5/1-5/24）が消えてるかも？ ===")
print("既存ログ:")
df = conn.execute(
    """
    SELECT id, file_name, file_type, rows_inserted, rows_skipped
    FROM import_logs WHERE municipality_id = 1 ORDER BY id
    """
).fetchdf()
print(df.to_string(index=False))

conn.close()
