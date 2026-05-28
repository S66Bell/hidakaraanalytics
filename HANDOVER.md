# 引継ぎメモ — HIDAKARAanalytics

最終更新: 2026-05-28（Cloudflare Tunnel デプロイ進行中）

このファイルは「次にこのプロジェクトを触る人」向けの引継ぎノートです。
プロジェクトの全体像・用語ルール・データ仕様は `CLAUDE.md` を、デプロイ手順は `DEPLOYMENT.md` を、利用方法は `README.md` を参照。

---

## 0. 🚧 進行中タスク（次の Claude Code が引き継ぐべきもの）

**Cloudflare Tunnel + Access 経由での社外公開** の Phase 3（認証ゲート設定）の途中で中断しています。

### 現在の到達点

| Phase | 状態 |
|---|---|
| 1. ドメイン取得 (`aisuishin.com`) | ✅ Cloudflare Registrar で取得済み（アクティブ） |
| 1.5. Zero Trust 有効化 | ✅ Team 名 `twilight-butterfly-68b2`（Free プラン） |
| 2. Tunnel + cloudflared セットアップ | ✅ `hidakara-analytics` トンネル稼働中、`aisuishin.com` → `localhost:8501` ルーティング |
| 3. **Access ポリシー設定** | ⛔ **未完了** ← 再開時はここから |
| 4. 動作確認 | 認証なしの状態では `https://aisuishin.com` で接続可能 |

### 次にやること（Phase 3 続き）

1. Cloudflare Zero Trust → 「Access コントロール」→「アプリケーション」
2. 「+ アプリケーションを追加」→「セルフホスト型」
3. アプリケーション名: `HIDAKARAanalytics`、ドメイン: `aisuishin.com`（apex）
4. ポリシー作成: `@hidakara.com` のメアドのみ許可（One-time PIN 認証）
5. シークレットウィンドウで動作確認

### 重要メモ

- **新 UI では「Access 設定」配下に IdP（ID プロバイダー）の項目が無い**。アプリケーション作成中にインラインで「+ IdP 追加」が出るはずなので、そこから「ワンタイム PIN」を有効化する必要あり
- `hidakara.com` ドメインのメールが本当に届くかは未確認。テスト用に `yuuki.s66@gmail.com` も Include に追加すると安全
- Google Workspace 利用有無も未確認。あるなら OAuth に切替えると UX 向上

### 既存設定の控え

| 項目 | 値 |
|---|---|
| 公開 URL | `https://aisuishin.com` |
| Zero Trust Team | `twilight-butterfly-68b2` |
| Access URL | `twilight-butterfly-68b2.cloudflareaccess.com` |
| Tunnel 名 | `hidakara-analytics` |
| ルーティング | `aisuishin.com`（apex）→ `localhost:8501` |
| サーバー PC | `C:\Users\info\HIDAKARAanalytics_v2` |
| Cloudflare アカウント | `yuuki.s66@gmail.com`（推定） |

---

## 1. ひと目で状況把握

| 項目 | 状態 |
|---|---|
| 開発機（旧） | `C:\Users\info\motosuanalytics` |
| 社内サーバー機（新） | `C:\Users\info\HIDAKARAanalytics_v2` ← **現在稼働中** |
| ブランド名 | HIDAKARAanalytics |
| Streamlit | `start_server.bat` 起動で `http://localhost:8501` |
| 社外公開 URL | `https://aisuishin.com`（Cloudflare Tunnel 経由、認証未設定）|
| Git | GitHub プライベートリポジトリ `S66Bell/hidakaraanalytics` |
| 進行中ブランチ | `claude/loving-shannon-77YPm`（PR #1） |

## 2. 登録済み自治体（2026-05-26 時点）

| id | 名前 | code | 配送 | 寄附 | 配送 fmt | 寄附 fmt |
|---|---|---|---|---|---|---|
| 1 | 本巣市 | motosu | 98,415 | 72,931 | format_a | standard |
| 2 | 白川村 | shirakawa | 68,057 | 49,270 | format_b | standard |
| 3 | 飛騨市 | hida | 73,060 | 54,735 | format_c | no_product |
| 4 | 高山市 | takayama | 318,949 | 241,868 | format_a | standard |
| 5 | 郡上市 | gujo | 32,748 | 29,910 | format_a | standard |

合計 配送 591,229 件 / 寄附 448,714 件。残り 3 自治体は順次追加予定。

## 3. 集計ソースの大原則（直近の重要変更）

2026-05-26 に変更。これを把握していないと数値の意味を取り違えるので注意:

| 指標 | ソーステーブル |
|---|---|
| **寄付金額・件数** | `donations` |
| **謝礼品価格** | `shipments` |
| **経費率** | 謝礼品価格(shipments) / 寄付金額(donations) |
| カテゴリ・事業者・商品・チャネル別の分解 | `shipments` |

理由: 定期便など 1 寄附 → N 配送 のケースで shipments 側を sum すると件数が N 倍に膨らんでいたため。
寄附情報側は 1 行 = 1 寄附で正しい件数になる。

## 4. 直近にやった作業（過去 1〜2 日）

