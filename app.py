"""HIDAKARAanalytics - Streamlit entry point (multi-municipality)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db, list_municipalities
from src.ingest import (
    delete_import,
    get_import_history,
    get_table_counts,
    ingest_csv,
)
from src.views import channel as view_channel
from src.views import comparison as view_comparison
from src.views import ranking as view_ranking
from src.views import settings as view_settings
from src.views import summary as view_summary
from src.views import trend as view_trend
from src.views import vendor as view_vendor

st.set_page_config(
    page_title="HIDAKARAanalytics",
    page_icon="📊",
    layout="wide",
)


@st.cache_resource
def _get_conn():
    return ensure_db()


def _municipality_filter_widget(conn) -> tuple[list[int] | None, list[dict]]:
    """Render the global municipality multi-select. Returns (selected_ids, all_munis).

    Returns None for selected_ids if all are selected (= no filter)."""
    all_munis = list_municipalities(conn, active_only=False)
    if not all_munis:
        return None, []

    all_ids = [m["id"] for m in all_munis]
    name_by_id = {m["id"]: m["name"] for m in all_munis}

    selected_ids = st.sidebar.multiselect(
        "🏛️ 自治体（複数選択可）",
        options=all_ids,
        default=all_ids,
        format_func=lambda i: name_by_id.get(i, str(i)),
        key="global_municipality_filter",
    )

    if not selected_ids or set(selected_ids) == set(all_ids):
        return None, all_munis  # None = all (no filter)
    return selected_ids, all_munis


def _ingest_section(conn, munis: list[dict]) -> None:
    st.sidebar.markdown("---")
    st.sidebar.header("📥 データ取込")

    if not munis:
        st.sidebar.warning("先に「⚙️ 設定」タブで自治体を追加してください。")
        return

    name_by_id = {m["id"]: m["name"] for m in munis}
    ingest_muni_id = st.sidebar.selectbox(
        "取込先の自治体",
        options=[m["id"] for m in munis],
        format_func=lambda i: name_by_id.get(i, str(i)),
        key="ingest_municipality",
    )

    uploaded = st.sidebar.file_uploader(
        "寄附情報CSV または 配送情報CSV をアップロード（複数可）",
        type=["csv"],
        accept_multiple_files=True,
        key="uploader",
    )

    if st.sidebar.button("📥 取込実行", type="primary", use_container_width=True):
        if not uploaded:
            st.sidebar.warning("CSVファイルを選択してください。")
        else:
            results = []
            with st.spinner("取込中..."):
                for f in uploaded:
                    try:
                        result = ingest_csv(conn, f, ingest_muni_id, file_name=f.name)
                        results.append(("success", result))
                    except Exception as e:
                        results.append(("error", (f.name, str(e))))
            for status, payload in results:
                if status == "success":
                    st.sidebar.success(payload.summary())
                else:
                    name, msg = payload
                    st.sidebar.error(f"{name}: {msg}")


def _stats_section(conn, selected_ids: list[int] | None) -> None:
    st.sidebar.markdown("---")
    st.sidebar.header("📦 蓄積データ")
    counts = get_table_counts(conn, municipality_id=None)
    col1, col2 = st.sidebar.columns(2)
    col1.metric("配送情報（全体）", f"{counts['shipments']:,}")
    col2.metric("寄附情報（全体）", f"{counts['donations']:,}")
    if selected_ids:
        c1, c2 = st.sidebar.columns(2)
        # Sum across selected
        from src.ingest import get_counts_per_municipality
        per = get_counts_per_municipality(conn)
        per_sel = per[per["id"].isin(selected_ids)] if not per.empty else per
        sn = int(per_sel["shipments"].sum()) if not per_sel.empty else 0
        dn = int(per_sel["donations"].sum()) if not per_sel.empty else 0
        c1.metric("配送（選択中）", f"{sn:,}")
        c2.metric("寄附（選択中）", f"{dn:,}")


def render_sidebar() -> tuple[list[int] | None, list[dict]]:
    st.sidebar.title("📊 HIDAKARAanalytics")
    st.sidebar.caption("ふるさと納税データ分析ダッシュボード")
    conn = _get_conn()

    selected_ids, all_munis = _municipality_filter_widget(conn)
    _ingest_section(conn, all_munis)
    _stats_section(conn, selected_ids)

    return selected_ids, all_munis


def render_main(selected_ids: list[int] | None) -> None:
    st.title("📊 HIDAKARAanalytics")
    st.caption("ふるさと納税の日次データ分析ダッシュボード（マルチ自治体対応）")

    conn = _get_conn()

    tabs = st.tabs(
        [
            "🏠 サマリー",
            "📈 推移",
            "🏆 商品ランキング",
            "🏭 事業者別",
            "🛒 チャネル別",
            "🏛️ 自治体比較",
            "⚙️ 設定",
            "📜 取込履歴",
        ]
    )

    with tabs[0]:
        view_summary.render(conn, selected_ids)
    with tabs[1]:
        view_trend.render(conn, selected_ids)
    with tabs[2]:
        view_ranking.render(conn, selected_ids)
    with tabs[3]:
        view_vendor.render(conn, selected_ids)
    with tabs[4]:
        view_channel.render(conn, selected_ids)
    with tabs[5]:
        view_comparison.render(conn, selected_ids)
    with tabs[6]:
        view_settings.render(conn)
    with tabs[7]:
        _render_import_history(conn)


def _render_import_history(conn) -> None:
    st.subheader("📜 取込履歴")
    st.caption(
        "間違えて取込んだ場合は、該当の行で「🗑 この取込を取消」を押すと、"
        "その取込で追加された行のみが削除されます（DBへ既存だった他のデータは影響を受けません）。"
    )

    history = get_import_history(conn, limit=100)
    if history.empty:
        st.write("まだ取込履歴がありません。サイドバーからCSVを取り込んでください。")
        return

    # Header row
    h = st.columns([0.6, 1.2, 3.5, 1.2, 1.0, 1.0, 1.6, 1.2])
    h[0].markdown("**ID**")
    h[1].markdown("**自治体**")
    h[2].markdown("**ファイル名**")
    h[3].markdown("**種類**")
    h[4].markdown("**新規**")
    h[5].markdown("**スキップ**")
    h[6].markdown("**取込日時**")
    h[7].markdown("**操作**")

    for _, row in history.iterrows():
        c = st.columns([0.6, 1.2, 3.5, 1.2, 1.0, 1.0, 1.6, 1.2])
        log_id = int(row["id"])
        c[0].write(log_id)
        c[1].write(row["自治体"] or "—")
        c[2].write(row["file_name"])
        c[3].write(row["file_type"])
        c[4].write(f"{int(row['rows_inserted']):,}")
        c[5].write(f"{int(row['rows_skipped']):,}")
        c[6].write(pd.Timestamp(row["imported_at"]).strftime("%Y-%m-%d %H:%M:%S"))

        confirm_key = f"confirm_del_{log_id}"
        with c[7]:
            if st.session_state.get(confirm_key):
                cc1, cc2 = st.columns(2)
                if cc1.button("✓ 確定", key=f"yes_{log_id}", type="primary"):
                    result = delete_import(conn, log_id)
                    st.session_state[confirm_key] = False
                    if result.get("found"):
                        st.success(
                            f"取消完了: {result['file_name']} から {result['removed_rows']:,} 件削除"
                        )
                        st.rerun()
                    else:
                        st.error("対象の取込履歴が見つかりませんでした。")
                if cc2.button("× 中止", key=f"no_{log_id}"):
                    st.session_state[confirm_key] = False
                    st.rerun()
            else:
                if st.button("🗑 取消", key=f"del_{log_id}"):
                    st.session_state[confirm_key] = True
                    st.rerun()


def main() -> None:
    selected_ids, _ = render_sidebar()
    render_main(selected_ids)


if __name__ == "__main__":
    main()
