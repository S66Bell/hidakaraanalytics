"""DuckDB connection and schema management (multi-municipality)."""
from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"

DEFAULT_MUNICIPALITY_NAME = "自治体A"
DEFAULT_MUNICIPALITY_CODE = "city_a"


SEQUENCES_DDL = """
CREATE SEQUENCE IF NOT EXISTS donation_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS import_log_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS municipality_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS vendor_alias_id_seq START 1;
"""

MASTER_TABLES_DDL = """
CREATE TABLE IF NOT EXISTS municipalities (
    id              INTEGER PRIMARY KEY DEFAULT nextval('municipality_id_seq'),
    name            VARCHAR UNIQUE,
    code            VARCHAR UNIQUE,
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vendor_aliases (
    id              INTEGER PRIMARY KEY DEFAULT nextval('vendor_alias_id_seq'),
    canonical_name  VARCHAR,
    alias_name      VARCHAR,
    municipality_id INTEGER,
    UNIQUE(canonical_name, alias_name, municipality_id)
);
"""

SHIPMENTS_DDL = """
CREATE TABLE IF NOT EXISTS shipments (
    shipment_no     VARCHAR,
    municipality_id INTEGER,
    category        VARCHAR,
    product_code    VARCHAR,
    product_name    VARCHAR,
    vendor          VARCHAR,
    donation_amount INTEGER,
    channel         VARCHAR,
    payment_date    DATE,
    product_price   INTEGER,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (municipality_id, shipment_no)
);
"""

DONATIONS_DDL = """
CREATE TABLE IF NOT EXISTS donations (
    donation_id     INTEGER PRIMARY KEY DEFAULT nextval('donation_id_seq'),
    municipality_id INTEGER,
    payment_date    DATE,
    channel         VARCHAR,
    donation_amount INTEGER,
    product_name    VARCHAR,
    composite_key   VARCHAR,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(municipality_id, composite_key)
);
"""

