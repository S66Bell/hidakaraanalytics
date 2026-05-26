"""Settings tab: manage municipalities and vendor aliases."""
from __future__ import annotations

import re

import duckdb
import streamlit as st

from src.db import (
    add_municipality,
    add_vendor_alias,
    delete_municipality,
    delete_vendor_alias,
    list_municipalities,
    list_vendor_aliases,
    update_municipality,
)
from src.ingest import get_counts_per_municipality


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "city"


def _municipality_section(conn: duckdb.DuckDBPyConnection) -> None:
    st.markdown("##### 🏛️ 自治体マスタ")
    st.caption("自治体の追加・編集・削除を行います。同じCSVフォーマットを使うので、追加するだけで取込可能になります。")

    counts = get_counts_per_municipality(conn)
    munis = list_municipalities(conn)

    if munis:
        st.markdown("**現在の自治体一覧**")
        for m in munis:
            cdata = counts[counts["id"] == m["id"]]
            ship_cnt = int(cdata.iloc[0]["shipments"]) if not cdata.empty else 0
            don_cnt = int(cdata.iloc[0]["donations"]) if not cdata.empty else 0

            with st.expander(
                f"{m['name']} （配送 {ship_cnt:,} 件 / 寄附 {don_cnt:,} 件）"
                + ("" if m["active"] else " ※非アクティブ"),
                expanded=False,
            ):
                ec1, ec2, ec3, ec4 = st.columns([2, 2, 1, 1])
                new_name = ec1.text_input(
                    "名前", value=m["name"], key=f"mun_name_{m['id']}"
                )
                new_code = ec2.text_input(
                    "コード（英数字）", value=m["code"], key=f"mun_code_{m['id']}"
                )
                new_active = ec3.checkbox("有効", value=m["active"], key=f"mun_active_{m['id']}")
                if ec4.button("💾 更新", key=f"mun_save_{m['id']}"):
                    try:
                        update_municipality(
                            conn,
                            m["id"],
                            name=new_name if new_name != m["name"] else None,
                            code=new_code if new_code != m["code"] else None,
                            active=new_active if new_active != m["active"] else None,
                        )
                        st.success("更新しました。ページを再読込してください。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"更新失敗: {e}")

                st.markdown("---")
                st.markdown("**削除（取り扱い注意）**")
                st.caption(f"この自治体に紐づく配送 {ship_cnt:,} 件、寄附 {don_cnt:,} 件、エイリアスも全て削除されます。")
                confirm = st.text_input(
                    "削除する場合は自治体名を入力", key=f"mun_del_confirm_{m['id']}", placeholder=m["name"]
                )
                if st.button("🗑️ 削除", key=f"mun_del_{m['id']}", type="secondary"):
                    if confirm == m["name"]:
                        deleted = delete_municipality(conn, m["id"])
                        st.success(f"削除しました: 配送 {deleted['shipments']:,} 件、寄附 {deleted['donations']:,} 件")
                        st.rerun()
                    else:
                        st.error("削除確認のため、自治体名を正確に入力してください。")
    else:
        st.info("自治体が登録されていません。下から追加してください。")

    st.markdown("---")
    st.markdown("**自治体を追加**")
    with st.form("add_municipality_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("自治体名", placeholder="例: 高山市")
        suggested_code = _slugify(new_name) if new_name else ""
        new_code = c2.text_input("コード（英数字）", value=suggested_code, placeholder="例: takayama")
        submit = st.form_submit_button("➕ 追加", type="primary")
        if submit:
            if not new_name or not new_code:
                st.error("自治体名とコードを両方入力してください。")
            else:
                try:
                    new_id = add_municipality(conn, new_name, new_code)
                    st.success(f"「{new_name}」を追加しました（ID={new_id}）。サイドバーで選択してCSVを取り込めます。")
                    st.rerun()
                except Exception as e:
                    st.error(f"追加失敗: {e}")


def _vendor_alias_section(conn: duckdb.DuckDBPyConnection) -> None:
    st.markdown("##### 🔗 事業者エイリアス（同一視テーブル）")
    st.caption(
        "「トキノヤ食品」と「トキノヤ食品株式会社」のような表記揺れを同一の事業者として集計します。"
        "代表名（canonical_name）が集計時の表示名になります。"
    )

    aliases = list_vendor_aliases(conn)
    if aliases:
        st.markdown("**登録済みエイリアス**")
        munis = {m["id"]: m["name"] for m in list_municipalities(conn)}
        for a in aliases:
            scope = "全自治体" if a["municipality_id"] is None else munis.get(a["municipality_id"], "?")
            cols = st.columns([3, 3, 2, 1])
            cols[0].text(a["canonical_name"])
            cols[1].text(f"⇐ {a['alias_name']}")
            cols[2].text(f"範囲: {scope}")
            if cols[3].button("🗑️", key=f"alias_del_{a['id']}"):
                delete_vendor_alias(conn, a["id"])
                st.rerun()
    else:
        st.info("エイリアスはまだ登録されていません。")

    st.markdown("---")
    st.markdown("**エイリアスを追加**")
    with st.form("add_alias_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        canonical = c1.text_input("代表名（canonical）", placeholder="トキノヤ食品株式会社")
        alias = c2.text_input("別名（alias）", placeholder="トキノヤ食品")
        munis = list_municipalities(conn)
        scope_options = ["全自治体共通"] + [m["name"] for m in munis]
        scope_label = st.selectbox("適用範囲", scope_options)
        submit = st.form_submit_button("➕ 追加", type="primary")
        if submit:
            if not canonical or not alias:
                st.error("代表名と別名を両方入力してください。")
            elif canonical == alias:
                st.error("代表名と別名が同じです。")
            else:
                muni_id = None
                if scope_label != "全自治体共通":
                    muni_id = next((m["id"] for m in munis if m["name"] == scope_label), None)
                try:
                    add_vendor_alias(conn, canonical, alias, muni_id)
                    st.success("追加しました。")
                    st.rerun()
                except Exception as e:
                    st.error(f"追加失敗: {e}")


def render(conn: duckdb.DuckDBPyConnection) -> None:
    st.subheader("⚙️ 設定")

    tabs = st.tabs(["🏛️ 自治体", "🔗 事業者エイリアス"])
    with tabs[0]:
        _municipality_section(conn)
    with tabs[1]:
        _vendor_alias_section(conn)
