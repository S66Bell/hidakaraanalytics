"""Diagnose: motosu 2026/5/20-5/24 — compare shipments vs donations."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db


conn = ensure_db()

print("=" * 70)
print("本巣市 2026/05/20 - 2026/05/24 比較")
print("=" * 70)

print()
print("--- shipments テーブル ---")
df = conn.execute(
    """
    SELECT COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM shipments
    WHERE municipality_id = 1 AND payment_date BETWEEN '2026-05-20' AND '2026-05-24'
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("--- donations テーブル ---")
df = conn.execute(
    """
    SELECT COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM donations
    WHERE municipality_id = 1 AND payment_date BETWEEN '2026-05-20' AND '2026-05-24'
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("ユーザー手動集計: 154件 / ¥4,491,000")

print()
print("=" * 70)
print("月別比較（2026年5月のみ）")
print("=" * 70)
print()
print("--- shipments ---")
df = conn.execute(
    """
    SELECT payment_date, COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM shipments
    WHERE municipality_id = 1 AND payment_date >= '2026-05-01' AND payment_date <= '2026-05-31'
    GROUP BY 1 ORDER BY 1
    """
).fetchdf()
print(df.to_string(index=False))

print()
print("--- donations ---")
df = conn.execute(
    """
    SELECT payment_date, COUNT(*) AS cnt, SUM(donation_amount) AS revenue
    FROM donations
    WHERE municipality_id = 1 AND payment_date >= '2026-05-01' AND payment_date <= '2026-05-31'
    GROUP BY 1 ORDER BY 1
    """
).fetchdf()
print(df.to_string(index=False))

conn.close()
