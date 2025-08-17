#!/usr/bin/env python3
import sqlite3

# === You set these ===
DATABASE_PATH = "/home/eborcherding/Documents/florida/florida_v3/dbs/test_range_12s.db"
TABLE_TO_DELETE = "refined_annotations"
# =====================

def quote_ident(name: str) -> str:
    # Safely quote an identifier for SQLite
    return '"' + name.replace('"', '""') + '"'

def drop_table_or_view(cur, name: str):
    row = cur.execute(
        """
        SELECT type, name
        FROM sqlite_master
        WHERE lower(name) = lower(?) AND type IN ('table','view')
        LIMIT 1
        """,
        (name,),
    ).fetchone()

    if not row:
        print(f"'{name}' not found as a table or view; skipping drop.")
        return

    obj_type, obj_name = row  # 'table' or 'view'
    ident = quote_ident(obj_name)
    cur.execute(f"DROP {obj_type.upper()} IF EXISTS {ident}")
    print(f"Dropped {obj_type} '{obj_name}'.")

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    # Enforce FK constraints; DROP will fail if other tables depend on it (safer).
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        with conn:  # transaction
            cur = conn.cursor()
            drop_table_or_view(cur, TABLE_TO_DELETE)

            cur.execute("UPDATE events SET status = 'manual';")
            print(f"Updated {cur.rowcount} row(s) in 'events.status' to 'manual'.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
