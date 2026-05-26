# 🖥️ サーバー構築手順（別PCへの移行）

社内 LAN 内のサーバー PC で HIDAKARAanalytics を運用するための手順です。
**完全無料運用** が前提（追加ソフト・サービスへの課金なし）。

---

## ✅ 事前準備チェック

サーバーにする PC の要件:

| 項目 | 要件 |
|---|---|
| OS | Windows 10 / 11 |
| メモリ | 4GB 以上（推奨 8GB） |
| ストレージ | 空き 1GB 以上 |
| ネットワーク | 社内 LAN（Wi-Fi または有線）に接続 |
| 稼働時間 | 業務時間中（9:00〜18:00 想定）は起動状態にできる |
| Python | 3.13 を新規インストール予定（未インストールでOK） |

⚠️ **このサーバー PC を使う人は、業務時間中は基本的に**:
- シャットダウン・スリープしない（再起動はOK）
- 画面ロックはOK（バックグラウンドで稼働継続）

---

## Phase 1: 旧 PC でパッケージ作成

旧 PC（現在開発・運用中の PC）で実施します。

### 1-1. Streamlit を停止

```powershell
Get-Process | Where-Object { $_.ProcessName -eq 'python' -and $_.Path -like "*motosuanalytics*" } | Stop-Process -Force
```

### 1-2. パッケージング実行

PowerShell でプロジェクトフォルダに移動して:

```powershell
cd C:\Users\info\motosuanalytics
.\pack_for_server.ps1
```

→ デスクトップに `HIDAKARAanalytics_YYYYMMDD_HHMM.zip` が作成される（300〜500MB 程度）

含まれるもの: ソース・起動スクリプト・日本語フォント・蓄積済みDB（本巣市/白川村/飛騨市の全データ）

除外: `.venv` / `__pycache__` / 出力済みレポート

### 1-3. 新 PC に転送

以下のいずれかで:
- **USB メモリ** にコピー
- **社内共有フォルダ**（ネットワークドライブ）にコピー
- **OneDrive / Google ドライブ** 経由

---

## Phase 2: 新 PC で Python をインストール

### 2-1. Python 3.13 をダウンロード

