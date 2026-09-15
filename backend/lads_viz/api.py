"""API-Router: Server, OPC-UA-Discovery, Sensoren, History, Dashboards."""
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import config, db, history, opcua, stats, sync, usage as usage_mod

router = APIRouter()


class ServerIn(BaseModel):
    name: str
    url: str


class DashboardIn(BaseModel):
    name: str
    description: str = ""


class DashboardPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class WidgetIn(BaseModel):
    type: str
    title: str = ""
    config: dict = {}
    grid: dict = {}


class SettingsIn(BaseModel):
    eur_per_kwh: float | None = None


# ── Meta ───────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/config")
async def get_config():
    return {"default_opcua_url": config.OPC_URL}


# ── Einstellungen ──────────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    d = await db.get_db()
    cur = await d.execute("SELECT key, value FROM settings")
    rows = dict((r["key"], r["value"]) for r in await cur.fetchall())
    return {
        "eur_per_kwh": float(rows.get("eur_per_kwh", 0.32)),
        "everything": rows,
    }


@router.put("/settings")
async def put_settings(body: SettingsIn):
    d = await db.get_db()
    if body.eur_per_kwh is not None:
        await d.execute(
            "INSERT INTO settings(key, value) VALUES('eur_per_kwh', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(body.eur_per_kwh),),
        )
        await d.commit()
    return {"ok": True}


# ── Server ─────────────────────────────────────────────────────

@router.get("/servers")
async def list_servers():
    d = await db.get_db()
    cur = await d.execute("SELECT * FROM servers ORDER BY id")
    return [dict(r) for r in await cur.fetchall()]


@router.post("/servers")
async def create_server(body: ServerIn):
    d = await db.get_db()
    cur = await d.execute(
        "INSERT INTO servers (name, url) VALUES (?, ?)",
        (body.name.strip(), body.url.strip()),
    )
    await d.commit()
    return {"id": cur.lastrowid, "name": body.name.strip(), "url": body.url.strip()}


@router.delete("/servers/{server_id}")
async def delete_server(server_id: int):
    d = await db.get_db()
    await d.execute("DELETE FROM servers WHERE id=?", (server_id,))
    await d.commit()
    return {"deleted": True}


# ── Discovery (OPC UA) ─────────────────────────────────────────

@router.post("/servers/{server_id}/discover")
async def discover(server_id: int):
    try:
        return await sync.rediscover(server_id)
    except KeyError:
        raise HTTPException(404, "Server nicht gefunden")
    except Exception as e:
        raise HTTPException(502, f"OPC-UA-Fehler: {e}")


# ── Geräte & Sensoren ──────────────────────────────────────────

