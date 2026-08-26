"""Production DB migration for lcc-tools: dedup device_list 136 -> 39.

Safe guard: refuses to run unless source count shows duplicates and it creates
a timestamped backup first. Run while the API container is STOPPED.
"""
import os
import re
import shutil
import sqlite3
import sys
import time

DB = os.environ.get("LCC_DB", "/home/administrator/lcc-tools/data/device_cache.db")


def stable_key(node_id: str) -> str:
    if node_id is None:
        return ""
    m = re.search(r";s=(.*)$", node_id)
    return m.group(1) if m else node_id


def main():
    if not os.path.exists(DB):
        print("DB nicht gefunden:", DB)
        sys.exit(2)

    # Backup
    bak = DB + ".bak." + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB, bak)
    print("Backup erstellt:", bak)

    conn = sqlite3.connect(DB)
    before = conn.execute("SELECT COUNT(*) FROM device_list").fetchone()[0]
    uni = conn.execute(
        "SELECT COUNT(DISTINCT CASE WHEN instr(serial,';s=') THEN substr(serial,instr(serial,';s=')+3) ELSE serial END) FROM device_list"
    ).fetchone()[0]
    print(f"Vor Migration: {before} rows, {uni} eindeutige stable keys")

    if uni >= before:
        print("Keine Duplikate -> nichts zu tun")
        conn.close()
        sys.exit(0)

    rows = conn.execute(
        "SELECT serial, name, node_id, component_name, online, last_seen, last_updated FROM device_list"
    ).fetchall()

    best = {}
    for serial, name, node_id, comp, online, last_seen, last_updated in rows:
        sk = stable_key(serial or "")
        node_id = node_id or serial
        cand = (serial, name, node_id, comp, online or 0, last_seen or 0, last_updated or 0)
        if sk not in best:
            best[sk] = cand
            continue
        prev = best[sk]
        cand_online = cand[4]
        prev_online = prev[4]
        if cand_online != prev_online:
            keep = cand if cand_online else prev
        else:
            keep = cand if (cand[5] or 0) > (prev[5] or 0) else prev
        best[sk] = keep

    conn.execute("DROP TABLE device_list")
    conn.execute("""
        CREATE TABLE device_list (
            serial TEXT PRIMARY KEY,
            name TEXT,
            node_id TEXT,
            component_name TEXT,
            online INTEGER DEFAULT -1,
            last_seen REAL DEFAULT 0,
            last_updated REAL
        )
    """)
    for sk, (serial, name, node_id, comp, online, last_seen, last_updated) in best.items():
        conn.execute(
            "INSERT OR REPLACE INTO device_list (serial, name, node_id, component_name, online, last_seen, last_updated) VALUES (?,?,?,?,?,?,?)",
            (sk, name, node_id, comp or "", online, last_seen, 0.0),
        )
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM device_list").fetchone()[0]
    online = conn.execute("SELECT COUNT(*) FROM device_list WHERE online=1").fetchone()[0]
    print(f"Nach Migration: {after} rows ({online} online). Backup: {bak}")
    conn.close()


if __name__ == "__main__":
    main()