[https://www.python.org/downloads/](https://www.python.org/downloads/) から **Windows installer (64-bit)** をダウンロード。バージョンは 3.13 系（または 3.12）。

### 2-2. インストール

インストーラを起動 → **「Add python.exe to PATH」にチェック** → **Install Now**

⚠️ PATH にチェックを入れないと PowerShell から `python` コマンドが使えません。

### 2-3. 動作確認

新しい PowerShell ウィンドウを開いて:

```powershell
python --version
# → Python 3.13.x が表示されればOK
```

---

## Phase 3: プロジェクト展開

### 3-1. ZIP を解凍

転送した `HIDAKARAanalytics_YYYYMMDD_HHMM.zip` を **以下の場所に展開** します:

```
C:\HIDAKARAanalytics\
```

（フォルダ名はお好みでも OK、ただし以降の手順は上記前提で書きます）

展開後、こんな構成になっているか確認:

```
C:\HIDAKARAanalytics\
├── app.py
├── requirements.txt
├── start_server.ps1
├── start_server.bat
├── CLAUDE.md
├── README.md
├── DEPLOYMENT.md          ← このファイル
├── src/
├── data/
│   └── warehouse.duckdb   ← データ入り
├── assets/fonts/
└── tests/
```

### 3-2. 仮想環境を作成

PowerShell でこのフォルダに移動して:

```powershell
cd C:\HIDAKARAanalytics
python -m venv .venv
```

→ `.venv` フォルダができる（10秒程度）

### 3-3. 依存パッケージをインストール

```powershell
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
```

→ Streamlit / DuckDB / pandas など一式がインストールされる（数分かかる）

---

## Phase 4: 動作確認（localhost）

### 4-1. 起動

```powershell
.\start_server.bat
```

または

```powershell
.\start_server.ps1
```

ターミナルに次のような表示が出れば成功:

```
=== このPCのLAN IPアドレス ===
IPAddress       InterfaceAlias
---------       --------------
192.168.X.XX    Wi-Fi (or Ethernet)

HIDAKARAanalytics を起動します...
You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
  Network URL: http://192.168.X.XX:8501
```

→ **表示された LAN IP アドレスをメモ**（社内共有用 URL に使う）

### 4-2. ブラウザで確認

このサーバー PC 自身のブラウザで:

```
http://localhost:8501
```

ダッシュボードが開いて、サイドバーに「本巣市 / 白川村 / 飛騨市」が表示されればOK。

---

## Phase 5: ファイアウォール開放（LAN 公開）

他の PC からアクセスできるようにします。

### 5-1. 管理者権限の PowerShell を開く

**スタート** → 「PowerShell」と検索 → **右クリック → 「管理者として実行」**

### 5-2. ファイアウォールルール追加

開いたウィンドウに次を貼り付けて Enter:

```powershell
New-NetFirewallRule -DisplayName "HIDAKARAanalytics (port 8501)" `
  -Direction Inbound -LocalPort 8501 -Protocol TCP `
  -Action Allow -Profile Private,Domain
```

→ ルールが追加される。閉じて OK。

### 5-3. 他の PC からアクセステスト

同じ社内 LAN の別の PC（スマホでも可）のブラウザで:

```
http://<サーバー PC の IP アドレス>:8501
```

例: `http://192.168.10.20:8501`

→ ダッシュボードが見られれば成功！

---

## Phase 6: 自動起動の設定（推奨）

サーバー PC を再起動した時、自動的に Streamlit が起動するように設定。

### 6-1. スタートアップフォルダを開く

スタート → ファイル名を指定して実行 (`Win + R`) → 入力:

```
shell:startup
```

→ スタートアップフォルダが開く

### 6-2. ショートカットを作成

`C:\HIDAKARAanalytics\start_server.bat` を **右クリックドラッグ** で スタートアップフォルダに持っていき → **「ショートカットをここに作成」** を選ぶ

→ ログイン時に自動でサーバーが起動するようになる

### 6-3. PC を再起動して確認

サーバー PC を再起動 → ログイン後に黒い PowerShell ウィンドウが自動的に開いて Streamlit が起動すれば OK。

---

## Phase 7: 社内に URL を共有

社内の関係者に以下を伝える:

```
HIDAKARAanalytics ダッシュボードURL:
http://<サーバー PC IP>:8501

【利用条件】
- 同じ社内 Wi-Fi / LAN に接続中であること
- 業務時間中（9:00〜18:00）のみアクセス可能
- スマホでも閲覧可能
```

---

## 🔄 日々の運用

### CSV データ取込（社員作業）

1. ブラウザで `http://<サーバー IP>:8501` を開く
2. サイドバーの「取込先の自治体」で **正しい自治体を選択**
3. 寄附情報 CSV と配送情報 CSV をアップロード
4. 「📥 取込実行」ボタン
5. 完了メッセージを確認

### 取込ミスのリカバリ

1. 「📜 取込履歴」タブを開く
2. 間違った取込の行で「🗑 取消」ボタン
3. 「✓ 確定」で削除
4. 正しい自治体を選び直して再取込

### バックアップ（推奨：週1）

`C:\HIDAKARAanalytics\data\warehouse.duckdb` を別の場所にコピー保管:
- USB メモリ
- ネットワーク共有フォルダ
- OneDrive

復旧時はこのファイルを元の場所に戻すだけ。

---

## ❓ トラブルシューティング

### Q. ブラウザで「このサイトにアクセスできません」と出る
**A.** 以下を確認:
1. サーバー PC で Streamlit が動作しているか（黒いウィンドウが開いているか）
2. アクセスしている PC が同じ LAN にあるか
3. ファイアウォール (Phase 5) が設定済みか
4. IP アドレスが正しいか（サーバー PC で `ipconfig` で確認）

### Q. サーバー PC を再起動したら使えなくなった
**A.** スタートアップ自動起動 (Phase 6) が未設定。手動で `start_server.bat` を起動してください。または Phase 6 を実施。

### Q. CSV 取込時に「フォーマットを判定できません」エラー
**A.** 既知の 3 フォーマット（format_a / format_b / format_c）に該当しない新しい形式です。CLAUDE.md の「CSV フォーマット」セクション参照。新フォーマットは `src/ingest.py` への追加対応が必要。

### Q. パッケージ作成 (Phase 1) でエラー
**A.** Streamlit が動作中だと DB ファイルロックで失敗します。Phase 1-1 のコマンドで停止してから再試行。

### Q. データを完全に消して再取込したい
**A.** `C:\HIDAKARAanalytics\data\warehouse.duckdb` を削除して `start_server.bat` を再起動。空の DB が再生成される。自治体マスタも消えるので、設定タブから自治体追加 → 取込 と進める。

---

## 🚀 将来: 社外アクセス対応（Cloudflare Tunnel）

別途、リモート・出張先からもアクセス可能にしたい場合は Cloudflare Tunnel + Cloudflare Access で実現可能（月額 0 円、50 ユーザーまで）。CLAUDE.md の「デプロイ計画」セクション参照、または別途相談。
