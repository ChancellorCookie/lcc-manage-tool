"""Seed-Dashboard: legt ein Demo-Dashboard an, falls noch keines existiert."""
import json

from . import db


async def seed_demo_dashboard() -> dict | None:
    d = await db.get_db()
    cur = await d.execute("SELECT COUNT(*) FROM dashboards")
    if (await cur.fetchone())[0] > 0:
        return None
    cur = await d.execute(
        "SELECT id FROM signals WHERE browse_name='Power' AND engineering_unit='W' ORDER BY id LIMIT 8"
    )
    ids = [r["id"] for r in await cur.fetchall()]
    if not ids:
        return None

    cur = await d.execute(
        "INSERT INTO dashboards (name, description) VALUES (?, ?)",
        ("Verbrauch (Demo)", "Automatisch angelegtes Seed-Dashboard"),
    )
    dash_id = cur.lastrowid
    await d.execute(
        "INSERT INTO widgets (dashboard_id, type, title, config, grid) VALUES (?,?,?,?,?)",
        (dash_id, "charttable", "Leistung & Verbrauch",
         json.dumps({"signals": ids}), json.dumps({"x": 0, "y": 0, "w": 12, "h": 10})),
    )
    await d.execute(
        "INSERT INTO widgets (dashboard_id, type, title, config, grid) VALUES (?,?,?,?,?)",
        (dash_id, "stat", "Verbrauch (Ø)",
         json.dumps({"signals": ids[:1]}), json.dumps({"x": 0, "y": 10, "w": 4, "h": 4})),
    )
    await d.commit()
    return {"dashboard_id": dash_id, "signals": len(ids)}
