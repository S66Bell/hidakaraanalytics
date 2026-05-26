"""Channel breakdown tab (楽天 / ANA etc.)."""
from __future__ import annotations

from datetime import timedelta

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    get_channel_breakdown,
    get_channel_category_cross,
    get_channel_monthly_trend,
    get_data_date_range,
)
from src.format_utils import format_count, format_pct, format_yen


def _channel_pie(df: pd.DataFrame) -> go.Figure:
    fig = px.pie(
        df,
        names="channel",
        values="revenue",
        hole=0.4,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}<br>寄付金額: ¥%{value:,}<br>シェア: %{percent}<extra></extra>",
    )
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def _channel_bar(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["channel"],
            y=df["revenue"],
            name="寄付金額",
            marker_color="#1f77b4",
            hovertemplate="%{x}<br>寄付金額: ¥%{y:,}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["channel"],
            y=df["total_cost"],
            name="謝礼品価格",
            marker_color="#d62728",
            hovertemplate="%{x}<br>謝礼品価格: ¥%{y:,}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None),
        yaxis=dict(title="金額（円）", tickformat=",.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _channel_monthly_stacked(df: pd.DataFrame, mode: str = "revenue") -> go.Figure:
    pivot = df.pivot_table(index="month", columns="channel", values=mode, aggfunc="sum", fill_value=0)
    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(
            go.Bar(
                x=pivot.index,
                y=pivot[col],
                name=str(col),
                hovertemplate=(
                    "%{x|%Y/%m}<br>" + str(col) + ": "
                    + ("¥%{y:,}" if mode in ("revenue", "total_cost") else "%{y:,}件")
                    + "<extra></extra>"
                ),
            )
        )
    title_map = {"revenue": "寄付金額（円）", "total_cost": "謝礼品価格（円）", "orders": "件数"}
    fig.update_layout(
        barmode="stack",
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(
            title=title_map.get(mode, ""),
            tickformat=",.0f",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _channel_share_chart(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(index="month", columns="channel", values="revenue", aggfunc="sum", fill_value=0)
    share = pivot.div(pivot.sum(axis=1), axis=0).fillna(0)
    fig = go.Figure()
    for col in share.columns:
        fig.add_trace(
            go.Scatter(
                x=share.index,
                y=share[col] * 100,
                mode="lines+markers",
                name=str(col),
                stackgroup="one",
                groupnorm="percent",
                hovertemplate="%{x|%Y/%m}<br>" + str(col) + ": %{y:.1f}%<extra></extra>",
            )
        )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(title="寄付金額シェア（%）", ticksuffix="%", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _channel_category_heatmap(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(index="category", columns="channel", values="revenue", aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="Blues",
            hovertemplate="チャネル: %{x}<br>カテゴリ: %{y}<br>寄付金額: ¥%{z:,}<extra></extra>",
            colorbar=dict(title="寄付金額（円）"),
        )
    )
    fig.update_layout(
        height=max(420, 22 * len(pivot)),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None),
        yaxis=dict(title=None, autorange="reversed"),
    )
    return fig


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🛒 チャネル別 分析")

    min_date, max_date = get_data_date_range(conn, municipality_ids)
    if max_date is None:
        st.info("まだ取込データがありません。")
        return

    scope = "全自治体" if not municipality_ids else f"選択中 {len(municipality_ids)} 自治体"
    st.caption(f"データ期間: {min_date} 〜 {max_date} ／ 範囲: {scope}")

    default_start = max(min_date, max_date - timedelta(days=365))
    date_range = st.date_input(
        "期間",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
        key="channel_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    # === Summary ===
    st.markdown("---")
    st.markdown("##### 📊 チャネル別 寄付金額構成")

    df = get_channel_breakdown(conn, start, end, municipality_ids)
    if df.empty:
        st.info("指定期間内にデータがありません。")
        return

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(_channel_pie(df), use_container_width=True)
    with chart_col2:
        st.plotly_chart(_channel_bar(df), use_container_width=True)

    with st.expander("📋 チャネル別データを表で確認"):
        d = df.copy()
        d = d.rename(
            columns={
                "channel": "チャネル",
                "orders": "件数",
                "revenue": "寄付金額",
                "total_cost": "謝礼品価格",
                "expense_ratio": "経費率",
                "share": "寄付金額シェア",
            }
        )
        d["寄付金額"] = d["寄付金額"].map(format_yen)
        d["謝礼品価格"] = d["謝礼品価格"].map(format_yen)
        d["件数"] = d["件数"].map(format_count)
        d["経費率"] = d["経費率"].map(format_pct)
        d["寄付金額シェア"] = d["寄付金額シェア"].map(format_pct)
        st.dataframe(d, use_container_width=True, hide_index=True)

    # === Monthly trend ===
    st.markdown("---")
    st.markdown("##### 📈 月次推移（チャネル別）")

    monthly = get_channel_monthly_trend(conn, start, end, municipality_ids)
    if monthly.empty:
        st.info("月次データがありません。")
    else:
        mode_label = st.radio(
            "表示モード",
            options=["寄付金額", "謝礼品価格", "件数", "シェア（%）"],
            horizontal=True,
            key="channel_monthly_mode",
        )
        mode_map = {"寄付金額": "revenue", "謝礼品価格": "total_cost", "件数": "orders"}
        if mode_label in mode_map:
            st.plotly_chart(_channel_monthly_stacked(monthly, mode_map[mode_label]), use_container_width=True)
        else:
            st.plotly_chart(_channel_share_chart(monthly), use_container_width=True)

    # === Cross analysis ===
    st.markdown("---")
    st.markdown("##### 🔀 チャネル × カテゴリ クロス分析")

    cross = get_channel_category_cross(conn, start, end, municipality_ids)
    if cross.empty:
        st.info("クロス分析用のデータがありません。")
    else:
        st.plotly_chart(_channel_category_heatmap(cross), use_container_width=True)
        with st.expander("📋 クロス集計表"):
            pivot = cross.pivot_table(index="category", columns="channel", values="revenue", aggfunc="sum", fill_value=0)
            pivot.loc["合計"] = pivot.sum()
            pivot["合計"] = pivot.sum(axis=1)
            pivot = pivot.map(lambda v: format_yen(int(v)))
            pivot.index.name = "カテゴリ"
            st.dataframe(pivot, use_container_width=True)
