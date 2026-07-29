"""SQLite cache for OPC-UA device properties and device list."""

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_list (
            serial TEXT PRIMARY KEY,
            name TEXT,
            node_id TEXT,
            component_name TEXT,
            online INTEGER DEFAULT -1,
            last_seen REAL DEFAULT 0,
            last_updated REAL
        )
    """)
    conn.commit()
    return conn


def get_cached(serial: str) -> dict | None:
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
    conn = _get_db()
    rows = conn.execute(
        "SELECT serial, component_name, hierarchical_location, device_class, last_updated FROM device_cache ORDER BY serial"
    ).fetchall()
    conn.close()
    return [
        {"serial": r[0], "componentName": r[1], "hierarchicalLocation": r[2], "deviceClass": r[3], "lastUpdated": r[4]}
        for r in rows
    ]


# ── Device list cache ──────────────────────────────────────────────

def get_cached_devices() -> list[dict]:
    """Get cached device list including component names."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT serial, name, node_id, component_name, online, last_seen, last_updated FROM device_list ORDER BY serial"
    ).fetchall()
    conn.close()
    return [
        {"name": r[1], "nodeId": r[2], "componentName": r[3] or "", "online": r[4], "lastSeen": r[5], "lastUpdated": r[6]}
        for r in rows
    ]


def set_cached_devices(devices: list[dict]):
    """Update the cached device list, preserving component_names and online status."""
    conn = _get_db()
    now = time.time()
    existing = {}
    for r in conn.execute("SELECT serial, component_name, online, last_seen FROM device_list").fetchall():
        existing[r[0]] = (r[1], r[2], r[3])
    for d in devices:
        serial = d.get("nodeId", "")
        prev = existing.get(serial)
        prev_cn = prev[0] if prev else ""
        prev_online = prev[1] if prev else None  # None = new device
        prev_seen = prev[2] if prev else 0
        conn.execute("""
            INSERT OR REPLACE INTO device_list (serial, name, node_id, component_name, online, last_seen, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            serial,
            d.get("name", ""),
            serial,
            d.get("componentName") or prev_cn or "",
            prev_online if prev_online is not None else 1,  # new devices default online
            prev_seen if prev_seen else 0,
            now
        ))
    conn.commit()
    conn.close()


def set_component_name(serial: str, component_name: str):
    """Update the component name for a cached device."""
    conn = _get_db()
    conn.execute(
        "UPDATE device_list SET component_name = ?, last_updated = ? WHERE serial = ?",
        (component_name, time.time(), serial)
    )
    conn.commit()
    conn.close()


def set_device_online(serial: str):
    conn = _get_db()
    conn.execute("UPDATE device_list SET online = 1, last_seen = ?, last_updated = ? WHERE serial = ?",
                 (time.time(), time.time(), serial))
    conn.commit()
    conn.close()


def set_device_offline(serial: str):
    conn = _get_db()
    conn.execute("UPDATE device_list SET online = 0, last_updated = ? WHERE serial = ?",
                 (time.time(), serial))
    conn.commit()
    conn.close()