@router.get("/servers/{server_id}/devices")
async def list_devices(server_id: int):
    d = await db.get_db()
    cur = await d.execute(
        """
        SELECT dev.*,
               (SELECT COUNT(*) FROM signals s WHERE s.device_id = dev.id AND s.monitored=1) AS monitored_count
        FROM devices dev
        WHERE dev.server_id = ?
        ORDER BY dev.component_name COLLATE NOCASE, dev.hierarchical_location
        """,
        (server_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


@router.get("/devices/{device_id}/signals")
async def device_signals(device_id: int):
    d = await db.get_db()
    cur = await d.execute("SELECT * FROM devices WHERE id=?", (device_id,))
    dev = await cur.fetchone()
    if not dev:
        raise HTTPException(404, "Gerät nicht gefunden")
    cur = await d.execute("SELECT * FROM servers WHERE id=?", (dev["server_id"],))
    srv = await cur.fetchone()
    if not srv:
        raise HTTPException(404, "Server nicht gefunden")

    try:
        sigs = await opcua.list_signals(srv["url"], dev["serial"])
    except Exception as e:
        raise HTTPException(502, f"OPC-UA-Fehler: {e}")

    for s in sigs:
        cur = await d.execute(
            "SELECT id FROM signals WHERE device_id=? AND unit_browse_name=? AND browse_name=?",
            (device_id, s["unit_browse_name"], s["browse_name"]),
        )
        row = await cur.fetchone()
        if row:
            await d.execute(
                "UPDATE signals SET display_name=?, engineering_unit=?, historizing=?, node_id=?, last_value=?, last_ts=? WHERE id=?",
                (s["display_name"], s["engineering_unit"], 1 if s["historizing"] else 0,
                 s["node_id"], s["last_value"], s["last_ts"], row["id"]),
            )
        else:
            await d.execute(
                "INSERT INTO signals (device_id, browse_name, display_name, unit_browse_name, engineering_unit, historizing, node_id, last_value, last_ts, monitored) VALUES (?,?,?,?,?,?,?,?,?,0)",
                (device_id, s["browse_name"], s["display_name"], s["unit_browse_name"],
                 s["engineering_unit"], 1 if s["historizing"] else 0, s["node_id"],
                 s["last_value"], s["last_ts"]),
            )
    await d.commit()

    cur = await d.execute("SELECT * FROM signals WHERE device_id=? ORDER BY browse_name", (device_id,))
    return [dict(r) for r in await cur.fetchall()]


@router.get("/sensors")
async def monitored_sensors(server_id: int | None = None):
    d = await db.get_db()
    q = """
        SELECT s.*, dev.component_name, dev.hierarchical_location, dev.serial
        FROM signals s JOIN devices dev ON dev.id = s.device_id
        WHERE s.monitored = 1
    """
    params: tuple = ()
    if server_id is not None:
        q += " AND dev.server_id = ?"
        params = (server_id,)
    q += " ORDER BY dev.component_name COLLATE NOCASE, s.display_name COLLATE NOCASE"
    cur = await d.execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


@router.post("/sensors/{signal_id}/monitor")
async def monitor_signal(signal_id: int):
    d = await db.get_db()
    cur = await d.execute("UPDATE signals SET monitored=1 WHERE id=?", (signal_id,))
    await d.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Sensor nicht gefunden")
    return {"id": signal_id, "monitored": True}


@router.post("/sensors/{signal_id}/unmonitor")
async def unmonitor_signal(signal_id: int):
    d = await db.get_db()
    cur = await d.execute("UPDATE signals SET monitored=0 WHERE id=?", (signal_id,))
    await d.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Sensor nicht gefunden")
    return {"id": signal_id, "monitored": False}


# ── Alle gespeicherten Kanäle (Widget-Dialog) ─────────────────

@router.get("/signals")
async def list_all_signals(server_id: int | None = None, with_history_only: bool = False):
    """ALLE gespeicherten Signale (nicht nur 'überwachte') — zum Zusammenbauen der Dashboards."""
    d = await db.get_db()
    q = """SELECT s.*, dev.component_name, dev.hierarchical_location, dev.serial,
                  srv.url AS server_url, srv.name AS server_name
           FROM signals s
           JOIN devices dev ON dev.id = s.device_id
           JOIN servers srv ON srv.id = dev.server_id"""
    params: tuple = ()
    conds = []
    if server_id is not None:
        conds.append("dev.server_id = ?")
        params += (server_id,)
    if with_history_only:
        conds.append("s.historizing = 1")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY dev.component_name COLLATE NOCASE, s.display_name COLLATE NOCASE"
    cur = await d.execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


# ── System-Info (Docker-Host-Speicher) ─────────────────────────

@router.get("/system/storage")
async def system_storage():
    """Speicherplatz des Docker-Hosts für die Startseiten-Kachel.

    Bevorzugt: data/storage.json (vom Host-Cron geschrieben, liegt im
    gemounteten Volume) mit echten Host-Werten inkl. docker system df.
    Fallback: df des Dateisystems hinter der DB (im Container = Host-Partition).
    """
    import shutil
    from pathlib import Path

    payload = {"source": None, "disk": None, "docker": None, "ts": None}
    db_dir = Path(config.DB_PATH).parent
    for cand in (db_dir / "storage.json", Path("/app/data/storage.json")):
        try:
            if cand.exists():
                data = json.loads(cand.read_text())
                disk = data.get("disk")
                if disk and disk.get("total_gb"):
                    payload.update({"source": "host-cron", "disk": disk,
                                    "docker": data.get("docker"), "ts": data.get("ts")})
                    return payload
        except Exception:
            continue
    # Fallback: Container-Sicht (Overlay = Host-Partition hinter /var/lib/docker)
    try:
        u = shutil.disk_usage(str(db_dir))
        gb = 1024 ** 3
        payload.update({
            "source": "container-df",
            "disk": {
                "total_gb": round(u.total / gb, 1),
                "used_gb": round(u.used / gb, 1),
                "free_gb": round(u.free / gb, 1),
                "percent": round(u.used / u.total * 100, 1),
            },
        })
    except Exception:
        pass
    return payload


# ── History (OPC UA, on-demand) ────────────────────────────────

@router.get("/signals/{signal_id}/history")
async def signal_history(signal_id: int, start: str, end: str | None = None, points: int = 1500):
    d = await db.get_db()
    cur = await d.execute(
        """
        SELECT s.*, dev.component_name, dev.hierarchical_location, srv.url AS server_url
        FROM signals s
        JOIN devices dev ON dev.id = s.device_id
        JOIN servers srv ON srv.id = dev.server_id
        WHERE s.id = ?
        """,
        (signal_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Signal nicht gefunden")
    if not row["node_id"]:
        raise HTTPException(400, "Signal hat keine OPC-UA-nodeId — Gerät zuerst aufklappen")

    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, f"start ungültig: {start}")
    end_dt = None
    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, f"end ungültig: {end}")
    else:
        end_dt = datetime.now(timezone.utc)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    # DB-first: lokale Zeitreihe lesen; nur fehlende Fenster per OPC UA nachladen
    # (wird dabei ins Archiv geschrieben → Folgefragen kommen komplett aus der DB).
    try:
        raw, dmeta = await history.read_history_db_first(
            row["server_url"], row["node_id"], signal_id, start_ms, end_ms
        )
    except Exception as e:
        raise HTTPException(502, f"History-Fehler: {e}")

    pts = history.lttb(raw, max(2, points)) if points > 0 else raw
    stats = history.compute_stats(raw)
    unit = row["engineering_unit"] or ""
    if unit.rstrip().endswith("W"):
        wh = history.compute_energy_wh(raw)
        if wh is not None:
            stats["energy_wh"] = wh

    return {
        "signal": {"id": row["id"], "display_name": row["display_name"], "engineering_unit": unit},
        "device": {"component_name": row["component_name"], "hierarchical_location": row["hierarchical_location"]},
        "points": [[x, y] for x, y in pts],
        "raw_count": len(raw),
        "stats": stats,
        "source": dmeta["source"],
        "db_points": dmeta["db_points"],
        "filled_points": dmeta["filled_points"],
    }


# ── Verbrauchs-Statistiken ─────────────────────────────────────

@router.get("/stats/consumption")
async def stats_consumption(signals: str, start: str, end: str | None = None,
                            bucket: str = "auto", eur_kwh: float | None = None):
    from zoneinfo import ZoneInfo

    ids = [int(x) for x in signals.split(",") if x.strip().lstrip("-").isdigit()]
    if not ids:
        raise HTTPException(400, "signals (mind. 1 kommagetrennte Signal-IDs) erforderlich")
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, f"start ungültig: {start}")
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, f"end ungültig: {end}")
    else:
        end_dt = datetime.now(timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    if end_ms <= start_ms:
        raise HTTPException(400, "end muss nach start liegen")
    if eur_kwh is None:
        d = await db.get_db()
        srow = await (await d.execute("SELECT value FROM settings WHERE key='eur_per_kwh'")).fetchone()
        eur_kwh = float(srow["value"]) if srow else 0.32
    eur_kwh = round(float(eur_kwh), 6)

    @stats.cached
    async def compute(ids_t, start_ms_, end_ms_, bucket_, eur_):
        d = await db.get_db()
        ph = ",".join("?" * len(ids_t))
        cur = await d.execute(
            f"""
            SELECT s.id, s.node_id, s.browse_name, s.engineering_unit AS unit,
                   dev.component_name AS device, dev.hierarchical_location AS location,
                   srv.url AS server_url
            FROM signals s
            JOIN devices dev ON dev.id = s.device_id
            JOIN servers srv ON srv.id = dev.server_id
            WHERE s.id IN ({ph})
            """,
            list(ids_t),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        if not rows:
            raise HTTPException(404, "keine Signale gefunden")
        by_url: dict = {}
        for r in rows:
            by_url.setdefault(r["server_url"], []).append((r["id"], r["node_id"]))
        raw: dict = {}
        hmeta: dict = {}
        for url, items in by_url.items():
            try:
                rr, mm = await history.read_histories_db_first(url, items, start_ms_, end_ms_)
            except Exception as e:
                raise HTTPException(502, f"History-Fehler: {e}")
            raw.update(rr)
            hmeta.update(mm)
        metas = [
            {"id": m["id"], "unit": m["unit"], "device": m["device"],
             "location": m["location"], "browse_name": m["browse_name"]}
            for m in rows
        ]
        result = stats.consumption(metas, raw, start_ms_, end_ms_, bucket_, eur_)
        srcs = {v["source"] for v in hmeta.values()}
        result["source"] = "db" if srcs == {"db"} else ("opcua" if srcs == {"opcua"} else "db+opcua")
        result["db_points"] = sum(v["db_points"] for v in hmeta.values())
        result["filled_points"] = sum(v["filled_points"] for v in hmeta.values())
        return result

    return await compute(tuple(ids), start_ms, end_ms, bucket, eur_kwh)


@router.get("/usage")
async def viz_usage(
    signal_ids: str,
    start: str = "",
    end: str = "",
    start_threshold: float = 10.0,
    stop_threshold: float = 5.0,
):
    """Nutzungsanalyse: Hysterese auf der Summe mehrerer Indikator-Signale."""
    ids = [int(x) for x in signal_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(422, "signal_ids fehlt")
    if start:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    else:
        start_dt = datetime.now(timezone.utc) - timedelta(days=1)
    if end:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    else:
        end_dt = datetime.now(timezone.utc)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    if end_ms <= start_ms:
        raise HTTPException(400, "end muss nach start liegen")
    try:
        return await usage_mod.usage_analysis(ids, start_ms, end_ms, start_threshold, stop_threshold)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"Usage-Fehler: {e}")


# ── Dashboard-Statistiken (Startseiten-Kacheln) ────────────────
# WICHTIG: vor /dashboards/{dashboard_id} registrieren, sonst wird "stats"
# als dashboard_id geparst.

@router.get("/dashboards/stats")
async def dashboard_stats(window_h: int = 24):
    """Je Dashboard: kWh + Kosten im Fenster, aktueller Verbrauch, Widget-/Signal-Zahl.

    Quelle: lokaler sensor_values-Store (Collector + Write-through), nicht OPC UA.
    Fenster default 24 h; Signale ohne Daten liefern None (Kachel zeigt '–').
    """
    import time

    if window_h < 1 or window_h > 31 * 24:
        raise HTTPException(400, "window_h zwischen 1 und 744")

    async def compute(window_h_: int):
        d = await db.get_db()
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - window_h_ * 3_600_000
        cur = await d.execute(
            """SELECT db.id, db.name, db.description, w.id AS wid, w.config
               FROM dashboards db
               LEFT JOIN widgets w ON w.dashboard_id = db.id
               ORDER BY db.id, w.id"""
        )
        rows = await cur.fetchall()
        dash: dict = {}
        for r in rows:
            if r["id"] not in dash:
                dash[r["id"]] = {"id": r["id"], "name": r["name"], "description": r["description"],
                                 "widget_count": 0, "signal_ids": set()}
            if r["wid"] is not None:
                dash[r["id"]]["widget_count"] += 1
                try:
                    cfg = json.loads(r["config"] or "{}")
                except Exception:
                    cfg = {}
                for s in cfg.get("signals") or []:
                    try:
                        dash[r["id"]]["signal_ids"].add(int(s))
                    except Exception:
                        pass

        eur_kwh = 0.32
        srow = await (await d.execute("SELECT value FROM settings WHERE key='eur_per_kwh'")).fetchone()
        if srow:
            try:
                eur_kwh = float(srow["value"])
            except Exception:
                pass

        meta_cache: dict = {}

        async def signal_meta(sid: int):
            if sid not in meta_cache:
                rc = await d.execute(
                    """SELECT s.id, s.display_name, s.browse_name, s.engineering_unit AS unit,
                              dev.component_name
                       FROM signals s JOIN devices dev ON dev.id = s.device_id WHERE s.id = ?""",
                    (sid,),
                )
                row = await rc.fetchone()
                meta_cache[sid] = dict(row) if row else None
            return meta_cache[sid]

        out = []
        for dd in dash.values():
            ids = sorted(dd["signal_ids"]) or []
            kwh_total = 0.0
            current_w = 0.0
            power_n = 0
            coverage_h = 0.0
            latest = []
            for sid in ids:
                meta = await signal_meta(sid)
                if not meta:
                    continue
                unit = (meta["unit"] or "").lower()
                is_power = unit in ("w", "kw", "wh", "mwh")
                rc = await d.execute(
                    """SELECT ts, value FROM sensor_values
                       WHERE signal_id=? AND ts>=? AND ts<=? ORDER BY ts LIMIT 50000""",
                    (sid, start_ms, now_ms),
                )
                pts = [(r["ts"], r["value"]) for r in await rc.fetchall()]
                if is_power:
                    wh, _avg, _part, cov = stats.window_summary(pts, start_ms, now_ms)
                    if wh > 0:
                        kwh_total += wh / 1000.0
                        power_n += 1
                        coverage_h += cov
                rc = await d.execute(
                    "SELECT ts, value FROM sensor_values WHERE signal_id=? ORDER BY ts DESC LIMIT 1",
                    (sid,),
                )
                last = await rc.fetchone()
                if last:
                    latest.append({
                        "signal_id": sid,
                        "device": meta["component_name"] or "",
                        "name": meta["display_name"] or meta["browse_name"],
                        "unit": meta["unit"] or "",
                        "value": last["value"],
                        "ts": last["ts"],
                    })
                    if is_power:
                        current_w += last["value"]
            out.append({
                "id": dd["id"],
                "name": dd["name"],
                "description": dd["description"],
                "widget_count": dd["widget_count"],
                "signal_count": len(ids),
                "power_signals": power_n,
                "kwh": round(kwh_total, 3) if power_n else None,
                "cost": round(kwh_total * eur_kwh, 2) if power_n else None,
                "current_w": round(current_w, 1) if power_n else None,
                "coverage_h": round(coverage_h, 2),
                "latest": latest[:5],
            })
        return out

    return await stats.cached(compute)(window_h)


# ── Dashboards & Widgets ───────────────────────────────────────

@router.get("/dashboards")
async def list_dashboards():
    d = await db.get_db()
    cur = await d.execute(
        """
        SELECT db.*,
               (SELECT COUNT(*) FROM widgets w WHERE w.dashboard_id = db.id) AS widget_count
        FROM dashboards db
        ORDER BY db.updated_at DESC
        """
    )
    return [dict(r) for r in await cur.fetchall()]


@router.post("/dashboards")
async def create_dashboard(body: DashboardIn):
    d = await db.get_db()
    cur = await d.execute(
        "INSERT INTO dashboards (name, description) VALUES (?, ?)",
        (body.name.strip(), body.description.strip()),
    )
    await d.commit()
    return {"id": cur.lastrowid, "name": body.name.strip(), "description": body.description.strip()}


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard(dashboard_id: int):
    d = await db.get_db()
    cur = await d.execute("SELECT * FROM dashboards WHERE id=?", (dashboard_id,))
    dash = await cur.fetchone()
    if not dash:
        raise HTTPException(404, "Dashboard nicht gefunden")
    cur = await d.execute("SELECT * FROM widgets WHERE dashboard_id=? ORDER BY id", (dashboard_id,))
    widgets = []
    for r in await cur.fetchall():
        w = dict(r)
        try:
            w["config"] = json.loads(w["config"] or "{}")
            w["grid"] = json.loads(w["grid"] or "{}")
        except Exception:
            w["config"] = {}
            w["grid"] = {}
        widgets.append(w)
    return {"dashboard": dict(dash), "widgets": widgets}


@router.patch("/dashboards/{dashboard_id}")
async def patch_dashboard(dashboard_id: int, body: DashboardPatch):
    d = await db.get_db()
    sets = []
    params: list = []
    if body.name is not None:
        sets.append("name = ?")
        params.append(body.name.strip())
    if body.description is not None:
        sets.append("description = ?")
        params.append(body.description.strip())
    if not sets:
        raise HTTPException(400, "nichts zu ändern")
    sets.append("updated_at = datetime('now')")
    params.append(dashboard_id)
    cur = await d.execute(f"UPDATE dashboards SET {', '.join(sets)} WHERE id = ?", params)
    await d.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Dashboard nicht gefunden")
    return {"updated": True}


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(dashboard_id: int):
    d = await db.get_db()
    await d.execute("DELETE FROM dashboards WHERE id=?", (dashboard_id,))
    await d.commit()
    return {"deleted": True}


@router.post("/dashboards/{dashboard_id}/widgets")
async def create_widget(dashboard_id: int, body: WidgetIn):
    d = await db.get_db()
    cur = await d.execute("SELECT id FROM dashboards WHERE id=?", (dashboard_id,))
    if not await cur.fetchone():
        raise HTTPException(404, "Dashboard nicht gefunden")
    cur = await d.execute("SELECT COUNT(*) AS n FROM widgets WHERE dashboard_id=?", (dashboard_id,))
    y = (await cur.fetchone())["n"]
    grid = body.grid or {"x": 0, "y": y, "w": 6, "h": 4}
    cur = await d.execute(
        "INSERT INTO widgets (dashboard_id, type, title, config, grid) VALUES (?,?,?,?,?)",
        (dashboard_id, body.type, body.title, json.dumps(body.config or {}), json.dumps(grid)),
    )
    await d.commit()
    return {"id": cur.lastrowid, "type": body.type, "title": body.title, "config": body.config, "grid": grid}


@router.put("/widgets/{widget_id}")
async def update_widget(widget_id: int, body: WidgetIn):
    d = await db.get_db()
    cur = await d.execute(
        "UPDATE widgets SET type=?, title=?, config=?, grid=? WHERE id=?",
        (body.type, body.title, json.dumps(body.config or {}), json.dumps(body.grid or {}), widget_id),
    )
    await d.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Widget nicht gefunden")
    return {"updated": True}


@router.delete("/widgets/{widget_id}")
async def delete_widget(widget_id: int):
    d = await db.get_db()
    await d.execute("DELETE FROM widgets WHERE id=?", (widget_id,))
    await d.commit()
    return {"deleted": True}