"""Summary tab: KPI cards + recent monthly trend."""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    Kpi,
    get_data_date_range,
    get_monthly_kpi_set,
    get_recent_monthly_trend,
)
from src.format_utils import format_count, format_pct, format_yen, format_yen_round
from src.reports import build_monthly_excel, build_monthly_pdf

_format_yen = format_yen
_format_count = format_count
_format_pct = format_pct


def _yoy_label(current_val: float | int, prev_val: float | int | None) -> str | None:
    """前年比（増減率）。st.metric は先頭の +/- で矢印色を決めるので符号付きで返す。"""
    if prev_val is None or current_val is None or prev_val == 0:
        return None
    rate = (current_val - prev_val) / prev_val * 100
    return f"{rate:+.1f}% （前年比）"


def _yoy_pt_label(current_ratio: float | None, prev_ratio: float | None) -> str | None:
    """返礼率のような比率指標の前年比は差分（ポイント）で示す。"""
    if prev_ratio is None or current_ratio is None:
        return None
    diff_pt = (current_ratio - prev_ratio) * 100
    return f"{diff_pt:+.1f}pt （前年比）"


def _current_kpi_row(current: Kpi, prev_year: Kpi | None) -> None:
    """当月の KPI（寄付金額・件数・返礼率）を表示し、各カードに前年比を出す。"""
    has_prev = prev_year is not None and prev_year.revenue > 0
    cols = st.columns(3)
    with cols[0]:
        st.metric(
            "寄付金額",
            _format_yen(current.revenue),
            delta=_yoy_label(current.revenue, prev_year.revenue) if has_prev else None,
        )
    with cols[1]:
        st.metric(
            "件数",
            _format_count(current.orders),
            delta=_yoy_label(current.orders, prev_year.orders) if has_prev else None,
        )
    with cols[2]:
        st.metric(
            "返礼率",
            _format_pct(current.expense_ratio),
            delta=_yoy_pt_label(current.expense_ratio, prev_year.expense_ratio) if has_prev else None,
            delta_color="off",
        )


def _monthly_trend_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["period"],
            y=df["revenue"],
            name="寄付金額",
            marker_color="#1f77b4",
            yaxis="y1",
            hovertemplate="%{x|%Y年%m月}<br>寄付金額: ¥%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["period"],
            y=df["total_cost"],
            name="謝礼品価格",
            marker_color="#d62728",
            yaxis="y1",
            hovertemplate="%{x|%Y年%m月}<br>謝礼品価格: ¥%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["orders"],
            name="件数",
            mode="lines+markers",
            marker_color="#ff7f0e",
            yaxis="y2",
            hovertemplate="%{x|%Y年%m月}<br>件数: %{y:,}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(title="金額（円）", tickformat=",.0f"),
        yaxis2=dict(title="件数", overlaying="y", side="right", showgrid=False, tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🏠 サマリー")

    min_date, max_date = get_data_date_range(conn, municipality_ids)
    if max_date is None:
        st.info("まだ取込データがありません。サイドバーからCSVを取り込んでください。")
        return

    scope = "全自治体" if not municipality_ids else f"選択中 {len(municipality_ids)} 自治体"
    st.caption(f"データ期間: {min_date} 〜 {max_date} ／ 範囲: {scope}")

    # Month selector for the reference month
    available_months = pd.date_range(
        start=date(min_date.year, min_date.month, 1),
        end=date(max_date.year, max_date.month, 1),
        freq="MS",
    ).to_pydatetime().tolist()
    available_months = [d.date() for d in available_months]

    default_index = len(available_months) - 1
    selected = st.selectbox(
        "対象月",
        options=available_months,
        index=default_index,
        format_func=lambda d: f"{d.year}年{d.month}月",
        key="summary_month",
    )

    kpis = get_monthly_kpi_set(conn, reference_month=selected, municipality_ids=municipality_ids)
    current_kpi = kpis["current"].current

    rcol1, rcol2, rcol3 = st.columns([1, 1, 4])
    with rcol1:
        if st.button("📊 Excel ダウンロード", key="dl_xlsx"):
            xlsx_bytes = build_monthly_excel(conn, selected.year, selected.month, municipality_ids)
            st.session_state["_summary_xlsx"] = xlsx_bytes
            st.session_state["_summary_xlsx_name"] = f"月次レポート_{selected.year}{selected.month:02d}.xlsx"
        if "_summary_xlsx" in st.session_state:
            st.download_button(
                "💾 Excel を保存",
                data=st.session_state["_summary_xlsx"],
                file_name=st.session_state["_summary_xlsx_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx_save",
            )
    with rcol2:
        if st.button("📄 PDF ダウンロード", key="dl_pdf"):
            with st.spinner("PDF生成中..."):
                pdf_bytes = build_monthly_pdf(conn, selected.year, selected.month, municipality_ids)
            st.session_state["_summary_pdf"] = pdf_bytes
            st.session_state["_summary_pdf_name"] = f"月次レポート_{selected.year}{selected.month:02d}.pdf"
        if "_summary_pdf" in st.session_state:
            st.download_button(
                "💾 PDF を保存",
                data=st.session_state["_summary_pdf"],
                file_name=st.session_state["_summary_pdf_name"],
                mime="application/pdf",
                key="dl_pdf_save",
            )

    st.markdown("---")
    # 当月の KPI を表示し、各カードに前年同月比を出す
    prev_year_kpi = kpis["vs_prev_year"].previous
    st.markdown(f"##### {kpis['current'].label}（当月）")
    _current_kpi_row(current_kpi, prev_year_kpi)
    if prev_year_kpi is not None and prev_year_kpi.revenue > 0:
        st.caption(f"増減は {kpis['vs_prev_year'].label} との比較")
    else:
        st.caption("前年同月のデータがないため前年比は表示していません。")

    st.markdown("---")
    st.markdown("##### 月次推移（直近24ヶ月）")
    df = get_recent_monthly_trend(conn, months=24, municipality_ids=municipality_ids)
    if df.empty:
        st.info("月次データがありません。")
        return
    st.plotly_chart(_monthly_trend_chart(df), use_container_width=True)

    with st.expander("📋 月次データを表で確認"):
        display = df.copy()
        display["period"] = display["period"].dt.strftime("%Y年%m月")
        display = display.rename(
            columns={
                "period": "月",
                "orders": "件数",
                "revenue": "寄付金額",
                "total_cost": "謝礼品価格",
                "expense_ratio": "返礼率",
                "avg_order_value": "平均単価",
            }
        )
        display["寄付金額"] = display["寄付金額"].map(_format_yen)
        display["謝礼品価格"] = display["謝礼品価格"].map(_format_yen)
        display["件数"] = display["件数"].map(_format_count)
        display["平均単価"] = display["平均単価"].map(format_yen_round)
        display["返礼率"] = display["返礼率"].map(_format_pct)
        st.dataframe(display.iloc[::-1], use_container_width=True, hide_index=True)
