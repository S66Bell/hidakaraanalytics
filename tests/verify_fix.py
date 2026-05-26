"""After fix: verify KPI changes."""
import sys
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db
from src.analytics import _kpi_for_range, get_municipality_kpis


conn = ensure_db()

print("=== _kpi_for_range 2025/5/24 - 2026/5/24（修正後） ===")
print()
for muni_id, name in [(1, "本巣市"), (2, "白川村"), (3, "飛騨市"), (4, "高山市"), (5, "郡上市")]:
    kpi = _kpi_for_range(conn, date(2025, 5, 24), date(2026, 5, 25), [muni_id])
    print(f"{name:6s} 寄付金額={kpi.revenue:>14,} 件数={kpi.orders:>8,} 謝礼品価格={kpi.total_cost:>14,} 経費率={kpi.expense_ratio*100:.1f}%")

print()
print("=== get_municipality_kpis 2025/5/24 - 2026/5/24（修正後） ===")
df = get_municipality_kpis(conn, date(2025, 5, 24), date(2026, 5, 24))
print(df.to_string(index=False))

print()
print("=== 参考: 本巣市 全期間 KPI ===")
kpi = _kpi_for_range(conn, date(2024, 1, 1), date(2026, 12, 31), [1])
print(f"  寄付金額={kpi.revenue:,} / 件数={kpi.orders:,} / 謝礼品価格={kpi.total_cost:,} / 経費率={kpi.expense_ratio*100:.1f}%")

conn.close()
