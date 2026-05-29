"""Vendor analysis tab with search."""
from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    get_data_date_range,
    get_vendor_detail,
    get_vendor_ranking,
    shift_one_year,
)
from src.format_utils import format_count, format_int, format_pct, format_yen, format_yen_round, format_yoy
from src.reports import build_vendor_pdf


def _vendor_ranking_chart(df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    d = df.head(top_n).sort_values("revenue", ascending=True).copy()
    d["label"] = d["vendor"].str.slice(0, 30)
    d.loc[d["vendor"].str.len() > 30, "label"] += "…"
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=d["label"],
            x=d["revenue"],
            name="寄付金額",
            orientation="h",
            marker_color="#1f77b4",
            hovertemplate="%{y}<br>寄付金額: ¥%{x:,}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=d["label"],
            x=d["total_cost"],
            name="謝礼品価格",
            orientation="h",
            marker_color="#d62728",
            hovertemplate="%{y}<br>謝礼品価格: ¥%{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        height=max(420, 28 * len(d)),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title="金額（円）", tickformat=",.0f"),
        yaxis=dict(title=None, automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _vendor_monthly_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["month"],
            y=df["revenue"],
            name="寄付金額",
            marker_color="#1f77b4",
            hovertemplate="%{x|%Y/%m}<br>寄付金額: ¥%{y:,}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["month"],
            y=df["total_cost"],
            name="謝礼品価格",
            marker_color="#d62728",
            hovertemplate="%{x|%Y/%m}<br>謝礼品価格: ¥%{y:,}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(title="金額（円）", tickformat=",.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _vendor_ranking_section(conn, start: date, end: date, municipality_ids: list[int] | None) -> None:
    st.markdown("##### 🏭 事業者別ランキング")

    search = st.text_input("🔍 事業者名で絞り込み（部分一致）", "", key="vendor_search")
    df = get_vendor_ranking(conn, start, end, search=search if search else None, municipality_ids=municipality_ids)

    if df.empty:
        st.info("該当する事業者がありません。")
        return

    # 前年比（選択期間を1年前にシフトして比較、検索フィルタは掛けず名前で突合）
    prev_df = get_vendor_ranking(
        conn, shift_one_year(start), shift_one_year(end), municipality_ids=municipality_ids
    )
    prev_rev = dict(zip(prev_df["vendor"], prev_df["revenue"])) if not prev_df.empty else {}
    df = df.copy()
    df["revenue_prev"] = df["vendor"].map(prev_rev)
    df["yoy"] = (df["revenue"] - df["revenue_prev"]) / df["revenue_prev"]

    total_rev = int(df["revenue"].sum())
    total_cost = int(df["total_cost"].sum())
    total_expense_ratio = total_cost / total_rev if total_rev else 0

    cols = st.columns(4)
    cols[0].metric("該当事業者数", f"{len(df):,}")
    cols[1].metric("合計 寄付金額", format_yen(total_rev))
    cols[2].metric("合計 謝礼品価格", format_yen(total_cost))
    cols[3].metric("平均 返礼率", format_pct(total_expense_ratio))

    sort_label = st.radio(
        "並び順",
        options=["寄付金額", "謝礼品価格", "返礼率", "件数"],
        horizontal=True,
        index=0,
        key="vendor_sort",
    )
    sort_map = {
        "寄付金額": ("revenue", False),
        "謝礼品価格": ("total_cost", False),
        "返礼率": ("expense_ratio", False),
        "件数": ("orders", False),
    }
    sort_col, asc = sort_map[sort_label]
    sorted_df = df.sort_values(sort_col, ascending=asc)

    st.plotly_chart(_vendor_ranking_chart(sorted_df), use_container_width=True)

    with st.expander("📋 事業者別データを表で確認"):
        d = sorted_df.copy()
        d["寄付金額"] = d["revenue"].map(format_yen)
        d["前年比"] = d["yoy"].map(format_yoy)
        d["謝礼品価格"] = d["total_cost"].map(format_yen)
        d["件数"] = d["orders"].map(format_count)
        d["取扱商品数"] = d["product_count"].map(format_int)
        d["返礼率"] = d["expense_ratio"].map(format_pct)
        d["平均単価"] = d["avg_order_value"].map(format_yen_round)
        d = d.rename(columns={"vendor": "事業者"})
        st.dataframe(
            d[["事業者", "件数", "取扱商品数", "寄付金額", "前年比", "謝礼品価格", "返礼率", "平均単価"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"前年比 = {start.year-1}/{start.month:02d}〜{end.year-1}/{end.month:02d} の寄付金額との増減率"
        )


def _vendor_detail_section(conn, start: date, end: date, municipality_ids: list[int] | None) -> None:
    st.markdown("##### 🔎 事業者を選んで詳細を表示")

    df_all = get_vendor_ranking(conn, start, end, municipality_ids=municipality_ids)
    if df_all.empty:
        st.info("選択可能な事業者がありません。")
        return

    vendors = df_all["vendor"].tolist()
    selected = st.selectbox("事業者を選択", vendors, key="vendor_detail_select")
    if not selected:
        return

    detail = get_vendor_detail(conn, selected, start, end, municipality_ids=municipality_ids)
    prev_detail = get_vendor_detail(
        conn, selected, shift_one_year(start), shift_one_year(end), municipality_ids=municipality_ids
    )
    prev_ch = prev_detail["channels"]
    prev_ch_rev = dict(zip(prev_ch["channel"], prev_ch["revenue"])) if not prev_ch.empty else {}
    kpi = detail["kpi"]
    cols = st.columns(5)
    cols[0].metric("寄付金額", format_yen(kpi.revenue))
    cols[1].metric("件数", format_count(kpi.orders))
    cols[2].metric("謝礼品価格", format_yen(kpi.total_cost))
    cols[3].metric("返礼率", format_pct(kpi.expense_ratio))
    cols[4].metric("取扱商品数", f"{detail['product_count']:,}")

    if not detail["monthly"].empty and len(detail["monthly"]) > 1:
        st.markdown("**月次推移**")
        st.plotly_chart(_vendor_monthly_chart(detail["monthly"]), use_container_width=True)

    detail_col1, detail_col2 = st.columns(2)
    with detail_col1:
        st.markdown("**カテゴリ内訳**")
        c = detail["categories"].copy()
        if not c.empty:
            c["寄付金額"] = c["revenue"].map(format_yen)
            c["謝礼品価格"] = c["total_cost"].map(format_yen)
            c["件数"] = c["orders"].map(format_count)
            st.dataframe(
                c[["category", "件数", "寄付金額", "謝礼品価格"]].rename(columns={"category": "カテゴリ"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("データなし")
    with detail_col2:
        st.markdown("**チャネル内訳**")
        c = detail["channels"].copy()
        if not c.empty:
            c["revenue_prev"] = c["channel"].map(prev_ch_rev)
            c["前年比"] = ((c["revenue"] - c["revenue_prev"]) / c["revenue_prev"]).map(format_yoy)
            c["寄付金額"] = c["revenue"].map(format_yen)
            c["謝礼品価格"] = c["total_cost"].map(format_yen)
            c["件数"] = c["orders"].map(format_count)
            st.dataframe(
                c[["channel", "件数", "寄付金額", "前年比", "謝礼品価格"]].rename(columns={"channel": "チャネル"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("データなし")

    st.markdown("**商品別実績**")
    p = detail["products"].copy()
    if not p.empty:
        p = p.rename(
            columns={
                "product_code": "商品コード",
                "product_name": "商品名",
                "category": "カテゴリ",
                "orders": "件数",
                "revenue": "寄付金額",
                "total_cost": "謝礼品価格",
                "expense_ratio": "返礼率",
            }
        )
        p["寄付金額"] = p["寄付金額"].map(format_yen)
        p["謝礼品価格"] = p["謝礼品価格"].map(format_yen)
        p["件数"] = p["件数"].map(format_count)
        p["返礼率"] = p["返礼率"].map(format_pct)
        st.dataframe(p, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown(f"##### 📄 「{selected}」のPDFレポートをダウンロード")
    pdfcol1, pdfcol2 = st.columns([1, 3])
    with pdfcol1:
        if st.button("📄 PDF生成", key=f"vendor_pdf_gen_{selected}"):
            with st.spinner("PDF生成中..."):
                pdf_bytes = build_vendor_pdf(conn, selected, start, end, municipality_ids)
            st.session_state["_vendor_pdf"] = pdf_bytes
            safe_name = "".join(c if c.isalnum() or c in "ー_-" else "_" for c in selected)[:40]
            st.session_state["_vendor_pdf_name"] = f"事業者レポート_{safe_name}_{start}_{end}.pdf"
    with pdfcol2:
        if "_vendor_pdf" in st.session_state:
            st.download_button(
                "💾 PDFを保存",
                data=st.session_state["_vendor_pdf"],
                file_name=st.session_state["_vendor_pdf_name"],
                mime="application/pdf",
                key="vendor_pdf_save",
            )


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🏭 事業者別 分析")

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
        key="vendor_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    st.markdown("---")
    _vendor_ranking_section(conn, start, end, municipality_ids)

    st.markdown("---")
    _vendor_detail_section(conn, start, end, municipality_ids)
