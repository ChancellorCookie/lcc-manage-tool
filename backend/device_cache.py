"""SQLite cache for OPC-UA device properties (ComponentName, HierarchicalLocation)."""

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "device_cache.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_cache (
            serial TEXT PRIMARY KEY,
            component_name TEXT,
            hierarchical_location TEXT,
            device_class TEXT,
            last_updated REAL
        )
    """)
    conn.commit()
    return conn


def get_cached(serial: str) -> dict | None:
    """Get cached properties for a device serial number."""
    conn = _get_db()
    row = conn.execute(
        "SELECT component_name, hierarchical_location, device_class, last_updated FROM device_cache WHERE serial = ?",
        (serial,),
    ).fetchone()
    conn.close()
    if row:
        return {
            "componentName": row[0],
            "hierarchicalLocation": row[1],
            "deviceClass": row[2],
            "lastUpdated": row[3],
        }
    return None


def set_cached(serial: str, component_name: str | None = None,
               hierarchical_location: str | None = None,
               device_class: str | None = None):
    """Update cache for a device."""
    conn = _get_db()
    conn.execute("""
        INSERT INTO device_cache (serial, component_name, hierarchical_location, device_class, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(serial) DO UPDATE SET
            component_name = COALESCE(excluded.component_name, component_name),
            hierarchical_location = COALESCE(excluded.hierarchical_location, hierarchical_location),
            device_class = COALESCE(excluded.device_class, device_class),
            last_updated = excluded.last_updated
    """, (serial, component_name, hierarchical_location, device_class, time.time()))
    conn.commit()
    conn.close()


def get_all_cached() -> list[dict]:
    """Get all cached entries."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT serial, component_name, hierarchical_location, device_class, last_updated FROM device_cache ORDER BY serial"
    ).fetchall()
    conn.close()
    return [
        {
            "serial": r[0],
            "componentName": r[1],
            "hierarchicalLocation": r[2],
            "deviceClass": r[3],
            "lastUpdated": r[4],
        }
        for r in rows
    ]
