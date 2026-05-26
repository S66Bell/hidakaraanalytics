"""Summary tab: KPI cards + recent monthly trend."""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    Kpi,
    KpiComparison,
    get_data_date_range,
    get_monthly_kpi_set,
    get_recent_monthly_trend,
)
from src.format_utils import format_count, format_pct, format_yen, format_yen_round
from src.reports import build_monthly_excel, build_monthly_pdf

_format_yen = format_yen
_format_count = format_count
_format_pct = format_pct


def _delta_vs_current_label(
    period_val: float | int, current_val: float | int | None, *, is_pct: bool = False
) -> str | None:
    """Returns a delta string showing how the current month differs from this row's period.

    Streamlit's st.metric reads the leading +/- to color the arrow, so the
    string starts with the signed number.
    """
    if current_val is None or period_val is None or period_val == 0:
        return None
    if is_pct:
        diff_pt = (current_val - period_val) * 100
        return f"{diff_pt:+.1f}pt （当月との差）"
    rate = (current_val - period_val) / period_val * 100
    return f"{rate:+.1f}% （当月比）"


def _kpi_row(label: str, kpi: Kpi, current_for_comparison: Kpi | None = None) -> None:
    """Render a KPI row. `kpi` is this row's period; if `current_for_comparison`
    is provided, each metric also shows how the current month differs."""
    st.markdown(f"##### {label}")
    cols = st.columns(4)
    cmp_ = current_for_comparison
    with cols[0]:
        st.metric(
            "寄付金額",
            _format_yen(kpi.revenue),
            delta=_delta_vs_current_label(kpi.revenue, cmp_.revenue if cmp_ else None),
        )
    with cols[1]:
        st.metric(
            "件数",
            _format_count(kpi.orders),
            delta=_delta_vs_current_label(kpi.orders, cmp_.orders if cmp_ else None),
        )
    with cols[2]:
        st.metric(
            "謝礼品価格",
            _format_yen(kpi.total_cost),
            delta=_delta_vs_current_label(kpi.total_cost, cmp_.total_cost if cmp_ else None),
        )
    with cols[3]:
        st.metric(
            "経費率",
            _format_pct(kpi.expense_ratio),
            delta=_delta_vs_current_label(
                kpi.expense_ratio, cmp_.expense_ratio if cmp_ else None, is_pct=True
            ),
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
    # Row 1: current month actuals (no comparison delta)
    _kpi_row(kpis["current"].label + "（当月）", current_kpi, None)

    # Row 2: previous month's actuals; delta = how the current month compares
    prev_month_kpi = kpis["vs_prev_month"].previous
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if prev_month_kpi is not None and prev_month_kpi.revenue > 0:
        _kpi_row(kpis["vs_prev_month"].label, prev_month_kpi, current_kpi)
    else:
        st.markdown(f"##### {kpis['vs_prev_month'].label}")
        st.info("該当月のデータがありません。")

    # Row 3: previous year same month's actuals; delta = how current compares
    prev_year_kpi = kpis["vs_prev_year"].previous
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if prev_year_kpi is not None and prev_year_kpi.revenue > 0:
        _kpi_row(kpis["vs_prev_year"].label, prev_year_kpi, current_kpi)
    else:
        st.markdown(f"##### {kpis['vs_prev_year'].label}")
        st.info("該当月のデータがありません。")

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
                "expense_ratio": "経費率",
                "avg_order_value": "平均単価",
            }
        )
        display["寄付金額"] = display["寄付金額"].map(_format_yen)
        display["謝礼品価格"] = display["謝礼品価格"].map(_format_yen)
        display["件数"] = display["件数"].map(_format_count)
        display["平均単価"] = display["平均単価"].map(format_yen_round)
        display["経費率"] = display["経費率"].map(_format_pct)
        st.dataframe(display.iloc[::-1], use_container_width=True, hide_index=True)
