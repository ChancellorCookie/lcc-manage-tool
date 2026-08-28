"""SQLite cache for OPC-UA device properties and device list."""

import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "device_cache.db"


def stable_key(node_id: str) -> str:
    """Reduce a (possibly ns-volatile) nodeId to a stable device key.

    The namespace index (ns=N) is NOT stable across OPC UA server restarts /
    reconnects — the same physical device can be reported as ns=10;s=X on one
    refresh and ns=19;s=X on the next. Using the full nodeId as a primary key
    therefore spawns duplicate rows. Here we derive a durable key from the
    string identifier part only (e.g. 'ns=11;s=SD3GK002603' -> 'SD3GK002603').

    Integer nodeIds (no ';s=' part) are kept verbatim to avoid collisions.
    """
    if node_id is None:
        return ""
    m = re.search(r";s=(.*)$", node_id)
    if m:
        return m.group(1)
    return node_id


_stable_key = stable_key  # backward-compat alias


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add the offline-monitoring columns if this DB predates them."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(device_list)").fetchall()}
    adds = {
        "offline_monitor": "INTEGER DEFAULT 0",
        "offline_since": "REAL",
        "first_alerted": "INTEGER DEFAULT 0",
        "hierarchical_location": "TEXT",
    }
    for name, ddl in adds.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE device_list ADD COLUMN {name} {ddl}")


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
    _ensure_columns(conn)
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
    """Get cached device list including component names.

    `nodeId` is returned as the CURRENT full node id (it tracks ns changes),
    while `serial` serves as the stable key.
    """
    conn = _get_db()
    cols = [x[1] for x in conn.execute("PRAGMA table_info(device_list)").fetchall()]
    rows = conn.execute(
        "SELECT serial, name, node_id, component_name, online, last_seen, last_updated, offline_monitor, offline_since, first_alerted, hierarchical_location FROM device_list ORDER BY serial"
    ).fetchall()
    conn.close()
    return [
        {
            "serial": r[0], "name": r[1], "nodeId": r[2] or r[0], "componentName": r[3] or "",
            "online": r[4], "lastSeen": r[5], "lastUpdated": r[6],
            "offlineMonitor": bool(r[7]), "offlineSince": r[8], "firstAlerted": bool(r[9]),
            "hierarchicalLocation": r[10] or "" if "hierarchical_location" in cols else "",
        }
        for r in rows
    ]


def set_cached_devices(devices: list[dict]):
    """Update the cached device list, keyed by the STABLE device identifier.

    Handles a volatile namespace index: if a device reappears under a new
    ns=N;s=SERNR node id, we update its stored full node_id in place rather
    than inserting a duplicate row.
    """
    conn = _get_db()
    now = time.time()
    existing = {}
    for r in conn.execute("SELECT serial, node_id, component_name, online, last_seen FROM device_list").fetchall():
        existing[r[0]] = (r[1], r[2], r[3], r[4])
    for d in devices:
        node_id = d.get("nodeId", "")
        serial = _stable_key(node_id)
        prev = existing.get(serial)
        prev_cn = prev[1] if prev else ""
        prev_seen = prev[3] if prev else 0
        conn.execute("""
            INSERT INTO device_list (serial, name, node_id, component_name, online, last_seen, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(serial) DO UPDATE SET
                node_id = excluded.node_id,
                name = excluded.name,
                component_name = COALESCE(excluded.component_name, device_list.component_name),
                online = excluded.online,
                last_seen = excluded.last_seen,
                last_updated = excluded.last_updated
        """, (
            serial,
            d.get("name", ""),
            node_id,
            d.get("componentName") or prev_cn or "",
            1,  # device was just seen in the live browse -> online
            prev_seen if prev_seen else 0,
            now
        ))
    conn.commit()
    conn.close()


# ── Online state + offline monitoring ──────────────────────────────

def _get_row(conn, serial: str):
    return conn.execute(
        "SELECT online, offline_since, offline_monitor, first_alerted FROM device_list WHERE serial = ?",
        (serial,),
    ).fetchone()


def set_device_online(serial: str):
    conn = _get_db()
    now = time.time()
    conn.execute(
        "UPDATE device_list SET online = 1, last_seen = ?, last_updated = ?, offline_since = NULL, first_alerted = 0 WHERE serial = ?",
        (now, now, _stable_key(serial)),
    )
    conn.commit()
    conn.close()


def set_device_offline(serial: str):
    """Mark a device offline, recording offline_since only on the online->offline transition."""
    conn = _get_db()
    now = time.time()
    serial = _stable_key(serial)
    row = conn.execute("SELECT online, offline_since FROM device_list WHERE serial = ?", (serial,)).fetchone()
    if row is not None:
        was_online = row[0] == 1
        existing_off = row[1]
        # record offline_since on first transition only (don't keep overwriting)
        offline_since = existing_off or now
        conn.execute(
            "UPDATE device_list SET online = 0, last_updated = ?, offline_since = ? WHERE serial = ?",
            (now, offline_since, serial),
        )
    conn.commit()
    conn.close()


def set_offline_monitor(serial: str, enabled: bool):
    conn = _get_db()
    conn.execute("UPDATE device_list SET offline_monitor = ?, last_updated = ? WHERE serial = ?",
                 (1 if enabled else 0, time.time(), _stable_key(serial)))
    conn.commit()
    conn.close()


def set_device_meta(serial: str, component_name: str | None = None,
                   hierarchical_location: str | None = None):
    """Persist component name + hierarchical location for a device."""
    conn = _get_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(device_list)").fetchall()}
    sets = ["last_updated = ?"]
    args = [time.time()]
    if component_name is not None:
        sets.append("component_name = ?")
        args.append(component_name)
    if hierarchical_location is not None and "hierarchical_location" in cols:
        sets.append("hierarchical_location = ?")
        args.append(hierarchical_location)
    args.append(_stable_key(serial))
    conn.execute(f"UPDATE device_list SET {', '.join(sets)} WHERE serial = ?", args)
    conn.commit()
    conn.close()


def get_monitored_devices() -> list[dict]:
    """All devices with offline_monitor enabled (used by the offline monitor)."""
    conn = _get_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(device_list)").fetchall()}
    hloc = "hierarchical_location" in cols
    rows = conn.execute(
        "SELECT serial, name, node_id, component_name, online, offline_since, first_alerted, hierarchical_location FROM device_list WHERE offline_monitor = 1 ORDER BY name"
    ).fetchall()
    conn.close()
    return [
        {
            "serial": r[0], "name": r[1], "nodeId": r[2], "componentName": r[3] or "",
            "online": r[4], "offlineSince": r[5], "firstAlerted": bool(r[6]),
            "hierarchicalLocation": r[7] or "" if hloc else "",
        }
        for r in rows
    ]


def mark_first_alerted(serials: list[str]):
    conn = _get_db()
    with conn:  # autocommit transaction
        for s in serials:
            conn.execute("UPDATE device_list SET first_alerted = 1, last_updated = ? WHERE serial = ?",
                         (time.time(), _stable_key(s)))
    conn.close()


def set_component_name(serial: str, component_name: str):
    """Update the component name for a cached device (keyed by stable serial)."""
    serial = _stable_key(serial)
    conn = _get_db()
    conn.execute(
        "UPDATE device_list SET component_name = ?, last_updated = ? WHERE serial = ?",
        (component_name, time.time(), serial)
    )
    conn.commit()
    conn.close()