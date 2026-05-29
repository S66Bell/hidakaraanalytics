"""Trend tab: flexible date range + granularity switcher."""
from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import get_data_date_range, get_period_aggregates
from src.format_utils import format_int, format_pct, format_yen, format_yen_round


GRANULARITY_OPTIONS = {
    "日次": "day",
    "週次": "week",
    "月次": "month",
}

METRIC_OPTIONS = {
    "寄付金額": "revenue",
    "件数": "orders",
    "謝礼品価格": "total_cost",
    "返礼率": "expense_ratio",
    "平均単価": "avg_order_value",
}


_format_yen = format_yen
_format_pct = format_pct


def _build_chart(df: pd.DataFrame, metric_key: str, granularity: str) -> go.Figure:
    is_pct = metric_key == "expense_ratio"
    is_money = metric_key in {"revenue", "total_cost", "avg_order_value"}

    period_label = {"day": "日次", "week": "週次", "month": "月次"}[granularity]
    tick_fmt = {"day": "%Y/%m/%d", "week": "%Y/%m/%d", "month": "%Y/%m"}[granularity]

    if is_pct:
        y_vals = df[metric_key] * 100
        hover_y = "%{y:.2f}%"
        y_title = "返礼率（%）"
    elif is_money:
        y_vals = df[metric_key]
        hover_y = "¥%{y:,.0f}"
        y_title = "金額（円）"
    else:
        y_vals = df[metric_key]
        hover_y = "%{y:,.0f}"
        y_title = "件数"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=y_vals,
            mode="lines+markers",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=6),
            hovertemplate=f"%{{x|{tick_fmt}}}<br>{hover_y}<extra></extra>",
            name=period_label,
        )
    )
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title=None, tickformat=tick_fmt),
        yaxis=dict(title=y_title, tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def _build_breakdown_chart(df: pd.DataFrame, granularity: str) -> go.Figure:
    tick_fmt = {"day": "%Y/%m/%d", "week": "%Y/%m/%d", "month": "%Y/%m"}[granularity]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["period"],
            y=df["revenue"],
            name="寄付金額",
            marker_color="#1f77b4",
            hovertemplate=f"%{{x|{tick_fmt}}}<br>寄付金額: ¥%{{y:,.0f}}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["period"],
            y=df["total_cost"],
            name="謝礼品価格",
            marker_color="#d62728",
            hovertemplate=f"%{{x|{tick_fmt}}}<br>謝礼品価格: ¥%{{y:,.0f}}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None, tickformat=tick_fmt),
        yaxis=dict(title="金額（円）", tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("📈 日次/月次 推移")

    min_date, max_date = get_data_date_range(conn, municipality_ids)
    if max_date is None:
        st.info("まだ取込データがありません。")
        return

    scope = "全自治体" if not municipality_ids else f"選択中 {len(municipality_ids)} 自治体"
    st.caption(f"データ期間: {min_date} 〜 {max_date} ／ 範囲: {scope}")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        default_start = max(min_date, max_date - timedelta(days=365))
        date_range = st.date_input(
            "期間",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
            key="trend_range",
        )
    with col2:
        granularity_label = st.radio(
            "粒度",
            options=list(GRANULARITY_OPTIONS.keys()),
            horizontal=True,
            index=2,
            key="trend_granularity",
        )
        granularity = GRANULARITY_OPTIONS[granularity_label]
    with col3:
        metric_label = st.selectbox(
            "指標",
            options=list(METRIC_OPTIONS.keys()),
            index=0,
            key="trend_metric",
        )
        metric_key = METRIC_OPTIONS[metric_label]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    df = get_period_aggregates(conn, start, end, granularity, municipality_ids)
    if df.empty:
        st.info("指定期間内にデータがありません。")
        return

    total_revenue = int(df["revenue"].sum())
    total_orders = int(df["orders"].sum())
    total_cost = int(df["total_cost"].sum())
    expense_ratio = total_cost / total_revenue if total_revenue else 0.0

    cols = st.columns(4)
    cols[0].metric("期間合計 寄付金額", _format_yen(total_revenue))
    cols[1].metric("期間合計 件数", f"{total_orders:,} 件")
    cols[2].metric("期間合計 謝礼品価格", _format_yen(total_cost))
    cols[3].metric("期間 返礼率", _format_pct(expense_ratio))

    st.markdown(f"##### {metric_label} の推移")
    st.plotly_chart(_build_chart(df, metric_key, granularity), use_container_width=True)

    st.markdown("##### 寄付金額 vs 謝礼品価格")
    st.plotly_chart(_build_breakdown_chart(df, granularity), use_container_width=True)

    with st.expander("📋 集計データを表で確認"):
        display = df.copy()
        fmt = {"day": "%Y-%m-%d", "week": "%Y-%m-%d (W)", "month": "%Y-%m"}[granularity]
        display["period"] = display["period"].dt.strftime(fmt)
        display = display.rename(
            columns={
                "period": "期間",
                "orders": "件数",
                "revenue": "寄付金額",
                "total_cost": "謝礼品価格",
                "expense_ratio": "返礼率",
                "avg_order_value": "平均単価",
            }
        )
        display["寄付金額"] = display["寄付金額"].map(_format_yen)
        display["謝礼品価格"] = display["謝礼品価格"].map(_format_yen)
        display["平均単価"] = display["平均単価"].map(format_yen_round)
        display["返礼率"] = display["返礼率"].map(_format_pct)
        display["件数"] = display["件数"].map(format_int)
        st.dataframe(display.iloc[::-1], use_container_width=True, hide_index=True)

        csv_bytes = df.assign(period=df["period"].dt.strftime("%Y-%m-%d")).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード",
            data=csv_bytes,
            file_name=f"trend_{granularity}_{start}_{end}.csv",
            mime="text/csv",
        )
