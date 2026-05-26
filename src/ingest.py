"""CSV ingestion with format auto-detection and multi-municipality support.

Supported shipment-CSV formats:
- format_a: 本巣市 layout (9 cols, 配送No. あり)
- format_b: 白川村 実績用 layout (9 cols, 配送No. なし, 寄附金額カラムあり)
- format_c: 飛騨市 layout (7 cols, 配送No. あり, 謝礼品番号・寄附方法なし)

Supported donation-CSV formats:
- standard: 4 cols (入金日, 寄附方法, 寄附金額, 謝礼品)
- no_product: 4 cols (受付日, 寄附方法, 入金日, 寄附金額) ※謝礼品なし、飛騨市
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Union

import duckdb
import pandas as pd


# Format A: classic shipment CSV with 配送No. (e.g., 本巣市)
SHIPMENT_FORMAT_A = {
    "configured_columns": {
        "配送No.": "shipment_no",
        "謝礼品カテゴリ": "category",
        "謝礼品番号": "product_code",
        "謝礼品": "product_name",
        "事業者": "vendor",
        "寄附設定金額": "donation_amount",
        "寄附方法": "channel",
        "寄附 入金日(収納日)": "payment_date",
        "謝礼品価格": "product_price",
    },
    "required": {"配送No.", "謝礼品カテゴリ", "謝礼品番号", "謝礼品", "事業者",
                 "寄附設定金額", "寄附方法", "寄附 入金日(収納日)", "謝礼品価格"},
    "has_shipment_no": True,
}

# Format B: 白川村 実績用 layout (no 配送No., has both 寄附金額 and 寄附設定金額)
# We treat 寄附設定金額 as donation_amount per row (consistent with format A's
# revenue treatment). 寄附金額 is the donor-level total and stored as a separate
# column for reference if needed later.
SHIPMENT_FORMAT_B = {
    "configured_columns": {
        "謝礼品カテゴリ": "category",
        "謝礼品番号": "product_code",
        "謝礼品": "product_name",
        "事業者": "vendor",
        "寄附設定金額": "donation_amount",
        "寄附方法": "channel",
        "寄附 入金日(収納日)": "payment_date",
        "謝礼品価格": "product_price",
    },
    "required": {"謝礼品カテゴリ", "謝礼品番号", "謝礼品", "事業者",
                 "寄附設定金額", "寄附方法", "寄附 入金日(収納日)", "謝礼品価格",
                 "寄附金額"},   # 寄附金額 is the discriminator vs format A
    "has_shipment_no": False,
}

# Format C: 飛騨市 layout (7 cols, 配送No. あり, 謝礼品番号・寄附方法なし)
# Discriminator: has 配送No. AND 事業者, but no 謝礼品番号 column.
SHIPMENT_FORMAT_C = {
    "configured_columns": {
        "配送No.": "shipment_no",
        "事業者": "vendor",
        "謝礼品": "product_name",
        "謝礼品カテゴリ": "category",
        "寄附 入金日(収納日)": "payment_date",
        "寄附設定金額": "donation_amount",
        "謝礼品価格": "product_price",
    },
    "required": {"配送No.", "事業者", "謝礼品", "謝礼品カテゴリ",
                 "寄附 入金日(収納日)", "寄附設定金額", "謝礼品価格"},
    "has_shipment_no": True,
}


# Donation standard format: 4 cols, has 謝礼品 (本巣市 / 白川村)
DONATION_FORMAT_STANDARD = {
    "configured_columns": {
        "入金日(収納日)": "payment_date",
        "寄附方法": "channel",
        "寄附金額": "donation_amount",
        "謝礼品": "product_name",
    },
    "required": {"入金日(収納日)", "寄附方法", "寄附金額", "謝礼品"},
    "has_product_name": True,
}

# Donation no-product format: 4 cols, no 謝礼品 (飛騨市)
# 「受付日」が discriminator
DONATION_FORMAT_NO_PRODUCT = {
    "configured_columns": {
        "入金日(収納日)": "payment_date",
        "寄附方法": "channel",
        "寄附金額": "donation_amount",
    },
    "required": {"入金日(収納日)", "寄附方法", "寄附金額", "受付日"},
    "has_product_name": False,
}

# Backward-compat alias for callers that still import DONATION_COLUMNS
DONATION_COLUMNS = DONATION_FORMAT_STANDARD["configured_columns"]

DATE_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


@dataclass
class IngestResult:
    file_name: str
    file_type: str
    file_format: str
    municipality_id: int
    municipality_name: str
    rows_inserted: int
    rows_skipped: int

    def summary(self) -> str:
        return (
            f"[{self.municipality_name}] {self.file_name} [{self.file_type}/{self.file_format}]: "
            f"新規 {self.rows_inserted} 件 / 重複スキップ {self.rows_skipped} 件"
        )


def _parse_japanese_date(value: object) -> pd.Timestamp | None:
    if pd.isna(value):
        return None
    s = str(value).strip()
    m = DATE_PATTERN.match(s)
    if not m:
        try:
            return pd.to_datetime(s).normalize()
        except Exception:
            return None
    y, mo, d = m.groups()
    return pd.Timestamp(int(y), int(mo), int(d))


def _read_csv(source: Union[str, Path, IO]) -> pd.DataFrame:
    encodings = ["cp932", "utf-8-sig", "utf-8"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"CSVのエンコーディングを判定できませんでした: {last_err}")


def detect_file_type(df: pd.DataFrame) -> tuple[str, str]:
    """Return (file_type, format_name).

    file_type: 'shipment' | 'donation'
    format_name: 'format_a' | 'format_b' | 'format_c' (shipment); 'standard' | 'no_product' (donation)
    """
    cols = set(df.columns)
    # Shipment formats first (more discriminating, longer required sets)
    if SHIPMENT_FORMAT_A["required"] <= cols:
        return "shipment", "format_a"
    if SHIPMENT_FORMAT_B["required"] <= cols:
        return "shipment", "format_b"
    if SHIPMENT_FORMAT_C["required"] <= cols:
        return "shipment", "format_c"
    # Donation formats
    if DONATION_FORMAT_STANDARD["required"] <= cols:
        return "donation", "standard"
    if DONATION_FORMAT_NO_PRODUCT["required"] <= cols:
        return "donation", "no_product"
    raise ValueError(
        "CSVのカラム構成を判定できませんでした。配送情報CSVまたは寄附情報CSVを指定してください。"
        f" 検出カラム: {sorted(cols)}"
    )


def _to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "").str.strip(), errors="coerce"
    ).astype("Int64")


def _make_synthetic_shipment_no(row: pd.Series, municipality_id: int) -> str:
    parts = [
        str(municipality_id),
        str(row.get("payment_date")),
        str(row.get("product_code")),
        str(row.get("vendor")),
        str(row.get("donation_amount")),
        str(row.get("_seq")),
    ]
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"SYN_{h}"


_SHIPMENT_SPECS = {
    "format_a": SHIPMENT_FORMAT_A,
    "format_b": SHIPMENT_FORMAT_B,
    "format_c": SHIPMENT_FORMAT_C,
}

_SHIPMENT_STANDARD_COLS = [
    "shipment_no", "category", "product_code", "product_name",
    "vendor", "donation_amount", "channel", "payment_date", "product_price",
]


def _normalize_shipment_df(
    df: pd.DataFrame, municipality_id: int, format_name: str
) -> pd.DataFrame:
    spec = _SHIPMENT_SPECS.get(format_name)
    if spec is None:
        raise ValueError(f"未知の配送フォーマット: {format_name}")

    column_map = spec["configured_columns"]
    out = df.rename(columns=column_map)[list(column_map.values())].copy()

    # Fill in any missing standard columns with NA so downstream is uniform
    for col in _SHIPMENT_STANDARD_COLS:
        if col not in out.columns:
            out[col] = pd.NA

    out["payment_date"] = out["payment_date"].map(_parse_japanese_date)
    out["donation_amount"] = _to_int(out["donation_amount"])
    out["product_price"] = _to_int(out["product_price"])
    out["municipality_id"] = municipality_id

    if spec["has_shipment_no"]:
        out["shipment_no"] = out["shipment_no"].astype(str).str.strip()
    else:
        # Generate a reproducible synthetic shipment_no per row
        group_cols = ["payment_date", "product_code", "vendor", "donation_amount"]
        out["_seq"] = out.groupby(group_cols).cumcount() + 1
        out["shipment_no"] = out.apply(
            lambda r: _make_synthetic_shipment_no(r, municipality_id), axis=1
        )
        out = out.drop(columns=["_seq"])

    out = out[out["shipment_no"].str.len() > 0]
    return out


_DONATION_SPECS = {
    "standard": DONATION_FORMAT_STANDARD,
    "no_product": DONATION_FORMAT_NO_PRODUCT,
}


def _normalize_donation_df(
    df: pd.DataFrame, municipality_id: int, format_name: str = "standard"
) -> pd.DataFrame:
    spec = _DONATION_SPECS.get(format_name)
    if spec is None:
        raise ValueError(f"未知の寄附フォーマット: {format_name}")

    column_map = spec["configured_columns"]
    out = df.rename(columns=column_map)[list(column_map.values())].copy()

    # Ensure product_name column exists (NA if not provided by this format)
    if "product_name" not in out.columns:
        out["product_name"] = pd.NA

    out["payment_date"] = out["payment_date"].map(_parse_japanese_date)
    out["donation_amount"] = _to_int(out["donation_amount"])
    group_cols = ["payment_date", "channel", "donation_amount", "product_name"]
    out["_seq"] = out.groupby(group_cols, dropna=False).cumcount() + 1
    out["municipality_id"] = municipality_id
    out["composite_key"] = out.apply(_make_donation_key, axis=1)
    out = out.drop(columns=["_seq"])
    return out


def _make_donation_key(row: pd.Series) -> str:
    parts = [
        str(row.get("payment_date")),
        str(row.get("channel")),
        str(row.get("donation_amount")),
        str(row.get("product_name")),
        str(row.get("_seq")),
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _insert_shipments(
    conn: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    municipality_id: int,
    batch_ts: pd.Timestamp,
) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    existing = conn.execute(
        "SELECT shipment_no FROM shipments WHERE municipality_id = ?", [municipality_id]
    ).fetchdf()
    existing_set = set(existing["shipment_no"].astype(str)) if not existing.empty else set()
    new_df = df[~df["shipment_no"].isin(existing_set)].copy()
    new_df = new_df.drop_duplicates(subset=["shipment_no"])
    skipped = len(df) - len(new_df)
    if not new_df.empty:
        new_df["imported_at"] = batch_ts
        conn.register("_new_shipments", new_df)
        conn.execute(
            """
            INSERT INTO shipments
                (shipment_no, municipality_id, category, product_code, product_name,
                 vendor, donation_amount, channel, payment_date, product_price, imported_at)
            SELECT shipment_no, municipality_id, category, product_code, product_name,
                   vendor, donation_amount, channel, payment_date, product_price, imported_at
            FROM _new_shipments
            """
        )
        conn.unregister("_new_shipments")
    return len(new_df), skipped


def _insert_donations(
    conn: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    municipality_id: int,
    batch_ts: pd.Timestamp,
) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    existing = conn.execute(
        "SELECT composite_key FROM donations WHERE municipality_id = ?", [municipality_id]
    ).fetchdf()
    existing_set = set(existing["composite_key"]) if not existing.empty else set()
    new_df = df[~df["composite_key"].isin(existing_set)].copy()
    new_df = new_df.drop_duplicates(subset=["composite_key"])
    skipped = len(df) - len(new_df)
    if not new_df.empty:
        new_df["imported_at"] = batch_ts
        conn.register("_new_donations", new_df)
        conn.execute(
            """
            INSERT INTO donations
                (municipality_id, payment_date, channel, donation_amount, product_name, composite_key, imported_at)
            SELECT municipality_id, payment_date, channel, donation_amount, product_name, composite_key, imported_at
            FROM _new_donations
            """
        )
        conn.unregister("_new_donations")
    return len(new_df), skipped


def _log_import(
    conn: duckdb.DuckDBPyConnection,
    municipality_id: int,
    file_name: str,
    file_type: str,
    rows_inserted: int,
    rows_skipped: int,
    batch_ts: pd.Timestamp,
) -> int:
    """Insert an import_logs row using batch_ts and return its id."""
    conn.execute(
        """
        INSERT INTO import_logs
            (municipality_id, file_name, file_type, rows_inserted, rows_skipped, imported_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [municipality_id, file_name, file_type, rows_inserted, rows_skipped, batch_ts],
    )
    row = conn.execute(
        """SELECT id FROM import_logs
           WHERE municipality_id = ? AND file_name = ? AND imported_at = ?
           ORDER BY id DESC LIMIT 1""",
        [municipality_id, file_name, batch_ts],
    ).fetchone()
    return int(row[0]) if row else 0


