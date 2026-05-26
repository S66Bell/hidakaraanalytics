"""Check import_logs for double imports."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db


conn = ensure_db()
print("=" * 70)
print("All import_logs")
print("=" * 70)
df = conn.execute(
    """
    SELECT il.id, m.name AS muni, il.file_name, il.file_type,
           il.rows_inserted, il.rows_skipped, il.imported_at
    FROM import_logs il LEFT JOIN municipalities m ON m.id = il.municipality_id
    ORDER BY il.id
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("=" * 70)
print("自治体ごとの ship 行数 vs ship 取込ログ rows_inserted の合計")
print("=" * 70)
df2 = conn.execute(
    """
    SELECT
        m.name,
        (SELECT COUNT(*) FROM shipments WHERE municipality_id = m.id) AS actual_rows,
        (SELECT COALESCE(SUM(rows_inserted), 0) FROM import_logs
         WHERE municipality_id = m.id AND file_type = 'shipment') AS log_inserted_sum
    FROM municipalities m
    ORDER BY m.id
    """
).fetchdf()
print(df2.to_string(index=False))

print()
print("=" * 70)
print("年別 本巣市 shipments の集計")
print("=" * 70)
df3 = conn.execute(
    """
    SELECT EXTRACT(year FROM payment_date) AS year,
           COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM shipments
    WHERE municipality_id = 1
    GROUP BY 1 ORDER BY 1
    """
).fetchdf()
print(df3.to_string(index=False))

print()
print("=" * 70)
print("月別 本巣市 shipments の集計（直近16ヶ月）")
print("=" * 70)
df4 = conn.execute(
    """
    SELECT date_trunc('month', payment_date) AS month,
           COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM shipments
    WHERE municipality_id = 1
    GROUP BY 1 ORDER BY 1 DESC LIMIT 24
    """
).fetchdf()
print(df4.to_string(index=False))

conn.close()
