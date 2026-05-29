"""Single-municipality deep-dive tab (1自治体ドリルダウン)."""
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
    get_municipality_kpis,
    get_period_aggregates,
    get_product_ranking,
    get_vendor_ranking,
    shift_one_year,
)
from src.db import list_municipalities
from src.format_utils import (
    format_count,
    format_int,
    format_pct,
    format_yen,
    format_yen_round,
    format_yoy,
)


def _yoy_label(current_val, prev_val) -> str | None:
    if prev_val is None or current_val is None or prev_val == 0:
        return None
    return f"{(current_val - prev_val) / prev_val * 100:+.1f}% （前年比）"


def _yoy_pt_label(current_ratio, prev_ratio) -> str | None:
    if prev_ratio is None or current_ratio is None:
        return None
    return f"{(current_ratio - prev_ratio) * 100:+.1f}pt （前年比）"


def _kpi_dict_from_row(df: pd.DataFrame, muni_id: int) -> dict | None:
    if df.empty:
        return None
    sub = df[df["municipality_id"] == muni_id]
    if sub.empty:
        return None
    r = sub.iloc[0]
    return {
        "revenue": int(r["revenue"]),
        "orders": int(r["orders"]),
        "total_cost": int(r["total_cost"]),
        "expense_ratio": float(r["expense_ratio"]),
        "product_count": int(r["product_count"]),
        "vendor_count": int(r["vendor_count"]),
    }


def _monthly_chart(df: pd.DataFrame) -> go.Figure:
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
        height=380,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None, tickformat="%Y/%m"),
        yaxis=dict(title="寄付金額（円）", tickformat=",.0f"),
        yaxis2=dict(title="件数", overlaying="y", side="right", showgrid=False, tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def _composition_pie(df: pd.DataFrame, names_col: str) -> go.Figure:
    top = df.head(10).copy()
    if len(df) > 10:
        other = pd.DataFrame([{names_col: "その他", "revenue": df.iloc[10:]["revenue"].sum()}])
        top = pd.concat([top[[names_col, "revenue"]], other], ignore_index=True)
    fig = px.pie(top, names=names_col, values="revenue", hole=0.4)
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}<br>寄付金額: ¥%{value:,}<br>シェア: %{percent}<extra></extra>",
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    return fig