def _get_municipality_name(conn: duckdb.DuckDBPyConnection, municipality_id: int) -> str:
    row = conn.execute(
        "SELECT name FROM municipalities WHERE id = ?", [municipality_id]
    ).fetchone()
    return row[0] if row else f"(id={municipality_id})"


def ingest_csv(
    conn: duckdb.DuckDBPyConnection,
    source: Union[str, Path, IO],
    municipality_id: int,
    file_name: str | None = None,
) -> IngestResult:
    """Ingest a single CSV file for a given municipality (auto-detects format)."""
    if file_name is None:
        file_name = getattr(source, "name", str(source))
        file_name = Path(file_name).name

    df = _read_csv(source)
    file_type, file_format = detect_file_type(df)

    # Shared batch timestamp so the inserted rows and the import_log row align.
    # This is what enables "this import を取消" later: we DELETE rows whose
    # imported_at matches the log's imported_at.
    batch_ts = pd.Timestamp.now()

    if file_type == "shipment":
        normalized = _normalize_shipment_df(df, municipality_id, file_format)
        inserted, skipped = _insert_shipments(conn, normalized, municipality_id, batch_ts)
    else:
        normalized = _normalize_donation_df(df, municipality_id, file_format)
        inserted, skipped = _insert_donations(conn, normalized, municipality_id, batch_ts)

    _log_import(conn, municipality_id, file_name, file_type, inserted, skipped, batch_ts)
    name = _get_municipality_name(conn, municipality_id)
    return IngestResult(
        file_name=file_name,
        file_type=file_type,
        file_format=file_format,
        municipality_id=municipality_id,
        municipality_name=name,
        rows_inserted=inserted,
        rows_skipped=skipped,
    )


