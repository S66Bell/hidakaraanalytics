# HIDAKARAanalytics

ふるさと納税の日次データ分析ダッシュボード（マルチ自治体対応）。

## セットアップ

```powershell
# 仮想環境作成（推奨）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 依存関係インストール
pip install -r requirements.txt

# 起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開く。

## 使い方

1. ⚙️ 設定タブから自治体を追加（既に本巣市・白川村が登録済み）
2. サイドバーで取込先の自治体を選択
3. 寄附情報CSV・配送情報CSVをアップロード
4. 「📥 取込実行」ボタンをクリック
5. 各タブから分析を確認、🏛️ 自治体比較タブで本巣市 vs 白川村 のサイドバイサイド比較

## ディレクトリ構成

```
motosuanalytics/        ← フォルダ名（プロジェクトの実体）
├── app.py              # Streamlitエントリ
├── requirements.txt
├── data/
│   ├── raw/            # 受領した生CSV（バックアップ）
│   ├── warehouse.duckdb # 集約DB
│   └── reports/        # 出力レポート（Excel/PDF）
├── src/
│   ├── db.py           # DuckDB接続・スキーマ・自治体CRUD
│   ├── ingest.py       # CSV取込（フォーマット自動検出: format_a/format_b）
│   ├── analytics.py    # 集計ロジック（自治体フィルタ対応）
│   ├── reports.py      # Excel/PDF レポート生成
│   ├── format_utils.py # 共通フォーマッタ
│   └── views/
│       ├── summary.py
│       ├── trend.py
│       ├── ranking.py
│       ├── vendor.py
│       ├── channel.py
│       ├── comparison.py  # 🆚 自治体比較タブ
│       └── settings.py    # ⚙️ 設定タブ
└── assets/
    └── fonts/          # 日本語PDF用フォント (IPAex Gothic/Mincho)
```

## データ定義（用語）

| 用語 | 意味 |
|---|---|
| 寄付金額 | 寄附者が支払った額（受取総額）= SUM(donation_amount) |
| 謝礼品価格 | 自治体が支払う商品代金 = SUM(product_price) |
| 経費率 | 謝礼品価格 ÷ 寄付金額 |

## 対応CSVフォーマット

- **format_a**: 配送No.あり、`寄附設定金額` を per-row 金額として使用（本巣市など）
- **format_b**: 配送No.なし、`寄附金額`（総額）と `寄附設定金額`（per-row）の両方あり。`寄附設定金額` を金額として使用（白川村など）
- 検出は自動。CSV文字コード: Shift-JIS (cp932) 想定
