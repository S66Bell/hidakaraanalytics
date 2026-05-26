"""Product / Category ranking tab."""
from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    get_category_ranking,
    get_data_date_range,
    get_product_ranking,
    list_categories,
)
from src.format_utils import format_count, format_int, format_pct, format_yen, format_yen_round


ORDER_BY_OPTIONS = {
    "寄付金額": "revenue",
    "件数": "orders",
    "謝礼品価格": "total_cost",
}


def _category_pie(df: pd.DataFrame) -> go.Figure:
    fig = px.pie(
        df,
        names="category",
        values="revenue",
        title=None,
        hole=0.4,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}<br>寄付金額: ¥%{value:,}<br>シェア: %{percent}<extra></extra>",
    )
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def _category_bar(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["category"],
            y=df["revenue"],
            name="寄付金額",
            marker_color="#1f77b4",
            hovertemplate="%{x}<br>寄付金額: ¥%{y:,}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["category"],
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
        xaxis=dict(title=None, tickangle=-30),
        yaxis=dict(title="金額（円）", tickformat=",.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _product_bar(df: pd.DataFrame, metric: str) -> go.Figure:
    df_sorted = df.sort_values(metric, ascending=True).copy()
    is_money = metric in {"revenue", "total_cost"}
    color = {"revenue": "#1f77b4", "total_cost": "#d62728", "orders": "#ff7f0e"}[metric]
    label = {"revenue": "寄付金額", "total_cost": "謝礼品価格", "orders": "件数"}[metric]

    df_sorted["label"] = df_sorted["product_name"].str.slice(0, 40)
    df_sorted.loc[df_sorted["product_name"].str.len() > 40, "label"] += "…"

    fig = go.Figure(
        go.Bar(
            x=df_sorted[metric],
            y=df_sorted["label"],
            orientation="h",
            marker_color=color,
            text=df_sorted[metric].map(lambda v: f"¥{int(v):,}" if is_money else f"{int(v):,}"),
            textposition="outside",
            hovertemplate=("%{y}<br>" + label + ": " + ("¥%{x:,}" if is_money else "%{x:,}") + "<extra></extra>"),
        )
    )
    fig.update_layout(
        height=max(420, 28 * len(df_sorted)),
        margin=dict(l=10, r=120, t=10, b=10),
        xaxis=dict(title=label + ("（円）" if is_money else ""), tickformat=",.0f"),
        yaxis=dict(title=None, automargin=True),
    )
    return fig


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🏆 商品・カテゴリランキング")

    min_date, max_date = get_data_date_range(conn, municipality_ids)
    if max_date is None:
        st.info("まだ取込データがありません。")
        return

    scope = "全自治体" if not municipality_ids else f"選択中 {len(municipality_ids)} 自治体"
    st.caption(f"データ期間: {min_date} 〜 {max_date} ／ 範囲: {scope}")

    col1, col2 = st.columns([2, 1])
    with col1:
        default_start = max(min_date, max_date - timedelta(days=365))
        date_range = st.date_input(
            "期間",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
            key="ranking_range",
        )
    with col2:
        limit = st.number_input("商品TOP 件数", min_value=5, max_value=100, value=20, step=5, key="ranking_limit")

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    # === Category section ===
    st.markdown("---")
    st.markdown("##### 📦 カテゴリ別 寄付金額構成")

    cat_df = get_category_ranking(conn, start, end, municipality_ids)
    if cat_df.empty:
        st.info("指定期間内にデータがありません。")
        return

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(_category_pie(cat_df), use_container_width=True)
    with chart_col2:
        st.plotly_chart(_category_bar(cat_df), use_container_width=True)

    with st.expander("📋 カテゴリ別データを表で確認"):
        d = cat_df.copy()
        d = d.rename(
            columns={
                "category": "カテゴリ",
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

    # === Product section ===
    st.markdown("---")
    st.markdown(f"##### 🏆 商品別 TOP{int(limit)}")

    pc1, pc2 = st.columns([1, 1])
    with pc1:
        categories = ["(全カテゴリ)"] + list_categories(conn, municipality_ids)
        selected_cat = st.selectbox("カテゴリ絞り込み", categories, key="ranking_cat")
    with pc2:
        order_label = st.radio(
            "ランキング基準",
            options=list(ORDER_BY_OPTIONS.keys()),
            horizontal=True,
            key="ranking_order",
        )
        order_by = ORDER_BY_OPTIONS[order_label]

    prod_df = get_product_ranking(
        conn,
        start=start,
        end=end,
        limit=int(limit),
        category=selected_cat,
        order_by=order_by,
        municipality_ids=municipality_ids,
    )
    if prod_df.empty:
        st.info("該当する商品がありません。")
        return

    st.plotly_chart(_product_bar(prod_df, order_by), use_container_width=True)

    with st.expander("📋 商品別データを表で確認"):
        d = prod_df.copy()
        d = d[["product_code", "product_name", "category", "orders", "revenue", "total_cost", "expense_ratio", "avg_donation"]]
        d = d.rename(
            columns={
                "product_code": "商品コード",
                "product_name": "商品名",
                "category": "カテゴリ",
                "orders": "件数",
                "revenue": "寄付金額",
                "total_cost": "謝礼品価格",
                "expense_ratio": "経費率",
                "avg_donation": "平均寄附額",
            }
        )
        d["寄付金額"] = d["寄付金額"].map(format_yen)
        d["謝礼品価格"] = d["謝礼品価格"].map(format_yen)
        d["件数"] = d["件数"].map(format_count)
        d["経費率"] = d["経費率"].map(format_pct)
        d["平均寄附額"] = d["平均寄附額"].map(format_yen_round)
        st.dataframe(d, use_container_width=True, hide_index=True)
