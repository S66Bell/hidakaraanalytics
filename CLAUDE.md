# CLAUDE.md — HIDAKARAanalytics

このファイルは Claude Code がこのプロジェクトを扱うときに最初に読むコンテキストです。実装・修正の前に必ず目を通してください。

---

## プロジェクト概要

- **名称（UI 表示）**: HIDAKARAanalytics
- **フォルダ名（変更不可）**: `C:\Users\info\motosuanalytics`
  - `.venv` が絶対パスに依存しているため、フォルダリネームは原則 NG
- **目的**: ふるさと納税の日次データ（寄附情報CSV + 配送情報CSV）を **複数自治体まとめて** 蓄積し、経営層向けレポートと事業者別レポートを発行するダッシュボード
- **想定ユーザー**: 自治体運営側の社員（複数人が日次でデータ取込）、経営層、事業者
- **稼働形態**: ローカル PC → 将来 社内 LAN サーバー（古い PC 1 台 + Cloudflare Tunnel + Cloudflare Access 想定、完全無料運用）

---

## ⚠️ 用語ルール（最重要）

ユーザー指定で **以下の用語は使用禁止**。必ず置換版を使うこと:

| 禁止 | 使用する用語 | DB カラム | 意味 |
|---|---|---|---|
| 売上 | **寄付金額** | `donation_amount` | 寄附者が支払った額 |
| 原価 | **謝礼品価格** | `product_price` | 自治体が支払う商品代金 |
| 粗利 | （概念ごと削除） | — | 表示しない |
| 粗利率 | **経費率** | `expense_ratio` | `謝礼品価格 / 寄付金額` |

新規 UI・レポート・ドキュメントを作成する際は必ずこの用語で統一。SQL クエリ内部の英語フィールド名（`revenue`, `total_cost`）は内部実装のためそのままで OK。

---

## 技術スタック

- Python 3.13
- **Streamlit** — UI（社内 Web ダッシュボード）
- **DuckDB** — 単一ファイル分析 DB（`data/warehouse.duckdb`）
- **pandas** — データ処理
- **Plotly** — インタラクティブグラフ
- **ReportLab** + IPAex Gothic/Mincho フォント — PDF 出力
- **openpyxl** — Excel 出力（グラフ埋込み対応）
- **matplotlib** — PDF 用チャート生成（日本語対応）

仮想環境: `C:\Users\info\motosuanalytics\.venv`

---

## ディレクトリ構成

```
motosuanalytics/
├── CLAUDE.md                   ← このファイル
├── README.md
├── app.py                      ← Streamlit エントリポイント
├── requirements.txt
├── start_server.bat            ← サーバー起動用（ダブルクリック）
├── start_server.ps1
├── .venv/                      ← 仮想環境（リネーム禁止）
├── data/
│   ├── raw/                    ← 受領した生 CSV のバックアップ
│   ├── warehouse.duckdb        ← 集約 DB
│   └── reports/                ← 出力されたレポート（Excel/PDF）
├── assets/
│   └── fonts/                  ← IPAex Gothic/Mincho（PDF 日本語用、コミット対象）
├── src/
│   ├── db.py                   ← DuckDB 接続・スキーマ・マイグレーション・自治体 CRUD
│   ├── ingest.py               ← CSV 取込（フォーマット自動検出 + マルチ自治体 + 取消機能）
│   ├── analytics.py            ← 集計クエリ（全関数 municipality_ids フィルタ対応）
│   ├── reports.py              ← Excel/PDF レポート生成
│   ├── format_utils.py         ← NaN 安全なフォーマッタ（format_yen / format_pct / 等）
│   └── views/
│       ├── summary.py          ← 🏠 サマリー
│       ├── trend.py            ← 📈 推移
│       ├── ranking.py          ← 🏆 商品ランキング
│       ├── vendor.py           ← 🏭 事業者別（事業者検索 + 個別 PDF）
│       ├── channel.py          ← 🛒 チャネル別
│       ├── comparison.py       ← 🏛️ 自治体比較（サイドバイサイド + 全自治体）
│       └── settings.py         ← ⚙️ 設定（自治体 CRUD + エイリアス管理）
└── tests/                      ← スモークテスト・一回限りスクリプト
    ├── smoke_ingest.py
    ├── smoke_reports.py
    ├── ingest_shirakawa.py
    ├── ingest_hida.py
    └── check_db.py
```

