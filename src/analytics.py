"""Aggregation and analytics queries (multi-municipality).

集計ソースのルール（2026-05-26 確定）:
- **寄付金額 / 件数** は `donations` テーブル（寄附情報CSV）が一次ソース。
  1行=1寄附 なので、定期便のような 1寄附→N配送 の場合でも件数・金額が過大に
  ならない。
- **謝礼品価格** は `shipments` テーブルにしか存在しないのでこちらから集計。
- **返礼率** は 謝礼品価格(shipments) / 寄付金額(donations)。
- カテゴリ / 事業者 / 商品コード による分解は `shipments` を使う（これらの属性は
  shipments にしか無い）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb
import pandas as pd


GRANULARITY_TO_TRUNC = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}

# Resolves vendor name via vendor_aliases table (canonical name if aliased, else raw).
# Use as a column expression in any query joining/scanning shipments aliased as `s`.
VENDOR_RESOLVE = """
COALESCE(
    (SELECT canonical_name FROM vendor_aliases va
       WHERE va.alias_name = s.vendor
         AND (va.municipality_id IS NULL OR va.municipality_id = s.municipality_id)
       LIMIT 1),
    s.vendor
)
"""


@dataclass
class Kpi:
    revenue: int           # 寄付金額
    orders: int            # 件数
    total_cost: int        # 謝礼品価格

    @property
    def expense_ratio(self) -> float:
        return self.total_cost / self.revenue if self.revenue else 0.0

    @property
    def avg_order_value(self) -> float:
        return self.revenue / self.orders if self.orders else 0.0


@dataclass
class KpiComparison:
    label: str
    current: Kpi
    previous: Kpi | None

    def delta(self, attr: str) -> float | None:
        if self.previous is None:
            return None
        prev_value = getattr(self.previous, attr)
        curr_value = getattr(self.current, attr)
        if prev_value == 0:
            return None
        return (curr_value - prev_value) / prev_value


# ---------- Filter helpers ----------

def _filter_clause(
    start: date | None,
    end: date | None,
    municipality_ids: list[int] | None,
    *,
    use_lt_end: bool = False,
    table_alias: str = "",
) -> tuple[str, list]:
    """Build a WHERE clause and parameter list for date + municipality filters."""
    prefix = f"{table_alias}." if table_alias else ""
    clauses = []
    params: list = []
    if start is not None:
        clauses.append(f"{prefix}payment_date >= ?")
        params.append(start)
    if end is not None:
        op = "<" if use_lt_end else "<="
        clauses.append(f"{prefix}payment_date {op} ?")
        params.append(end)
    if municipality_ids:
        placeholders = ",".join(["?"] * len(municipality_ids))
        clauses.append(f"{prefix}municipality_id IN ({placeholders})")
        params.extend(municipality_ids)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def _municipality_only_clause(
    municipality_ids: list[int] | None,
    table_alias: str = "",
) -> tuple[str, list]:
    if not municipality_ids:
        return "", []
    prefix = f"{table_alias}." if table_alias else ""
    placeholders = ",".join(["?"] * len(municipality_ids))
    return f" WHERE {prefix}municipality_id IN ({placeholders})", list(municipality_ids)


# ---------- Basic KPI helpers ----------

def _kpi_for_range(
    conn: duckdb.DuckDBPyConnection,
    start: date,
    end_exclusive: date,
    municipality_ids: list[int] | None = None,
) -> Kpi:
    """寄付金額・件数 は donations、謝礼品価格 は shipments から集計する。"""
    where, params = _filter_clause(start, end_exclusive, municipality_ids, use_lt_end=True)
    # 寄付金額・件数 = donations
    don_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(donation_amount), 0) AS revenue,
               COUNT(*)                           AS orders
        FROM donations
        {where}
        """,
        params,
    ).fetchone()
    revenue = int(don_row[0]) if don_row and don_row[0] is not None else 0
    orders = int(don_row[1]) if don_row and don_row[1] is not None else 0

    # 謝礼品価格 = shipments
    ship_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(product_price), 0) AS total_cost
        FROM shipments
        {where}
        """,
        params,
    ).fetchone()
    total_cost = int(ship_row[0]) if ship_row and ship_row[0] is not None else 0

    return Kpi(revenue=revenue, orders=orders, total_cost=total_cost)


def get_data_date_range(
    conn: duckdb.DuckDBPyConnection,
    municipality_ids: list[int] | None = None,
) -> tuple[date | None, date | None]:
    """donations と shipments の両テーブルから合算で min/max を取る。"""
    where, params = _municipality_only_clause(municipality_ids)
    row = conn.execute(
        f"""
        SELECT MIN(d), MAX(d) FROM (
            SELECT payment_date AS d FROM donations {where}
            UNION ALL
            SELECT payment_date AS d FROM shipments {where}
        )
        """,
        params + params,
    ).fetchone()
    if row is None or row[0] is None:
        return None, None
    return row[0], row[1]


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def get_monthly_kpi_set(
    conn: duckdb.DuckDBPyConnection,
    reference_month: date | None = None,
    municipality_ids: list[int] | None = None,
) -> dict[str, KpiComparison]:
    if reference_month is None:
        _, max_date = get_data_date_range(conn, municipality_ids)
        reference_month = max_date if max_date is not None else date.today()

    y, m = reference_month.year, reference_month.month
    cur_start, cur_end = _month_bounds(y, m)
    current = _kpi_for_range(conn, cur_start, cur_end, municipality_ids)

    if m == 1:
        py, pm = y - 1, 12
    else:
        py, pm = y, m - 1
    prev_start, prev_end = _month_bounds(py, pm)
    prev_month = _kpi_for_range(conn, prev_start, prev_end, municipality_ids)

    yoy_start, yoy_end = _month_bounds(y - 1, m)
    yoy = _kpi_for_range(conn, yoy_start, yoy_end, municipality_ids)

    return {
        "current": KpiComparison(label=f"{y}年{m}月", current=current, previous=None),
        "vs_prev_month": KpiComparison(
            label=f"前月（{py}年{pm}月）", current=current, previous=prev_month
        ),
        "vs_prev_year": KpiComparison(
            label=f"前年同月（{y-1}年{m}月）", current=current, previous=yoy
        ),
    }


# ---------- Period aggregates ----------

def get_period_aggregates(
    conn: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    granularity: str = "month",
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    """period × (orders/revenue from donations) + (total_cost from shipments)."""
    trunc = GRANULARITY_TO_TRUNC.get(granularity, "month")
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).date()
    where, params = _filter_clause(start, end_exclusive, municipality_ids, use_lt_end=True)

    df = conn.execute(
        f"""
        WITH d AS (
            SELECT date_trunc('{trunc}', payment_date) AS period,
                   COUNT(*)                            AS orders,
                   COALESCE(SUM(donation_amount), 0)   AS revenue
            FROM donations
            {where}
            GROUP BY 1
        ),
        s AS (
            SELECT date_trunc('{trunc}', payment_date) AS period,
                   COALESCE(SUM(product_price), 0)     AS total_cost
            FROM shipments
            {where}
            GROUP BY 1
        )
        SELECT COALESCE(d.period, s.period) AS period,
               COALESCE(d.orders, 0)        AS orders,
               COALESCE(d.revenue, 0)       AS revenue,
               COALESCE(s.total_cost, 0)    AS total_cost
        FROM d FULL OUTER JOIN s USING (period)
        ORDER BY period
        """,
        params + params,
    ).fetchdf()
    if df.empty:
        return df
    df["period"] = pd.to_datetime(df["period"])
    df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
    df["avg_order_value"] = (df["revenue"] / df["orders"]).fillna(0.0)
    return df


def get_recent_monthly_trend(
    conn: duckdb.DuckDBPyConnection,
    months: int = 24,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    _, max_date = get_data_date_range(conn, municipality_ids)
    if max_date is None:
        return pd.DataFrame(
            columns=["period", "orders", "revenue", "total_cost", "expense_ratio", "avg_order_value"]
        )
    end = max_date
    start_year = max_date.year
    start_month = max_date.month - months + 1
    while start_month <= 0:
        start_year -= 1
        start_month += 12
    start = date(start_year, start_month, 1)
    return get_period_aggregates(conn, start, end, "month", municipality_ids)


# ---------- Rankings ----------

def get_category_ranking(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    where, params = _filter_clause(start, end, municipality_ids)
    df = conn.execute(
        f"""
        SELECT
            COALESCE(category, '(未分類)')         AS category,
            COUNT(*)                                AS orders,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COALESCE(SUM(product_price), 0)         AS total_cost
        FROM shipments
        {where}
        GROUP BY 1
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()
    if not df.empty:
        df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
        df["share"] = df["revenue"] / df["revenue"].sum()
    return df