IMPORT_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS import_logs (
    id              INTEGER PRIMARY KEY DEFAULT nextval('import_log_id_seq'),
    municipality_id INTEGER,
    file_name       VARCHAR,
    file_type       VARCHAR,
    rows_inserted   INTEGER,
    rows_skipped    INTEGER,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_shipments_payment_date ON shipments(payment_date);
CREATE INDEX IF NOT EXISTS idx_shipments_vendor ON shipments(vendor);
CREATE INDEX IF NOT EXISTS idx_shipments_category ON shipments(category);
CREATE INDEX IF NOT EXISTS idx_shipments_channel ON shipments(channel);
CREATE INDEX IF NOT EXISTS idx_shipments_municipality ON shipments(municipality_id);
CREATE INDEX IF NOT EXISTS idx_donations_payment_date ON donations(payment_date);
CREATE INDEX IF NOT EXISTS idx_donations_municipality ON donations(municipality_id);
CREATE INDEX IF NOT EXISTS idx_vendor_aliases_alias ON vendor_aliases(alias_name);
"""


# ---------- Connection ----------

def get_connection(db_path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    return conn


# ---------- Schema introspection helpers ----------

def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchone()
    return bool(row and row[0])


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {row[1] for row in rows}


# ---------- Migration (handles upgrade from single-tenant schema) ----------

def _ensure_default_municipality(conn: duckdb.DuckDBPyConnection) -> int:
    existing = conn.execute(
        "SELECT id FROM municipalities WHERE code = ?", [DEFAULT_MUNICIPALITY_CODE]
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    conn.execute(
        "INSERT INTO municipalities (name, code, active) VALUES (?, ?, true)",
        [DEFAULT_MUNICIPALITY_NAME, DEFAULT_MUNICIPALITY_CODE],
    )
    row = conn.execute(
        "SELECT id FROM municipalities WHERE code = ?", [DEFAULT_MUNICIPALITY_CODE]
    ).fetchone()
    return int(row[0])


def _migrate_shipments(conn: duckdb.DuckDBPyConnection, default_id: int) -> int:
    """Rebuild shipments table with multi-municipality schema. Returns rows migrated."""
    cols = _table_columns(conn, "shipments")
    if not cols:
        # Fresh: just create
        conn.execute(SHIPMENTS_DDL)
        return 0
    if "municipality_id" in cols:
        return 0  # Already migrated

    rebuilt_ddl = SHIPMENTS_DDL.replace(
        "CREATE TABLE IF NOT EXISTS shipments",
        "CREATE TABLE shipments_new",
    )
    conn.execute(rebuilt_ddl)
    conn.execute(
        """
        INSERT INTO shipments_new
            (shipment_no, municipality_id, category, product_code, product_name,
             vendor, donation_amount, channel, payment_date, product_price, imported_at)
        SELECT shipment_no, ?, category, product_code, product_name,
               vendor, donation_amount, channel, payment_date, product_price, imported_at
        FROM shipments
        """,
        [default_id],
    )
    moved = conn.execute("SELECT COUNT(*) FROM shipments_new").fetchone()[0]
    conn.execute("DROP TABLE shipments")
    conn.execute("ALTER TABLE shipments_new RENAME TO shipments")
    return int(moved)


def _migrate_donations(conn: duckdb.DuckDBPyConnection, default_id: int) -> int:
    cols = _table_columns(conn, "donations")
    if not cols:
        conn.execute(DONATIONS_DDL)
        return 0
    if "municipality_id" in cols:
        return 0

    rebuilt_ddl = DONATIONS_DDL.replace(
        "CREATE TABLE IF NOT EXISTS donations",
        "CREATE TABLE donations_new",
    )
    conn.execute(rebuilt_ddl)
    conn.execute(
        """
        INSERT INTO donations_new
            (donation_id, municipality_id, payment_date, channel, donation_amount,
             product_name, composite_key, imported_at)
        SELECT donation_id, ?, payment_date, channel, donation_amount,
               product_name, composite_key, imported_at
        FROM donations
        """,
        [default_id],
    )
    moved = conn.execute("SELECT COUNT(*) FROM donations_new").fetchone()[0]
    conn.execute("DROP TABLE donations")
    conn.execute("ALTER TABLE donations_new RENAME TO donations")
    return int(moved)


def _migrate_import_logs(conn: duckdb.DuckDBPyConnection, default_id: int) -> int:
    cols = _table_columns(conn, "import_logs")
    if not cols:
        conn.execute(IMPORT_LOGS_DDL)
        return 0
    if "municipality_id" in cols:
        return 0

    rebuilt_ddl = IMPORT_LOGS_DDL.replace(
        "CREATE TABLE IF NOT EXISTS import_logs",
        "CREATE TABLE import_logs_new",
    )
    conn.execute(rebuilt_ddl)
    conn.execute(
        """
        INSERT INTO import_logs_new
            (id, municipality_id, file_name, file_type, rows_inserted, rows_skipped, imported_at)
        SELECT id, ?, file_name, file_type, rows_inserted, rows_skipped, imported_at
        FROM import_logs
        """,
        [default_id],
    )
    moved = conn.execute("SELECT COUNT(*) FROM import_logs_new").fetchone()[0]
    conn.execute("DROP TABLE import_logs")
    conn.execute("ALTER TABLE import_logs_new RENAME TO import_logs")
    return int(moved)


def initialize_schema(conn: duckdb.DuckDBPyConnection) -> dict:
    """Create all tables / indexes and migrate any legacy single-tenant tables.

    Returns a report describing what was changed.
    """
    report = {"created_default_municipality": False, "migrated": {}}

    conn.execute(SEQUENCES_DDL)
    conn.execute(MASTER_TABLES_DDL)

    needs_legacy_migration = (
        _table_exists(conn, "shipments")
        and "municipality_id" not in _table_columns(conn, "shipments")
    ) or (
        _table_exists(conn, "donations")
        and "municipality_id" not in _table_columns(conn, "donations")
    ) or (
        _table_exists(conn, "import_logs")
        and "municipality_id" not in _table_columns(conn, "import_logs")
    )

    default_id = None
    if needs_legacy_migration:
        if conn.execute("SELECT COUNT(*) FROM municipalities").fetchone()[0] == 0:
            report["created_default_municipality"] = True
        default_id = _ensure_default_municipality(conn)

    report["migrated"]["shipments"] = _migrate_shipments(conn, default_id or 0)
    report["migrated"]["donations"] = _migrate_donations(conn, default_id or 0)
    report["migrated"]["import_logs"] = _migrate_import_logs(conn, default_id or 0)

    conn.execute(INDEXES_DDL)
    return report


def ensure_db(db_path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the DB, ensure the schema exists, and run idempotent migrations."""
    conn = get_connection(db_path)
    initialize_schema(conn)
    return conn


# ---------- Municipality CRUD ----------

def list_municipalities(conn: duckdb.DuckDBPyConnection, active_only: bool = False) -> list[dict]:
    sql = "SELECT id, name, code, active, created_at FROM municipalities"
    if active_only:
        sql += " WHERE active = true"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    return [
        {"id": r[0], "name": r[1], "code": r[2], "active": r[3], "created_at": r[4]}
        for r in rows
    ]


def get_municipality(conn: duckdb.DuckDBPyConnection, municipality_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, code, active, created_at FROM municipalities WHERE id = ?",
        [municipality_id],
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "code": row[2], "active": row[3], "created_at": row[4]}


def add_municipality(conn: duckdb.DuckDBPyConnection, name: str, code: str) -> int:
    conn.execute(
        "INSERT INTO municipalities (name, code, active) VALUES (?, ?, true)",
        [name, code],
    )
    row = conn.execute("SELECT id FROM municipalities WHERE code = ?", [code]).fetchone()
    return int(row[0])


def update_municipality(
    conn: duckdb.DuckDBPyConnection,
    municipality_id: int,
    name: str | None = None,
    code: str | None = None,
    active: bool | None = None,
) -> None:
    sets = []
    params: list = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if code is not None:
        sets.append("code = ?")
        params.append(code)
    if active is not None:
        sets.append("active = ?")
        params.append(active)
    if not sets:
        return
    params.append(municipality_id)
    conn.execute(f"UPDATE municipalities SET {', '.join(sets)} WHERE id = ?", params)


def delete_municipality(conn: duckdb.DuckDBPyConnection, municipality_id: int) -> dict:
    """Delete a municipality and all its data. Returns counts deleted."""
    sn = conn.execute(
        "SELECT COUNT(*) FROM shipments WHERE municipality_id = ?", [municipality_id]
    ).fetchone()[0]
    dn = conn.execute(
        "SELECT COUNT(*) FROM donations WHERE municipality_id = ?", [municipality_id]
    ).fetchone()[0]
    ln = conn.execute(
        "SELECT COUNT(*) FROM import_logs WHERE municipality_id = ?", [municipality_id]
    ).fetchone()[0]
    conn.execute("DELETE FROM shipments WHERE municipality_id = ?", [municipality_id])
    conn.execute("DELETE FROM donations WHERE municipality_id = ?", [municipality_id])
    conn.execute("DELETE FROM import_logs WHERE municipality_id = ?", [municipality_id])
    conn.execute("DELETE FROM vendor_aliases WHERE municipality_id = ?", [municipality_id])
    conn.execute("DELETE FROM municipalities WHERE id = ?", [municipality_id])
    return {"shipments": sn, "donations": dn, "import_logs": ln}


# ---------- Vendor alias CRUD ----------

def list_vendor_aliases(
    conn: duckdb.DuckDBPyConnection,
    municipality_id: int | None = None,
) -> list[dict]:
    if municipality_id is None:
        rows = conn.execute(
            "SELECT id, canonical_name, alias_name, municipality_id FROM vendor_aliases ORDER BY canonical_name"
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, canonical_name, alias_name, municipality_id FROM vendor_aliases
               WHERE municipality_id IS NULL OR municipality_id = ?
               ORDER BY canonical_name""",
            [municipality_id],
        ).fetchall()
    return [
        {"id": r[0], "canonical_name": r[1], "alias_name": r[2], "municipality_id": r[3]}
        for r in rows
    ]


def add_vendor_alias(
    conn: duckdb.DuckDBPyConnection,
    canonical_name: str,
    alias_name: str,
    municipality_id: int | None = None,
) -> int:
    conn.execute(
        "INSERT INTO vendor_aliases (canonical_name, alias_name, municipality_id) VALUES (?, ?, ?)",
        [canonical_name, alias_name, municipality_id],
    )
    row = conn.execute(
        """SELECT id FROM vendor_aliases
           WHERE canonical_name = ? AND alias_name = ?
             AND (municipality_id IS NOT DISTINCT FROM ?)""",
        [canonical_name, alias_name, municipality_id],
    ).fetchone()
    return int(row[0]) if row else 0


def delete_vendor_alias(conn: duckdb.DuckDBPyConnection, alias_id: int) -> None:
    conn.execute("DELETE FROM vendor_aliases WHERE id = ?", [alias_id])


# ---------- SQL helper for resolving vendor through alias table ----------

VENDOR_RESOLVE_SQL = """
COALESCE(
    (SELECT canonical_name FROM vendor_aliases va
       WHERE va.alias_name = s.vendor
         AND (va.municipality_id IS NULL OR va.municipality_id = s.municipality_id)
       LIMIT 1),
    s.vendor
)
"""
