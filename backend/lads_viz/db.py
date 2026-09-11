"""SQLite-Store: Metadaten (Server, Geräte, Signale) + Dashboard-Konfiguration.

Messwerte/Zeitreihen folgen später (TimescaleDB); bis dahin lesen die
Dashboards Historien on-demand per OPC UA (siehe history.py).
"""
from pathlib import Path

import aiosqlite

from . import config

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS servers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,          -- opc.tcp://...
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id              INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    serial                 TEXT NOT NULL,   -- nodeId-String-Teil (stabiler Key)
    browse_name            TEXT NOT NULL,   -- "SERIAL@SERIAL"
    component_name         TEXT DEFAULT '',
    hierarchical_location  TEXT DEFAULT '',
    device_class           TEXT DEFAULT '',
    manufacturer           TEXT DEFAULT '',
    model                  TEXT DEFAULT '',
    UNIQUE(server_id, serial)
);

CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id        INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    browse_name      TEXT NOT NULL,   -- Funktionsname, z.B. "Power"
    display_name     TEXT DEFAULT '',
    unit_browse_name TEXT NOT NULL,   -- z.B. "Switch0", "SensorUnit"
    engineering_unit TEXT DEFAULT '', -- z.B. "W", "°C"
    historizing      INTEGER DEFAULT 0,
    node_id          TEXT DEFAULT '', -- SensorValue-nodeId (History/Subscriptions)
    last_value       TEXT DEFAULT '',
    last_ts          TEXT DEFAULT '',
    monitored        INTEGER DEFAULT 0, -- "hinzugefügt" -> für Dashboards verfügbar
    UNIQUE(device_id, unit_browse_name, browse_name)
);

CREATE TABLE IF NOT EXISTS dashboards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sensor_values (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    ts        INTEGER NOT NULL,   -- epoch ms
    value     REAL NOT NULL,
    UNIQUE(signal_id, ts)
);

CREATE TABLE IF NOT EXISTS widgets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,           -- 'linechart' | 'stat'
    title        TEXT DEFAULT '',
    config       TEXT DEFAULT '{}',       -- JSON: {signals: [signal_ids]}
    grid         TEXT DEFAULT '{}',       -- JSON: {x, y, w, h}
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_devices_server ON devices(server_id);
CREATE INDEX IF NOT EXISTS idx_signals_device ON signals(device_id);
CREATE INDEX IF NOT EXISTS idx_widgets_dashboard ON widgets(dashboard_id);
CREATE INDEX IF NOT EXISTS idx_sensor_values_sig_ts ON sensor_values(signal_id, ts);
"""

_db: aiosqlite.Connection | None = None


async def init_db():
    global _db
    if _db is not None:
        return _db
    db_path = config.DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()
    return _db


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        await init_db()
    return _db


# ── Zeitreihen-Store (append-only) ─────────────────────────────

async def insert_values(signal_id: int, points) -> None:
    """Punkte [(ts_ms, value), ...] append-only einfügen (Duplikate ignoriert)."""
    d = await get_db()
    await d.executemany(
        "INSERT OR IGNORE INTO sensor_values (signal_id, ts, value) VALUES (?, ?, ?)",
        [(signal_id, int(t), float(v)) for t, v in points],
    )
    await d.commit()


async def read_values(signal_id: int, start_ms: int, end_ms: int) -> list:
    d = await get_db()
    cur = await d.execute(
        "SELECT ts, value FROM sensor_values WHERE signal_id=? AND ts>=? AND ts<=? ORDER BY ts",
        (signal_id, start_ms, end_ms),
    )
    return [(r["ts"], r["value"]) for r in await cur.fetchall()]


async def monitored_signals() -> list[dict]:
    d = await get_db()
    cur = await d.execute(
        "SELECT id, node_id, engineering_unit FROM signals WHERE monitored=1 AND node_id != ''"
    )
    return [dict(r) for r in await cur.fetchall()]