def _vendor_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    d = df.head(top_n).sort_values("revenue", ascending=True).copy()
    d["label"] = d["vendor"].str.slice(0, 30)
    d.loc[d["vendor"].str.len() > 30, "label"] += "…"
    fig = go.Figure(
        go.Bar(
            y=d["label"],
            x=d["revenue"],
            orientation="h",
            marker_color="#2ca02c",
            text=d["revenue"].map(lambda v: f"¥{int(v):,}"),
            textposition="outside",
            hovertemplate="%{y}<br>寄付金額: ¥%{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(360, 26 * len(d)),
        margin=dict(l=10, r=120, t=10, b=10),
        xaxis=dict(title="寄付金額（円）", tickformat=",.0f"),
        yaxis=dict(title=None, automargin=True),
    )
    return fig


def render(conn: duckdb.DuckDBPyConnection, municipality_ids: list[int] | None = None) -> None:
    st.subheader("🏙️ 自治体詳細（単一自治体ドリルダウン）")

    munis = list_municipalities(conn, active_only=True)
    if not munis:
        st.info("自治体がありません。「⚙️ 設定」タブから自治体を追加してください。")
        return

    name_by_id = {m["id"]: m["name"] for m in munis}
    ids = [m["id"] for m in munis]
    # グローバルフィルタで1つだけ選ばれていればそれを初期値に
    default_idx = 0
    if municipality_ids and municipality_ids[0] in ids:
        default_idx = ids.index(municipality_ids[0])

    sel_col, date_col = st.columns([1, 2])
    with sel_col:
        muni_id = st.selectbox(
            "自治体を選択",
            options=ids,
            index=default_idx,
            format_func=lambda i: name_by_id.get(i, str(i)),
            key="muni_detail_select",
        )
    muni_name = name_by_id[muni_id]

    min_date, max_date = get_data_date_range(conn, [muni_id])
    if max_date is None:
        st.info(f"{muni_name} の取込データがありません。")
        return

    with date_col:
        default_start = max(min_date, max_date - timedelta(days=365))
        date_range = st.date_input(
            "期間",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
            key="muni_detail_range",
        )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = default_start, max_date

    ps, pe = shift_one_year(start), shift_one_year(end)
    st.caption(
        f"対象: **{muni_name}** ／ 期間: {start} 〜 {end} "
        f"（前年比は {ps} 〜 {pe} と比較）"
    )

    # === KPI ===
    st.markdown("---")
    cur = _kpi_dict_from_row(get_municipality_kpis(conn, start, end), muni_id)
    prev = _kpi_dict_from_row(get_municipality_kpis(conn, ps, pe), muni_id)
    if cur is None:
        st.info("指定期間内にデータがありません。")
        return
    has_prev = prev is not None and prev["revenue"] > 0

    cols = st.columns(5)
    cols[0].metric(
        "寄付金額", format_yen(cur["revenue"]),
        delta=_yoy_label(cur["revenue"], prev["revenue"]) if has_prev else None,
    )
    cols[1].metric(
        "件数", format_count(cur["orders"]),
        delta=_yoy_label(cur["orders"], prev["orders"]) if has_prev else None,
    )
    cols[2].metric(
        "返礼率", format_pct(cur["expense_ratio"]),
        delta=_yoy_pt_label(cur["expense_ratio"], prev["expense_ratio"]) if has_prev else None,
        delta_color="off",
    )
    cols[3].metric("取扱商品数", format_int(cur["product_count"]))
    cols[4].metric("取扱事業者数", format_int(cur["vendor_count"]))
    if not has_prev:
        st.caption("前年同期のデータがないため前年比は表示していません。")

    # === Monthly trend ===
    st.markdown("---")
    st.markdown("##### 📈 月次推移")
    mdf = get_period_aggregates(conn, start, end, "month", [muni_id])
    if mdf.empty or len(mdf) < 2:
        st.info("月次推移を表示するには2か月以上のデータが必要です。")
    else:
        st.plotly_chart(_monthly_chart(mdf), use_container_width=True, key="muni_detail_monthly")

    # === Category composition ===
    st.markdown("---")
    st.markdown("##### 📦 カテゴリ構成")
    cat = get_category_ranking(conn, start, end, [muni_id])
    if cat.empty:
        st.info("カテゴリデータがありません。")
    else:
        prev_cat = get_category_ranking(conn, ps, pe, [muni_id])
        prev_rev = dict(zip(prev_cat["category"], prev_cat["revenue"])) if not prev_cat.empty else {}
        cat["revenue_prev"] = cat["category"].map(prev_rev)
        cat["yoy"] = (cat["revenue"] - cat["revenue_prev"]) / cat["revenue_prev"]
        c1, c2 = st.columns([1, 1])
        with c1:
            st.plotly_chart(_composition_pie(cat, "category"), use_container_width=True,
                            key="muni_detail_cat_pie")
        with c2:
            d = cat.copy()
            d["寄付金額"] = d["revenue"].map(format_yen)
            d["前年比"] = d["yoy"].map(format_yoy)
            d["件数"] = d["orders"].map(format_count)
            d["返礼率"] = d["expense_ratio"].map(format_pct)
            d = d.rename(columns={"category": "カテゴリ"})
            st.dataframe(
                d[["カテゴリ", "件数", "寄付金額", "前年比", "返礼率"]],
                use_container_width=True, hide_index=True, height=360,
            )

    # === Channel composition ===
    st.markdown("---")
    st.markdown("##### 🛒 チャネル構成")
    ch = get_channel_breakdown(conn, start, end, [muni_id])
    if ch.empty:
        st.info("チャネルデータがありません。")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.plotly_chart(_composition_pie(ch, "channel"), use_container_width=True,
                            key="muni_detail_ch_pie")
        with c2:
            d = ch.copy()
            d["寄付金額"] = d["revenue"].map(format_yen)
            d["件数"] = d["orders"].map(format_count)
            d["寄付金額シェア"] = d["share"].map(format_pct)
            d = d.rename(columns={"channel": "チャネル"})
            st.dataframe(
                d[["チャネル", "件数", "寄付金額", "寄付金額シェア"]],
                use_container_width=True, hide_index=True, height=360,
            )

    # === Top vendors ===
    st.markdown("---")
    st.markdown("##### 🏭 事業者 TOP")
    v = get_vendor_ranking(conn, start, end, municipality_ids=[muni_id])
    if v.empty:
        st.info("事業者データがありません。")
    else:
        prev_v = get_vendor_ranking(conn, ps, pe, municipality_ids=[muni_id])
        prev_vrev = dict(zip(prev_v["vendor"], prev_v["revenue"])) if not prev_v.empty else {}
        v["revenue_prev"] = v["vendor"].map(prev_vrev)
        v["yoy"] = (v["revenue"] - v["revenue_prev"]) / v["revenue_prev"]
        st.plotly_chart(_vendor_bar(v, top_n=15), use_container_width=True, key="muni_detail_vendor_bar")
        with st.expander("📋 事業者別データを表で確認"):
            d = v.copy()
            d["寄付金額"] = d["revenue"].map(format_yen)
            d["前年比"] = d["yoy"].map(format_yoy)
            d["謝礼品価格"] = d["total_cost"].map(format_yen)
            d["件数"] = d["orders"].map(format_count)
            d["取扱商品数"] = d["product_count"].map(format_int)
            d["返礼率"] = d["expense_ratio"].map(format_pct)
            d = d.rename(columns={"vendor": "事業者"})
            st.dataframe(
                d[["事業者", "件数", "取扱商品数", "寄付金額", "前年比", "謝礼品価格", "返礼率"]],
                use_container_width=True, hide_index=True,
            )

    # === Top products ===
    st.markdown("---")
    st.markdown("##### 🏆 商品 TOP20")
    prod = get_product_ranking(conn, start=start, end=end, limit=20, municipality_ids=[muni_id])
    if prod.empty:
        st.info("商品データがありません。")
    else:
        d = prod.copy()
        d["寄付金額"] = d["revenue"].map(format_yen)
        d["謝礼品価格"] = d["total_cost"].map(format_yen)
        d["件数"] = d["orders"].map(format_count)
        d["返礼率"] = d["expense_ratio"].map(format_pct)
        d["平均寄附額"] = d["avg_donation"].map(format_yen_round)
        d = d.rename(
            columns={
                "product_code": "商品コード",
                "product_name": "商品名",
                "category": "カテゴリ",
            }
        )
        st.dataframe(
            d[["商品コード", "商品名", "カテゴリ", "件数", "寄付金額", "謝礼品価格", "返礼率", "平均寄附額"]],
            use_container_width=True, hide_index=True,
        )
