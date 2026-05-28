"""Municipality comparison tab: side-by-side (A vs B) + multi-municipality views."""
from __future__ import annotations

from datetime import timedelta

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    get_category_ranking,
    get_channel_breakdown,
    get_data_date_range,
    get_municipality_category_cross,
    get_municipality_channel_cross,
    get_municipality_kpis,
    get_municipality_monthly,
    get_period_aggregates,
    get_vendor_ranking,
)
from src.db import list_municipalities
from src.format_utils import format_count, format_int, format_pct, format_yen


# ===========================================================
# Side-by-side helpers (A vs B)
# ===========================================================

def _delta_pct(a: float, b: float) -> str:
    """Returns 'A is X% higher/lower than B'."""
    if b == 0:
        return "—"
    diff = a - b
    rate = diff / b * 100
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate:.1f}%"


def _kpi_delta_str(a, b, *, is_pct: bool = False) -> str:
    if b is None or b == 0:
        return ""
    diff = a - b
    rate = diff / b * 100
    sign = "+" if rate >= 0 else ""
    if is_pct:
        return f"{diff*100:+.1f}pt (vs B {sign}{rate:.1f}%)"
    return f"vs B {sign}{rate:.1f}%"


def _kpi_diff_only(a, b, *, is_pct: bool = False) -> str:
    if b is None or b == 0:
        return None
    rate = (a - b) / b * 100
    if is_pct:
        diff_pt = (a - b) * 100
        return f"{diff_pt:+.1f}pt"
    return f"{rate:+.1f}%"


def _side_by_side_kpis(
    a_name: str, a_kpi: dict, b_name: str, b_kpi: dict
) -> None:
    """Render side-by-side KPI metrics: 2 columns × 4 rows."""
    st.markdown(f"##### 📊 KPI: **{a_name}** ⇔ **{b_name}**")
    col_a, col_b = st.columns(2)

    a_rev, b_rev = int(a_kpi["revenue"]), int(b_kpi["revenue"])
    a_ord, b_ord = int(a_kpi["orders"]), int(b_kpi["orders"])
    a_cost, b_cost = int(a_kpi["total_cost"]), int(b_kpi["total_cost"])
    a_exp = a_cost / a_rev if a_rev else 0
    b_exp = b_cost / b_rev if b_rev else 0

    with col_a:
        st.markdown(f"### 🏛️ {a_name}")
        c1, c2 = st.columns(2)
        c1.metric("寄付金額", format_yen(a_rev), delta=_kpi_diff_only(a_rev, b_rev))
        c2.metric("件数", format_count(a_ord), delta=_kpi_diff_only(a_ord, b_ord))
        c3, c4 = st.columns(2)
        c3.metric("謝礼品価格", format_yen(a_cost), delta=_kpi_diff_only(a_cost, b_cost))
        c4.metric("返礼率", format_pct(a_exp), delta=_kpi_diff_only(a_exp, b_exp, is_pct=True))

    with col_b:
        st.markdown(f"### 🏛️ {b_name}")
        c1, c2 = st.columns(2)
        c1.metric("寄付金額", format_yen(b_rev))
        c2.metric("件数", format_count(b_ord))
        c3, c4 = st.columns(2)
        c3.metric("謝礼品価格", format_yen(b_cost))
        c4.metric("返礼率", format_pct(b_exp))


def _muni_kpi_dict(conn, muni_id, start, end) -> dict:
    """Single-municipality KPI dict.

    寄付金額・件数 は donations、謝礼品価格 は shipments から集計（定期便などの
    多重カウントを避けるため、KPI は寄附情報を一次ソースにする）。
    """
    try:
        don_row = conn.execute(
            """
            SELECT COALESCE(SUM(donation_amount), 0), COUNT(*)
            FROM donations
            WHERE municipality_id = ? AND payment_date BETWEEN ? AND ?
            """,
            [muni_id, start, end],
        ).fetchone()
    except Exception:
        don_row = None
    try:
        ship_row = conn.execute(
            """
            SELECT COALESCE(SUM(product_price), 0)
            FROM shipments
            WHERE municipality_id = ? AND payment_date BETWEEN ? AND ?
            """,
            [muni_id, start, end],
        ).fetchone()
    except Exception:
        ship_row = None
    return {
        "revenue": int(don_row[0]) if don_row and don_row[0] is not None else 0,
        "orders": int(don_row[1]) if don_row and don_row[1] is not None else 0,
        "total_cost": int(ship_row[0]) if ship_row and ship_row[0] is not None else 0,
    }


