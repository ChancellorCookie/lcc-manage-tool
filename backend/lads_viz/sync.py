"""Rediscover: Geräte + Signale eines Servers re-browsen und node_ids reparieren.

Gemeinsam genutzt vom Discover-Endpoint UND dem periodischen Wartungs-Task, damit
Server-Adressraum-Änderungen (ns-Index-Rebuild) automatisch geheilt werden.
"""
import logging

from . import db, opcua

log = logging.getLogger("lads_viz.sync")


async def rediscover(server_id: int) -> dict:
    d = await db.get_db()
    cur = await d.execute("SELECT * FROM servers WHERE id=?", (server_id,))
    srv = await cur.fetchone()
    if not srv:
        raise KeyError(f"Server {server_id} nicht gefunden")

    devices = await opcua.list_devices(srv["url"])
    all_sig = await opcua.list_all_signals(srv["url"])

    devices_added = 0
    for dev in devices:
        cur = await d.execute(
            "SELECT id, component_name, hierarchical_location FROM devices WHERE server_id=? AND serial=?",
            (server_id, dev["serial"]),
        )
        row = await cur.fetchone()
        if row:
            existing_loc = row["hierarchical_location"] or ""
            existing_comp = row["component_name"] or ""
            if dev["hierarchical_location"] or not existing_loc:
                await d.execute(
                    "UPDATE devices SET browse_name=?, component_name=?, hierarchical_location=?, device_class=?, manufacturer=?, model=? WHERE id=?",
                    (dev["browse_name"], dev["component_name"] or existing_comp, dev["hierarchical_location"],
                     dev["device_class"], dev["manufacturer"], dev["model"], row["id"]),
                )
            # node_ids re-browsen + reparieren (ns-Index kann sich geändert haben)
            dev_id = row["id"]
            for s in all_sig.get(dev["serial"], []):
                cur = await d.execute(
                    "SELECT id FROM signals WHERE device_id=? AND unit_browse_name=? AND browse_name=?",
                    (dev_id, s["unit_browse_name"], s["browse_name"]),
                )
                srow = await cur.fetchone()
                if srow:
                    await d.execute(
                        "UPDATE signals SET display_name=?, engineering_unit=?, historizing=?, node_id=?, last_value=?, last_ts=? WHERE id=?",
                        (s["display_name"], s["engineering_unit"], 1 if s["historizing"] else 0,
                         s["node_id"], s["last_value"], s["last_ts"], srow["id"]),
                    )
                else:
                    await d.execute(
                        "INSERT INTO signals (device_id, browse_name, display_name, unit_browse_name, engineering_unit, historizing, node_id, last_value, last_ts, monitored) VALUES (?,?,?,?,?,?,?,?,?,0)",
                        (dev_id, s["browse_name"], s["display_name"], s["unit_browse_name"], s["engineering_unit"],
                         1 if s["historizing"] else 0, s["node_id"], s["last_value"], s["last_ts"]),
                    )
        else:
            await d.execute(
                "INSERT INTO devices (server_id, browse_name, serial, component_name, hierarchical_location, device_class, manufacturer, model) VALUES (?,?,?,?,?,?,?,?)",
                (server_id, dev["browse_name"], dev["serial"], dev["component_name"], dev["hierarchical_location"],
                 dev["device_class"], dev["manufacturer"], dev["model"]),
            )
            devices_added += 1

    await d.commit()
    return {"devices_added": devices_added, "total_devices": len(devices)}