---

## 起動・開発コマンド

```powershell
# 開発用起動（localhost のみ、デフォルト）
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false

# 社内 LAN 公開（要 Windows ファイアウォール開放）
.\start_server.ps1
# または
.\start_server.bat

# ブラウザで http://localhost:8501
```

依存追加後:
```powershell
.\.venv\Scripts\pip install <package>
.\.venv\Scripts\pip freeze > requirements.txt  # 必要に応じて
```

---

## データモデル

5 つのテーブル（DuckDB）。マルチ自治体対応。

```
municipalities      id(PK), name, code, active, created_at
vendor_aliases      id(PK), canonical_name, alias_name, municipality_id (NULL=全自治体共通)
shipments           shipment_no, municipality_id, category, product_code, product_name,
                    vendor, donation_amount, channel, payment_date, product_price, imported_at
                    PK = (municipality_id, shipment_no)
donations           donation_id(PK), municipality_id, payment_date, channel, donation_amount,
                    product_name, composite_key, imported_at
                    UNIQUE(municipality_id, composite_key)
import_logs         id(PK), municipality_id, file_name, file_type, rows_inserted,
                    rows_skipped, imported_at
```

### 重要: 取込ロット単位の削除の仕組み
- ingest 時に `batch_ts = pd.Timestamp.now()` を生成し、**import_logs と shipments/donations の `imported_at` を同一値で揃える**
- `delete_import(conn, import_log_id)` は `(municipality_id, imported_at)` の組で対象行を DELETE
- スキーマ変更なしで取消機能を実現している
- ⚠️ 改修前（2026-05-26 より前）に取り込んだ既存データは imported_at が揃っていない可能性があり、取消対象外

---

## CSV フォーマット（自治体ごとに異なる）

`detect_file_type()` がカラム集合で自動判定する。

### 配送 CSV
| フォーマット | 該当自治体 | 配送No. | 寄附方法 | 謝礼品番号 | 寄附金額 | 寄附設定金額 |
|---|---|---|---|---|---|---|
| **format_a** | 本巣市 | ✅ | ✅ | ✅ | — | ✅ |
| **format_b** | 白川村 | ❌ (合成キー生成) | ✅ | ✅ | ✅ | ✅ |
| **format_c** | 飛騨市 | ✅ | ❌ (NULL) | ❌ (NULL) | — | ✅ |

- いずれも `寄附設定金額` → `donation_amount` にマップ（per-row として SUM すると寄付金額合計になる）
- `配送No.` が無いフォーマット (format_b) は `SYN_xxx` 形式の合成キーを生成して一意性を担保
  - キー = `SHA1(municipality_id|payment_date|product_code|vendor|amount|row_seq)` 先頭 16 文字

### 寄附 CSV
| フォーマット | 該当自治体 | 謝礼品 | 受付日 |
|---|---|---|---|
| **standard** | 本巣市・白川村 | ✅ | — |
| **no_product** | 飛騨市 | ❌ (NULL) | ✅（discriminator） |

- 重複排除キーは `payment_date|channel|donation_amount|product_name|row_seq` の SHA1
- product_name が NULL の場合も seq で一意化できるので問題なし

### 文字コード
すべて Shift-JIS (cp932) 想定。`_read_csv()` が cp932 → utf-8-sig → utf-8 の順でフォールバック。

---

## 登録済み自治体（2026-05-26 時点）

| id | 名前 | code | 配送件数 | 寄附件数 | 配送 fmt | 寄附 fmt |
|---|---|---|---|---|---|---|
| 1 | 本巣市 | motosu | 98,415 | 72,931 | format_a | standard |
| 2 | 白川村 | shirakawa | 68,057 | 49,270 | format_b | standard |
| 3 | 飛騨市 | hida | 73,060 | 54,735 | format_c | no_product |

合計: 配送 239,532 件 / 寄附 176,936 件

残り 5 自治体は順次追加予定。新フォーマットが出てきたら ingest.py に追加する。