def get_product_ranking(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    limit: int = 20,
    category: str | None = None,
    order_by: str = "revenue",
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    clauses = []
    params: list = []
    if start is not None:
        clauses.append("payment_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("payment_date <= ?")
        params.append(end)
    if category and category != "(全カテゴリ)":
        clauses.append("category = ?")
        params.append(category)
    if municipality_ids:
        placeholders = ",".join(["?"] * len(municipality_ids))
        clauses.append(f"municipality_id IN ({placeholders})")
        params.extend(municipality_ids)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order_col = {"revenue": "revenue", "orders": "orders", "total_cost": "total_cost"}.get(
        order_by, "revenue"
    )
    df = conn.execute(
        f"""
        SELECT
            COALESCE(product_code, '')             AS product_code,
            COALESCE(product_name, '(不明)')       AS product_name,
            COALESCE(category, '(未分類)')         AS category,
            COUNT(*)                                AS orders,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COALESCE(SUM(product_price), 0)         AS total_cost,
            AVG(donation_amount)                    AS avg_donation
        FROM shipments
        {where}
        GROUP BY 1, 2, 3
        ORDER BY {order_col} DESC
        LIMIT ?
        """,
        params + [int(limit)],
    ).fetchdf()
    if not df.empty:
        df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
    return df


def get_vendor_ranking(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    clauses = []
    params: list = []
    if start is not None:
        clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("s.payment_date <= ?")
        params.append(end)
    if municipality_ids:
        placeholders = ",".join(["?"] * len(municipality_ids))
        clauses.append(f"s.municipality_id IN ({placeholders})")
        params.extend(municipality_ids)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""

    # Resolve vendor via aliases (canonical name if mapped)
    df = conn.execute(
        f"""
        WITH resolved AS (
            SELECT
                COALESCE({VENDOR_RESOLVE}, '(不明)') AS vendor,
                s.donation_amount, s.product_price, s.product_code
            FROM shipments s
            {where}
        )
        SELECT
            vendor,
            COUNT(*)                                AS orders,
            COUNT(DISTINCT product_code)            AS product_count,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COALESCE(SUM(product_price), 0)         AS total_cost
        FROM resolved
        GROUP BY 1
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()

    if search and not df.empty:
        df = df[df["vendor"].str.contains(search, case=False, na=False)]

    if not df.empty:
        df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
        df["avg_order_value"] = (df["revenue"] / df["orders"]).fillna(0.0)
    return df


def list_vendors(
    conn: duckdb.DuckDBPyConnection,
    municipality_ids: list[int] | None = None,
) -> list[str]:
    where, params = _municipality_only_clause(municipality_ids, table_alias="s")
    if where:
        where += " AND s.vendor IS NOT NULL"
    else:
        where = " WHERE s.vendor IS NOT NULL"
    rows = conn.execute(
        f"""
        SELECT vendor, SUM(donation_amount) AS rev FROM (
            SELECT {VENDOR_RESOLVE} AS vendor, s.donation_amount
            FROM shipments s
            {where}
        ) t
        WHERE vendor IS NOT NULL
        GROUP BY vendor
        ORDER BY rev DESC
        """,
        params,
    ).fetchall()
    return [r[0] for r in rows]


def list_categories(
    conn: duckdb.DuckDBPyConnection,
    municipality_ids: list[int] | None = None,
) -> list[str]:
    where, params = _municipality_only_clause(municipality_ids)
    extra = " AND category IS NOT NULL" if where else " WHERE category IS NOT NULL"
    rows = conn.execute(
        f"""
        SELECT category, SUM(donation_amount) AS rev
        FROM shipments
        {where}{extra}
        GROUP BY category
        ORDER BY rev DESC
        """,
        params,
    ).fetchall()
    return [r[0] for r in rows]


def get_vendor_detail(
    conn: duckdb.DuckDBPyConnection,
    vendor: str,
    start: date | None = None,
    end: date | None = None,
    municipality_ids: list[int] | None = None,
) -> dict:
    """Vendor detail with alias resolution. `vendor` is the canonical name."""
    clauses = [f"({VENDOR_RESOLVE}) = ?"]
    params: list = [vendor]
    if start is not None:
        clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("s.payment_date <= ?")
        params.append(end)
    if municipality_ids:
        placeholders = ",".join(["?"] * len(municipality_ids))
        clauses.append(f"s.municipality_id IN ({placeholders})")
        params.extend(municipality_ids)
    where = "WHERE " + " AND ".join(clauses)

    kpi_row = conn.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(s.donation_amount), 0),
            COALESCE(SUM(s.product_price), 0),
            COUNT(DISTINCT s.product_code)
        FROM shipments s {where}
        """,
        params,
    ).fetchone()

    products = conn.execute(
        f"""
        SELECT
            COALESCE(s.product_code, '')           AS product_code,
            COALESCE(s.product_name, '(不明)')      AS product_name,
            COALESCE(s.category, '(未分類)')        AS category,
            COUNT(*)                                AS orders,
            COALESCE(SUM(s.donation_amount), 0)     AS revenue,
            COALESCE(SUM(s.product_price), 0)       AS total_cost
        FROM shipments s {where}
        GROUP BY 1, 2, 3
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()
    if not products.empty:
        products["expense_ratio"] = (products["total_cost"] / products["revenue"]).fillna(0.0)

    monthly = conn.execute(
        f"""
        SELECT
            date_trunc('month', s.payment_date)     AS month,
            COUNT(*)                                 AS orders,
            COALESCE(SUM(s.donation_amount), 0)      AS revenue,
            COALESCE(SUM(s.product_price), 0)        AS total_cost
        FROM shipments s {where}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    ).fetchdf()
    if not monthly.empty:
        monthly["month"] = pd.to_datetime(monthly["month"])

    channels = conn.execute(
        f"""
        SELECT
            COALESCE(s.channel, '(不明)')           AS channel,
            COUNT(*)                                 AS orders,
            COALESCE(SUM(s.donation_amount), 0)      AS revenue,
            COALESCE(SUM(s.product_price), 0)        AS total_cost
        FROM shipments s {where}
        GROUP BY 1
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()

    categories = conn.execute(
        f"""
        SELECT
            COALESCE(s.category, '(未分類)')        AS category,
            COUNT(*)                                 AS orders,
            COALESCE(SUM(s.donation_amount), 0)      AS revenue,
            COALESCE(SUM(s.product_price), 0)        AS total_cost
        FROM shipments s {where}
        GROUP BY 1
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()

    return {
        "vendor": vendor,
        "kpi": Kpi(revenue=int(kpi_row[1]), orders=int(kpi_row[0]), total_cost=int(kpi_row[2])),
        "product_count": int(kpi_row[3]),
        "products": products,
        "monthly": monthly,
        "channels": channels,
        "categories": categories,
        "start": start,
        "end": end,
    }


def get_channel_breakdown(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    where, params = _filter_clause(start, end, municipality_ids)
    df = conn.execute(
        f"""
        SELECT
            COALESCE(channel, '(不明)')            AS channel,
            COUNT(*)                                AS orders,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COALESCE(SUM(product_price), 0)         AS total_cost
        FROM shipments
        {where}
        GROUP BY 1
        ORDER BY revenue DESC
        """,
        params,
    ).fetchdf()
    if not df.empty:
        df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
        df["share"] = df["revenue"] / df["revenue"].sum()
    return df


def get_channel_monthly_trend(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    where, params = _filter_clause(start, end, municipality_ids)
    df = conn.execute(
        f"""
        SELECT
            date_trunc('month', payment_date)      AS month,
            COALESCE(channel, '(不明)')             AS channel,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COALESCE(SUM(product_price), 0)         AS total_cost,
            COUNT(*)                                AS orders
        FROM shipments
        {where}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        params,
    ).fetchdf()
    if not df.empty:
        df["month"] = pd.to_datetime(df["month"])
    return df


def get_channel_category_cross(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
    municipality_ids: list[int] | None = None,
) -> pd.DataFrame:
    where, params = _filter_clause(start, end, municipality_ids)
    df = conn.execute(
        f"""
        SELECT
            COALESCE(channel, '(不明)')            AS channel,
            COALESCE(category, '(未分類)')         AS category,
            COALESCE(SUM(donation_amount), 0)       AS revenue,
            COUNT(*)                                AS orders
        FROM shipments
        {where}
        GROUP BY 1, 2
        """,
        params,
    ).fetchdf()
    return df


# ---------- Municipality comparison helpers ----------

def get_municipality_kpis(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Per-municipality KPI summary.

    寄付金額・件数 は donations、謝礼品価格 は shipments、商品/事業者数も shipments。
    """
    don_clauses = []
    ship_clauses = []
    params: list = []
    if start is not None:
        don_clauses.append("d.payment_date >= ?")
        ship_clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        don_clauses.append("d.payment_date <= ?")
        ship_clauses.append("s.payment_date <= ?")
        params.append(end)
    don_where = (" WHERE " + " AND ".join(don_clauses)) if don_clauses else ""
    ship_where = (" WHERE " + " AND ".join(ship_clauses)) if ship_clauses else ""

    # params: 日付パラメータをそれぞれの CTE 用に2回渡す
    df = conn.execute(
        f"""
        WITH d AS (
            SELECT d.municipality_id,
                   COUNT(*) AS orders,
                   COALESCE(SUM(d.donation_amount), 0) AS revenue
            FROM donations d
            {don_where}
            GROUP BY d.municipality_id
        ),
        s AS (
            SELECT s.municipality_id,
                   COALESCE(SUM(s.product_price), 0) AS total_cost,
                   COUNT(DISTINCT s.product_code)    AS product_count,
                   COUNT(DISTINCT s.vendor)          AS vendor_count
            FROM shipments s
            {ship_where}
            GROUP BY s.municipality_id
        )
        SELECT
            m.id AS municipality_id,
            m.name AS municipality,
            COALESCE(d.orders, 0)        AS orders,
            COALESCE(d.revenue, 0)       AS revenue,
            COALESCE(s.total_cost, 0)    AS total_cost,
            COALESCE(s.product_count, 0) AS product_count,
            COALESCE(s.vendor_count, 0)  AS vendor_count
        FROM municipalities m
        LEFT JOIN d ON d.municipality_id = m.id
        LEFT JOIN s ON s.municipality_id = m.id
        ORDER BY revenue DESC
        """,
        params + params,
    ).fetchdf()
    if not df.empty:
        df["expense_ratio"] = (df["total_cost"] / df["revenue"]).fillna(0.0)
    return df


def get_municipality_monthly(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Per-municipality monthly revenue/orders (from donations) + total_cost (from shipments)."""
    don_clauses = []
    ship_clauses = []
    params: list = []
    if start is not None:
        don_clauses.append("d.payment_date >= ?")
        ship_clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        don_clauses.append("d.payment_date <= ?")
        ship_clauses.append("s.payment_date <= ?")
        params.append(end)
    don_where = (" WHERE " + " AND ".join(don_clauses)) if don_clauses else ""
    ship_where = (" WHERE " + " AND ".join(ship_clauses)) if ship_clauses else ""

    df = conn.execute(
        f"""
        WITH d AS (
            SELECT date_trunc('month', d.payment_date) AS month,
                   d.municipality_id,
                   COUNT(*) AS orders,
                   COALESCE(SUM(d.donation_amount), 0) AS revenue
            FROM donations d
            {don_where}
            GROUP BY 1, 2
        ),
        s AS (
            SELECT date_trunc('month', s.payment_date) AS month,
                   s.municipality_id,
                   COALESCE(SUM(s.product_price), 0) AS total_cost
            FROM shipments s
            {ship_where}
            GROUP BY 1, 2
        )
        SELECT
            COALESCE(d.month, s.month)              AS month,
            m.name                                   AS municipality,
            COALESCE(d.revenue, 0)                   AS revenue,
            COALESCE(s.total_cost, 0)                AS total_cost,
            COALESCE(d.orders, 0)                    AS orders
        FROM d FULL OUTER JOIN s USING (month, municipality_id)
        JOIN municipalities m ON m.id = COALESCE(d.municipality_id, s.municipality_id)
        ORDER BY month, municipality
        """,
        params + params,
    ).fetchdf()
    if not df.empty:
        df["month"] = pd.to_datetime(df["month"])
    return df


def get_municipality_channel_cross(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    clauses = []
    params: list = []
    if start is not None:
        clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("s.payment_date <= ?")
        params.append(end)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    df = conn.execute(
        f"""
        SELECT
            m.name                                  AS municipality,
            COALESCE(s.channel, '(不明)')          AS channel,
            COALESCE(SUM(s.donation_amount), 0)     AS revenue,
            COUNT(*)                                AS orders
        FROM shipments s
        JOIN municipalities m ON m.id = s.municipality_id
        {where}
        GROUP BY 1, 2
        """,
        params,
    ).fetchdf()
    return df


def get_municipality_category_cross(
    conn: duckdb.DuckDBPyConnection,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    clauses = []
    params: list = []
    if start is not None:
        clauses.append("s.payment_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("s.payment_date <= ?")
        params.append(end)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    df = conn.execute(
        f"""
        SELECT
            m.name                                  AS municipality,
            COALESCE(s.category, '(未分類)')       AS category,
            COALESCE(SUM(s.donation_amount), 0)     AS revenue,
            COUNT(*)                                AS orders
        FROM shipments s
        JOIN municipalities m ON m.id = s.municipality_id
        {where}
        GROUP BY 1, 2
        """,
        params,
    ).fetchdf()
    return df
