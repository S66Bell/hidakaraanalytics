# 引継ぎメモ — HIDAKARAanalytics

最終更新: 2026-05-26

このファイルは「次にこのプロジェクトを触る人」向けの引継ぎノートです。
プロジェクトの全体像・用語ルール・データ仕様は `CLAUDE.md` を、デプロイ手順は `DEPLOYMENT.md` を、利用方法は `README.md` を参照。

---

## 1. ひと目で状況把握

| 項目 | 状態 |
|---|---|
| 開発機 | `C:\Users\info\motosuanalytics`（このフォルダ） |
| サーバー機 | 別 PC を準備中（DEPLOYMENT.md の手順で構築） |
| ブランド名 | HIDAKARAanalytics（フォルダ名は `motosuanalytics` のまま） |
| Streamlit | ローカル http://localhost:8501 で起動可能 |
| Git | GitHub プライベートリポジトリ `S66Bell/hidakaraanalytics` |

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

1. ✅ CLAUDE.md / DEPLOYMENT.md / HANDOVER.md（このファイル）作成
2. ✅ パッケージング用 `pack_for_server.ps1` 作成（別PCサーバー化用）
3. ✅ 高山市・郡上市のデータ取込
4. ✅ KPI 集計を shipments → donations 由来に切替（定期便二重カウント解消）
5. ✅ 自治体比較タブの plotly_chart 重複 ID エラー修正
6. ✅ Git 初期化 + GitHub プライベートリポジトリへ push

## 5. これからやることリスト

優先度高:

- [ ] 残り 3 自治体のデータ取込
- [ ] 別 PC でのサーバー構築（DEPLOYMENT.md 参照）
- [ ] サーバー稼働後、社内に URL 共有

優先度中:

- [ ] チャネル別タブを donations 由来に変更（現在 shipments）
- [ ] カテゴリ別・事業者別の合計値が KPI と微妙に違う（数% 程度）の説明追加 or 解消
- [ ] 月次レポート（Excel / PDF）出力の数値も donations 由来に切替

優先度低:

- [ ] 飛騨市のチャネル情報を補完（現状 shipments 側は NULL）
- [ ] Cloudflare Tunnel + Access で社外公開（必要になったら）

## 6. 重要な落とし穴

### 6.1 用語ルール（厳守）
- ❌ 売上 / 原価 / 粗利 / 粗利率 は禁止
- ✅ 寄付金額 / 謝礼品価格 / 経費率 を使う
- 詳細は CLAUDE.md の「用語ルール」

### 6.2 フォルダ名は変えない
- `C:\Users\info\motosuanalytics` のまま保持
- `.venv` がこのパスに依存
- リネームしたい場合は `.venv` 再作成が必要

### 6.3 DB ロック
- DuckDB は同時 1 接続のみ書込み可能
- スキーマ変更時は必ず Streamlit を停止
- 停止: `Get-Process | Where-Object { $_.ProcessName -eq 'python' -and $_.Path -like "*motosuanalytics*" } | Stop-Process -Force`

### 6.4 取込ミスのリカバリ
- 「📜 取込履歴」タブから「🗑 取消」で個別の取込を取り消せる
- 2026-05-26 以降の取込のみ対応（それ以前のは imported_at が揃っていない可能性）

### 6.5 CSV フォーマット
- 自治体ごとに違うため、新自治体追加時は `src/ingest.py` の format_a/b/c のどれに当たるか確認
- どれにも当たらない場合は format_d を追加する必要あり
- 検出ロジックは `detect_file_type()` 関数

## 7. 開発・運用コマンド早見表

```powershell
# 起動（localhost）
cd C:\Users\info\motosuanalytics
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501

# 起動（LAN 公開、サーバー機用）
.\start_server.bat

# 停止
Get-Process | Where-Object { $_.ProcessName -eq 'python' -and $_.Path -like "*motosuanalytics*" } | Stop-Process -Force

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