def _category_pie(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        return go.Figure().update_layout(title=f"{title}: データなし", height=320)
    top = df.head(8).copy()
    if len(df) > 8:
        other_rev = df.iloc[8:]["revenue"].sum()
        other_row = pd.DataFrame([{"category": "その他", "revenue": other_rev}])
        top = pd.concat([top[["category", "revenue"]], other_row], ignore_index=True)
    fig = px.pie(top, names="category", values="revenue", hole=0.4, title=title)
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}<br>¥%{value:,}<br>%{percent}<extra></extra>",
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


def _channel_pie(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        return go.Figure().update_layout(title=f"{title}: データなし", height=320)
    fig = px.pie(df, names="channel", values="revenue", hole=0.4, title=title)
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}<br>¥%{value:,}<br>%{percent}<extra></extra>",
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


def _vendor_top_table(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.head(top_n).copy()
    d["寄付金額"] = d["revenue"].map(format_yen)
    d["件数"] = d["orders"].map(format_int)
    return d[["vendor", "件数", "寄付金額"]].rename(columns={"vendor": "事業者"})


def _monthly_overlay_chart(conn, a_id: int, a_name: str, b_id: int, b_name: str, start, end) -> go.Figure:
    a_df = get_period_aggregates(conn, start, end, "month", [a_id])
    b_df = get_period_aggregates(conn, start, end, "month", [b_id])
    fig = go.Figure()
    if not a_df.empty:
        fig.add_trace(
            go.Scatter(
                x=a_df["period"],
                y=a_df["revenue"],
                mode="lines+markers",
                name=a_name,
                line=dict(color="#1f77b4", width=2),
                hovertemplate="%{x|%Y/%m}<br>" + a_name + ": ¥%{y:,}<extra></extra>",
            )
        )
    if not b_df.empty:
        fig.add_trace(
            go.Scatter(
                x=b_df["period"],
                y=b_df["revenue"],
                mode="lines+markers",
                name=b_name,
                line=dict(color="#d62728", width=2),
                hovertemplate="%{x|%Y/%m}<br>" + b_name + ": ¥%{y:,}<extra></extra>",
            )
        )
    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(title="寄付金額（円）", tickformat=",.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def _side_by_side_section(conn, munis: list[dict], start, end) -> None:
    """Render the A vs B side-by-side comparison section."""
    st.markdown("##### 🆚 2自治体 サイドバイサイド比較")

    name_by_id = {m["id"]: m["name"] for m in munis}
    ids = [m["id"] for m in munis]

    sel_col1, sel_col2 = st.columns(2)
    with sel_col1:
        a_id = st.selectbox(
            "自治体 A",
            options=ids,
            index=0,
            format_func=lambda i: name_by_id.get(i, str(i)),
            key="cmp_a",
        )
    with sel_col2:
        default_b = ids[1] if len(ids) > 1 else ids[0]
        b_id = st.selectbox(
            "自治体 B",
            options=ids,
            index=ids.index(default_b),
            format_func=lambda i: name_by_id.get(i, str(i)),
            key="cmp_b",
        )

    if a_id == b_id:
        st.warning("AとBに異なる自治体を選択してください。")
        return

    a_name = name_by_id[a_id]
    b_name = name_by_id[b_id]

    # --- KPI side-by-side ---
    a_kpi = _muni_kpi_dict(conn, a_id, start, end)
    b_kpi = _muni_kpi_dict(conn, b_id, start, end)
    _side_by_side_kpis(a_name, a_kpi, b_name, b_kpi)

    # --- Monthly overlay ---
    st.markdown("---")
    st.markdown(f"##### 📈 月次推移オーバーレイ（{a_name} vs {b_name}）")
    st.plotly_chart(
        _monthly_overlay_chart(conn, a_id, a_name, b_id, b_name, start, end),
        use_container_width=True,
        key=f"cmp_monthly_{a_id}_{b_id}",
    )

    # --- Category composition side-by-side ---
    st.markdown("---")
    st.markdown("##### 📦 カテゴリ構成（並列）")
    a_cat = get_category_ranking(conn, start, end, [a_id])
    b_cat = get_category_ranking(conn, start, end, [b_id])
    cc1, cc2 = st.columns(2)
    with cc1:
        st.plotly_chart(_category_pie(a_cat, a_name), use_container_width=True,
                        key=f"cmp_cat_a_{a_id}")
    with cc2:
        st.plotly_chart(_category_pie(b_cat, b_name), use_container_width=True,
                        key=f"cmp_cat_b_{b_id}")

    # --- Channel composition side-by-side ---
    st.markdown("---")
    st.markdown("##### 🛒 チャネル構成（並列）")
    a_ch = get_channel_breakdown(conn, start, end, [a_id])
    b_ch = get_channel_breakdown(conn, start, end, [b_id])
    cc1, cc2 = st.columns(2)
    with cc1:
        st.plotly_chart(_channel_pie(a_ch, a_name), use_container_width=True,
                        key=f"cmp_ch_a_{a_id}")
    with cc2:
        st.plotly_chart(_channel_pie(b_ch, b_name), use_container_width=True,
                        key=f"cmp_ch_b_{b_id}")

    # --- Top vendors side-by-side ---
    st.markdown("---")
    st.markdown("##### 🏭 TOP10 事業者（並列）")
    a_v = get_vendor_ranking(conn, start, end, municipality_ids=[a_id])
    b_v = get_vendor_ranking(conn, start, end, municipality_ids=[b_id])
    vv1, vv2 = st.columns(2)
    with vv1:
        st.markdown(f"**{a_name}**")
        d = _vendor_top_table(a_v)
        if d.empty:
            st.write("データなし")
        else:
            st.dataframe(d, use_container_width=True, hide_index=True)
    with vv2:
        st.markdown(f"**{b_name}**")
        d = _vendor_top_table(b_v)
        if d.empty:
            st.write("データなし")
        else:
            st.dataframe(d, use_container_width=True, hide_index=True)


# ===========================================================
# All-municipality charts (used when 3+ municipalities exist)
# ===========================================================

def _ranking_chart(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values("revenue", ascending=True).copy()
    fig = go.Figure(
        go.Bar(
            y=d["municipality"],
            x=d["revenue"],
            orientation="h",
            marker_color="#1f77b4",
            text=d["revenue"].map(lambda v: format_yen(int(v))),
            textposition="outside",
            hovertemplate="%{y}<br>寄付金額: ¥%{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(360, 40 * len(d)),
        margin=dict(l=10, r=120, t=10, b=10),
        xaxis=dict(title="寄付金額（円）", tickformat=",.0f"),
        yaxis=dict(title=None, automargin=True),
    )
    return fig


def _channel_cross_heatmap(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(
        index="municipality", columns="channel", values="revenue", aggfunc="sum", fill_value=0
    )
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="Blues",
            hovertemplate="自治体: %{y}<br>チャネル: %{x}<br>寄付金額: ¥%{z:,}<extra></extra>",
            colorbar=dict(title="寄付金額"),
        )
    )
    fig.update_layout(
        height=max(280, 40 * len(pivot)),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None),
        yaxis=dict(title=None, autorange="reversed"),
    )
    return fig


def _category_share_stacked(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(
        index="municipality", columns="category", values="revenue", aggfunc="sum", fill_value=0
    )
    totals = pivot.sum(axis=1)
    share = pivot.div(totals.replace(0, pd.NA), axis=0).fillna(0) * 100

    top_cats = pivot.sum(axis=0).sort_values(ascending=False).head(10).index
    other_share = 100 - share[top_cats].sum(axis=1)
    share_top = share[top_cats].copy()
    if (other_share > 0).any():
        share_top["その他"] = other_share

    fig = go.Figure()
    for cat in share_top.columns:
        fig.add_trace(
            go.Bar(
                y=share_top.index,
                x=share_top[cat],
                name=str(cat),
                orientation="h",
                hovertemplate="%{y}<br>" + str(cat) + ": %{x:.1f}%<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        height=max(360, 40 * len(share_top)),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title="カテゴリ構成比（%）", ticksuffix="%", range=[0, 100]),
        yaxis=dict(title=None, automargin=True, autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _all_munis_section(conn, start, end) -> None:
    st.markdown("##### 📊 全自治体 KPI 一覧")
    kpis = get_municipality_kpis(conn, start, end)
    if kpis.empty:
        st.info("KPIデータがありません。")
        return

    display = kpis.copy().rename(
        columns={
            "municipality": "自治体",
            "orders": "件数",
            "revenue": "寄付金額",
            "total_cost": "謝礼品価格",
            "expense_ratio": "返礼率",
            "product_count": "取扱商品数",
            "vendor_count": "取扱事業者数",
        }
    )
    display["件数"] = display["件数"].map(format_int)
    display["寄付金額"] = display["寄付金額"].map(format_yen)
    display["謝礼品価格"] = display["謝礼品価格"].map(format_yen)
    display["返礼率"] = display["返礼率"].map(format_pct)
    display["取扱商品数"] = display["取扱商品数"].map(format_int)
    display["取扱事業者数"] = display["取扱事業者数"].map(format_int)
    st.dataframe(
        display[["自治体", "件数", "寄付金額", "謝礼品価格", "返礼率", "取扱商品数", "取扱事業者数"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.markdown("##### 🏆 自治体別 寄付金額ランキング")
    st.plotly_chart(_ranking_chart(kpis), use_container_width=True, key="all_ranking")

    st.markdown("---")
    st.markdown("##### 📈 月次推移（全自治体）")
    monthly = get_municipality_monthly(conn, start, end)
    if monthly.empty or monthly["month"].nunique() < 2:
        st.info("月次推移を表示するには、2か月以上のデータが必要です。")
    else:
        fig = go.Figure()
        for muni, sub in monthly.groupby("municipality"):
            sub = sub.sort_values("month")
            fig.add_trace(
                go.Scatter(
                    x=sub["month"],
                    y=sub["revenue"],
                    mode="lines+markers",
                    name=str(muni),
                    hovertemplate="%{x|%Y/%m}<br>" + str(muni) + ": ¥%{y:,}<extra></extra>",
                )
            )
        fig.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(title=None, tickformat="%Y/%m"),
            yaxis=dict(title="寄付金額（円）", tickformat=",.0f"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="all_monthly")

    st.markdown("---")
    st.markdown("##### 🛒 自治体 × チャネル ヒートマップ")
    ch_cross = get_municipality_channel_cross(conn, start, end)
    if ch_cross.empty:
        st.info("チャネルクロスデータがありません。")
    else:
        st.plotly_chart(_channel_cross_heatmap(ch_cross), use_container_width=True,
                        key="all_channel_heatmap")

    st.markdown("---")
    st.markdown("##### 📦 自治体別 カテゴリ構成（100%積み上げ）")
    cat_cross = get_municipality_category_cross(conn, start, end)
    if cat_cross.empty:
        st.info("カテゴリデータがありません。")
    else:
        st.plotly_chart(_category_share_stacked(cat_cross), use_container_width=True,
                        key="all_category_stack")


# ===========================================================
# Entry
# ===========================================================

def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🏛️ 自治体比較")

    munis = list_municipalities(conn, active_only=True)
    if len(munis) < 2:
        st.info(
            "比較するには自治体が2つ以上必要です。「⚙️ 設定」タブから自治体を追加してください。"
        )
        return

    min_date, max_date = get_data_date_range(conn)
    if max_date is None:
        st.info("まだ取込データがありません。")
        return

    st.caption(f"データ期間: {min_date} 〜 {max_date}")
    default_start = max(min_date, max_date - timedelta(days=365))
    date_range = st.date_input(
        "比較期間",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
        key="comparison_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    sub_tabs = st.tabs(["🆚 2自治体 サイドバイサイド", "📊 全自治体 一括比較"])
    with sub_tabs[0]:
        st.markdown("---")
        _side_by_side_section(conn, munis, start, end)
    with sub_tabs[1]:
        st.markdown("---")
        _all_munis_section(conn, start, end)