def get_import_history(conn: duckdb.DuckDBPyConnection, limit: int = 50) -> pd.DataFrame:
    return conn.execute(
        f"""
        SELECT il.id, m.name AS 自治体, il.file_name, il.file_type,
               il.rows_inserted, il.rows_skipped, il.imported_at
        FROM import_logs il
        LEFT JOIN municipalities m ON m.id = il.municipality_id
        ORDER BY il.id DESC
        LIMIT {int(limit)}
        """
    ).fetchdf()


def delete_import(conn: duckdb.DuckDBPyConnection, import_log_id: int) -> dict:
    """Delete all rows that were inserted by a specific import_log.

    Returns a dict reporting how many rows were removed. Works by matching
    (municipality_id, imported_at) between the log and the data row, which is
    why ingest_csv shares a batch_ts across the log and the inserted rows.
    """
    log = conn.execute(
        """SELECT id, municipality_id, file_name, file_type, imported_at
           FROM import_logs WHERE id = ?""",
        [import_log_id],
    ).fetchone()
    if log is None:
        return {"found": False, "removed_rows": 0, "removed_log": False}

    log_id, muni_id, file_name, file_type, imported_at = log

    if file_type == "shipment":
        before = conn.execute(
            """SELECT COUNT(*) FROM shipments
               WHERE municipality_id = ? AND imported_at = ?""",
            [muni_id, imported_at],
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM shipments WHERE municipality_id = ? AND imported_at = ?",
            [muni_id, imported_at],
        )
        removed = int(before)
    elif file_type == "donation":
        before = conn.execute(
            """SELECT COUNT(*) FROM donations
               WHERE municipality_id = ? AND imported_at = ?""",
            [muni_id, imported_at],
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM donations WHERE municipality_id = ? AND imported_at = ?",
            [muni_id, imported_at],
        )
        removed = int(before)
    else:
        removed = 0

    conn.execute("DELETE FROM import_logs WHERE id = ?", [log_id])
    return {
        "found": True,
        "removed_rows": removed,
        "removed_log": True,
        "file_name": file_name,
        "file_type": file_type,
        "imported_at": imported_at,
    }


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> int:
    """Run a single-value query defensively. Returns 0 if the result is unexpected."""
    try:
        row = conn.execute(sql, params or []).fetchone()
    except Exception:
        return 0
    if row is None:
        return 0
    val = row[0]
    if val is None:
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def get_table_counts(
    conn: duckdb.DuckDBPyConnection,
    municipality_id: int | None = None,
) -> dict[str, int]:
    if municipality_id is None:
        return {
            "shipments": _scalar(conn, "SELECT COUNT(*) FROM shipments"),
            "donations": _scalar(conn, "SELECT COUNT(*) FROM donations"),
        }
    return {
        "shipments": _scalar(
            conn, "SELECT COUNT(*) FROM shipments WHERE municipality_id = ?", [municipality_id]
        ),
        "donations": _scalar(
            conn, "SELECT COUNT(*) FROM donations WHERE municipality_id = ?", [municipality_id]
        ),
    }


def get_counts_per_municipality(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute(
        """
        SELECT m.id, m.name, m.code, m.active,
               COALESCE(s.cnt, 0) AS shipments,
               COALESCE(d.cnt, 0) AS donations
        FROM municipalities m
        LEFT JOIN (SELECT municipality_id, COUNT(*) AS cnt FROM shipments GROUP BY 1) s
          ON s.municipality_id = m.id
        LEFT JOIN (SELECT municipality_id, COUNT(*) AS cnt FROM donations GROUP BY 1) d
          ON d.municipality_id = m.id
        ORDER BY m.id
        """
    ).fetchdf()