---

## 開発上の注意点

### 1. 用語の徹底
- UI / レポート / コメント / ドキュメントで `売上 / 原価 / 粗利 / 粗利率` を絶対使わない
- 既存コードでうっかり残っていたら見つけ次第修正

### 2. NaN 安全なフォーマッタを使う
- `format_yen`, `format_count`, `format_pct`, `format_int`, `format_yen_round` は NaN/None で `—` を返す
- `int(value)` `round(value)` を直接呼ぶと NaN で `ValueError` が出るので、必ず format_utils 経由

### 3. fetchone() の防御
- DuckDB + Streamlit `@st.cache_resource` の組合せで稀に `fetchone()` が None を返す
- COUNT クエリでも `_scalar()` などの防御的ヘルパーを使う
- `get_table_counts()` のパターンを参考にする

### 4. マルチ自治体フィルタ
- 集計関数は全て `municipality_ids: list[int] | None` を受け取る
- `None` または全自治体選択 = フィルタなし（全体集計）
- ビュー側からは `selected_ids` を渡す（`None` のとき全体）

### 5. DB ロックと Streamlit
- DuckDB は同時に 1 接続しか書込めない → Streamlit が動いている間は別プロセスから DB を変更できない
- スキーマ変更や手作業マイグレーションが必要な時は Streamlit を停止してから実行
- 停止コマンド: `Get-Process | Where-Object { $_.ProcessName -eq 'python' -and $_.Path -like "*motosuanalytics*" } | Stop-Process -Force`

### 6. 自治体ごとの集計
- 同じ事業者が複数自治体に供給するケースがある（要 `vendor_aliases` テーブルで同一視）
- 同じ商品コードも自治体跨ぎで存在する場合あり
- 「全自治体合算」と「自治体個別」を切り替えられる作りにする

### 7. レポート生成での日本語
- PDF: `reports.py` の `_register_fonts()` で IPAex Gothic/Mincho を登録（`assets/fonts/` 必須）
- matplotlib も `_setup_matplotlib()` で同フォントを登録

---

## 検証用スクリプト

```powershell
# DB 状態確認
.\.venv\Scripts\python.exe tests\check_db.py

# 取込スモークテスト（CSV → 取込 → 件数表示）
.\.venv\Scripts\python.exe tests\smoke_ingest.py

# レポート生成スモークテスト（Excel/PDF を data/reports/ に出力）
.\.venv\Scripts\python.exe tests\smoke_reports.py
```

---

## デプロイ計画（メモ）

**確定方針**: 完全無料運用

1. **現状**: ローカル PC で開発・テスト
2. **次フェーズ**: 別の社内 PC（古い PC）をサーバー化して社内 LAN 共有
   - `start_server.bat` を起動するだけで稼働
   - 同じ Wi-Fi/LAN 内の PC から `http://<サーバー PC IP>:8501` でアクセス
   - Windows ファイアウォールの開放（port 8501、Inbound、Private/Domain）が必要
3. **最終形**: Cloudflare Tunnel + Cloudflare Access（Google SSO）で社外アクセス対応
   - 月額 0 円（Cloudflare 無料プランの 50 ユーザー枠内）
   - 経営層は会社の Google アカウントでログインするだけ

---

## 既知の制約・TODO

- 改修前（2026-05-26 より前）に取り込んだ既存データは取込履歴からの取消ができない可能性あり
- 飛騨市は元データに `寄附方法` がないためチャネル別分析では `(不明)` 扱い
- 取込ボタンに対する Streamlit の管理者権限（ファイアウォール開放）はユーザー手動操作が必要

---

## 関連メモリ（Claude のメモリディレクトリ）

`C:\Users\info\.claude\projects\C--Users-info-motosuanalytics\memory\`

- `user_profile.md` — ユーザーの業務領域
- `company_environment.md` — Google Workspace + GAS 環境
- `project_motosuanalytics.md` — プロジェクト概要
- `tech_stack.md` — 技術スタック選定理由
- `data_spec.md` — CSV スキーマ・用語定義
- `multi_municipality.md` — マルチ自治体の設計と CSV フォーマット詳細
- `deployment_plan.md` — デプロイ計画
