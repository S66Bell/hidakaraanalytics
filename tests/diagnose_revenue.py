"""Diagnose: compare SUM(donation_amount) between shipments and donations tables
to detect potential double-counting in shipments (e.g., 定期便 multi-row issue)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db


def main() -> None:
    conn = ensure_db()
    print("=" * 70)
    print("自治体別 SHIPMENTS vs DONATIONS の合計比較（全期間）")
    print("=" * 70)
    df = conn.execute(
        """
        SELECT
            m.id, m.name,
            COALESCE(s.cnt, 0)        AS ship_cnt,
            COALESCE(s.sum_amount, 0) AS ship_sum,
            COALESCE(d.cnt, 0)        AS don_cnt,
            COALESCE(d.sum_amount, 0) AS don_sum,
            COALESCE(s.sum_amount, 0) - COALESCE(d.sum_amount, 0) AS diff
        FROM municipalities m
        LEFT JOIN (
            SELECT municipality_id,
                   COUNT(*) AS cnt,
                   SUM(donation_amount) AS sum_amount
            FROM shipments GROUP BY 1
        ) s ON s.municipality_id = m.id
        LEFT JOIN (
            SELECT municipality_id,
                   COUNT(*) AS cnt,
                   SUM(donation_amount) AS sum_amount
            FROM donations GROUP BY 1
        ) d ON d.municipality_id = m.id
        ORDER BY m.id
        """
    ).fetchdf()
    print(df.to_string(index=False))

    print()
    print("=" * 70)
    print("解説:")
    print(" - ship_sum と don_sum が大きく乖離していれば、")
    print("   shipments テーブルで 定期便など多重カウントが発生している可能性。")
    print(" - 「正しい revenue」は通常 donations テーブル側 (1 行 = 1 寄付)。")
    print("=" * 70)

    print()
    print("=" * 70)
    print("2025-05-24 から 2026-05-24 の期間（比較タブと同条件）")
    print("=" * 70)
    df2 = conn.execute(
        """
        SELECT
            m.name,
            COALESCE(s.cnt, 0)        AS ship_cnt,
            COALESCE(s.sum_amount, 0) AS ship_sum,
            COALESCE(d.cnt, 0)        AS don_cnt,
            COALESCE(d.sum_amount, 0) AS don_sum
        FROM municipalities m
        LEFT JOIN (
            SELECT municipality_id, COUNT(*) AS cnt, SUM(donation_amount) AS sum_amount
            FROM shipments
            WHERE payment_date BETWEEN '2025-05-24' AND '2026-05-24'
            GROUP BY 1
        ) s ON s.municipality_id = m.id
        LEFT JOIN (
            SELECT municipality_id, COUNT(*) AS cnt, SUM(donation_amount) AS sum_amount
            FROM donations
            WHERE payment_date BETWEEN '2025-05-24' AND '2026-05-24'
            GROUP BY 1
        ) d ON d.municipality_id = m.id
        ORDER BY m.id
        """
    ).fetchdf()
    print(df2.to_string(index=False))

    # 本巣市 の定期便っぽい商品をサンプル抽出
    print()
    print("=" * 70)
    print("本巣市: 同一日付・同一商品で複数行（定期便らしき）の例")
    print("=" * 70)
    df3 = conn.execute(
        """
        SELECT payment_date, product_code, product_name, donation_amount, COUNT(*) AS n
        FROM shipments
        WHERE municipality_id = 1
          AND product_name LIKE '%定期便%' OR product_name LIKE '%続便%' OR product_name LIKE '%回目%'
        GROUP BY payment_date, product_code, product_name, donation_amount
        HAVING n > 1
        ORDER BY n DESC
        LIMIT 10
        """
    ).fetchdf()
    print(df3.to_string(index=False))

    # 本巣市 寄附 CSV の同等期間
    print()
    print("=" * 70)
    print("本巣市 donations の総合計（参考）")
    print("=" * 70)
    df4 = conn.execute(
        """
        SELECT
            COUNT(*) AS cnt,
            SUM(donation_amount) AS sum_amount,
            MIN(payment_date) AS min_date,
            MAX(payment_date) AS max_date
        FROM donations
        WHERE municipality_id = 1
        """
    ).fetchdf()
    print(df4.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
