"""Quick DB inspection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, get_table_counts


conn = ensure_db()
print("Tables:")
for row in conn.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
).fetchall():
    print(" ", row[0])

print()
print("Shipments count:", conn.execute("SELECT COUNT(*) FROM shipments").fetchone())
print("Donations count:", conn.execute("SELECT COUNT(*) FROM donations").fetchone())
print()
print("Per-municipality:")
print(get_counts_per_municipality(conn).to_string(index=False))
print()
print("get_table_counts() result:", get_table_counts(conn))
conn.close()
