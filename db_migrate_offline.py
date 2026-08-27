"""Addite offline-monitoring columns to device_list (safe, idempotent)."""
import os
import sqlite3

DB = os.environ.get("LCC_DB", "/home/administrator/lcc-tools/data/device_cache.db")


def _ensure_columns(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(device_list)").fetchall()}
    adds = {
        "offline_monitor": "INTEGER DEFAULT 0",
        "offline_since": "REAL",
        "first_alerted": "INTEGER DEFAULT 0",
    }
    for name, ddl in adds.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE device_list ADD COLUMN {name} {ddl}")
            print("Spalte hinzugefuegt:", name)
        else:
            print("Spalte bereits vorhanden:", name)


def main():
    conn = sqlite3.connect(DB)
    _ensure_columns(conn)
    conn.commit()
    rows = conn.execute("SELECT COUNT(*) FROM device_list").fetchone()[0]
    print("device_list rows:", rows)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(device_list)").fetchall()]
    print("alle Spalten:", cols)
    conn.close()


if __name__ == "__main__":
    main()