1. ✅ CLAUDE.md / DEPLOYMENT.md / HANDOVER.md 作成
2. ✅ パッケージング用 `pack_for_server.ps1` 作成
3. ✅ 高山市・郡上市のデータ取込
4. ✅ KPI 集計を shipments → donations 由来に切替（定期便二重カウント解消）
5. ✅ 自治体比較タブの plotly_chart 重複 ID エラー修正
6. ✅ Git 初期化 + GitHub プライベートリポジトリへ push
7. ✅ **新サーバー PC `C:\Users\info\HIDAKARAanalytics_v2` でセットアップ**
8. ✅ **`start_server.bat` の文字化け修正**（UTF-8 LF → ASCII CRLF + chcp 65001）→ PR #1
9. ✅ **`start_server.ps1` の堅牢化**（projectRoot 3 段フォールバック）→ PR #1
10. ✅ **Cloudflare Registrar で `aisuishin.com` 取得**
11. ✅ **Cloudflare Zero Trust 有効化**（Team `twilight-butterfly-68b2`、Free プラン）
12. ✅ **cloudflared インストール + Tunnel `hidakara-analytics` 作成**
13. ✅ **`aisuishin.com` apex → `localhost:8501` のルーティング設定**
14. ⛔ **Cloudflare Access ポリシー設定（未完了、ここから再開）**

## 5. これからやることリスト

優先度高:

- [ ] **Cloudflare Access ポリシー設定（`@hidakara.com` 限定）** ← 進行中
- [ ] PR #1（`claude/loving-shannon-77YPm`）のレビュー & マージ
- [ ] 残り 3 自治体のデータ取込
- [ ] サーバー稼働後、社内に URL 共有

優先度中:

- [ ] チャネル別タブを donations 由来に変更（現在 shipments）
- [ ] カテゴリ別・事業者別の合計値が KPI と微妙に違う（数% 程度）の説明追加 or 解消
- [ ] 月次レポート（Excel / PDF）出力の数値も donations 由来に切替

優先度低:

- [ ] 飛騨市のチャネル情報を補完（現状 shipments 側は NULL）
- [ ] Google Workspace あれば Access の認証を OAuth に切替（One-time PIN より UX 良い）

## 6. 重要な落とし穴

### 6.1 用語ルール（厳守）
- ❌ 売上 / 原価 / 粗利 / 粗利率 は禁止
- ✅ 寄付金額 / 謝礼品価格 / 経費率 を使う
- 詳細は CLAUDE.md の「用語ルール」

### 6.2 フォルダ名
- 旧開発機: `C:\Users\info\motosuanalytics`
- 新サーバー機: `C:\Users\info\HIDAKARAanalytics_v2`
- `.venv` は各場所で個別に作成（絶対パス埋め込みなので移動・リネーム不可）

### 6.3 DB ロック
- DuckDB は同時 1 接続のみ書込み可能
- スキーマ変更時は必ず Streamlit を停止
- 停止: `Get-Process | Where-Object { $_.ProcessName -eq 'python' -and ($_.Path -like "*motosuanalytics*" -or $_.Path -like "*HIDAKARAanalytics*") } | Stop-Process -Force`

### 6.4 取込ミスのリカバリ
- 「📜 取込履歴」タブから「🗑 取消」で個別の取込を取り消せる
- 2026-05-26 以降の取込のみ対応（それ以前のは imported_at が揃っていない可能性）

### 6.5 CSV フォーマット
- 自治体ごとに違うため、新自治体追加時は `src/ingest.py` の format_a/b/c のどれに当たるか確認
- どれにも当たらない場合は format_d を追加する必要あり
- 検出ロジックは `detect_file_type()` 関数

## 7. 開発・運用コマンド早見表

```powershell
# 起動（新サーバー機: HIDAKARAanalytics_v2）
cd C:\Users\info\HIDAKARAanalytics_v2
.\start_server.bat

# 起動（手動・旧開発機）
cd C:\Users\info\motosuanalytics
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501

# 停止（両環境対応）
Get-Process | Where-Object { $_.ProcessName -eq 'python' -and ($_.Path -like "*motosuanalytics*" -or $_.Path -like "*HIDAKARAanalytics*") } | Stop-Process -Force

# Cloudflare Tunnel サービス状態
Get-Service cloudflared
Start-Service cloudflared  # 必要に応じて

# DB 状態確認
.\.venv\Scripts\python.exe tests\check_db.py

# サーバー機用 ZIP パッケージ作成（デスクトップに出力）
.\pack_for_server.ps1

# 依存関係追加後
.\.venv\Scripts\pip install <pkg>
.\.venv\Scripts\pip freeze > requirements.txt

# Git 操作（リモート: S66Bell/hidakaraanalytics）
git status
git add <files>
git commit -m "<message>"
git push
```

## 8. ファイル別の役割（ざっくり）

| ファイル | 役割 |
|---|---|
| `app.py` | Streamlit エントリ、サイドバー、タブ構成 |
| `src/db.py` | DuckDB スキーマ、マイグレーション、自治体 CRUD |
| `src/ingest.py` | CSV 取込、フォーマット自動検出、取消機能 |
| `src/analytics.py` | 集計 SQL ロジック（donations 主、shipments 補助）|
| `src/reports.py` | Excel / PDF レポート生成 |
| `src/format_utils.py` | NaN 安全な数値フォーマッタ |
| `src/views/*.py` | 各タブの UI 実装 |
| `CLAUDE.md` | プロジェクト全体仕様（Claude Code 用） |
| `README.md` | 利用者向け概要 |
| `DEPLOYMENT.md` | サーバー構築手順 |
| `HANDOVER.md` | このファイル |
| `pack_for_server.ps1` | サーバー機用 ZIP パッケージング |
| `start_server.ps1` / `.bat` | サーバー機での起動 |
| `tests/*.py` | スモークテスト・診断スクリプト |

## 9. 困ったときの参照先

- 全体仕様: `CLAUDE.md`
- サーバー構築: `DEPLOYMENT.md`
- 利用方法: `README.md`
- 開発メモ（過去の経緯）: `C:\Users\info\.claude\projects\C--Users-info-motosuanalytics\memory\` 配下の各 `.md`
- Git リポジトリ: https://github.com/S66Bell/hidakaraanalytics
