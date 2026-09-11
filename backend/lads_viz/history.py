"""History-Zugriff: DB-first (lokaler sensor_values-Store) mit OPC-UA-Lückenfüllung.

Die Charts lesen primär aus der lokalen Zeitreihen-DB. Nur Segmente, die dort
fehlen (Anfang/Ende des Fensters oder Lücken > GAP_MS), werden per OPC UA
nachgeladen und per Write-through mitarchiviert — der nächste Aufruf desselben
Fensters kommt dann komplett aus der DB.
Dazu: Downsampling (LTTB) + Statistiken.
"""
from datetime import datetime, timezone

from asyncua import Client

MAX_RAW = 60000      # Obergrenze pro HistoryRead (Server liefert die jüngsten N)
DB_TOL_MS = 120_000  # Toleranz an den Fensterrändern (2 min)
GAP_MS = 600_000     # DB-Lücken > 10 min gelten als fehlend (Collector-Ausfall)
MAX_FILL = 3         # max. Nachlade-Requests pro Signal


def _dv_to_points(values) -> list:
    """DataValue-Liste → [(ts_ms, value)] aufsteigend, Nicht-Zahlen werden verworfen."""
    out = []
    for dv in values or []:
        if dv.SourceTimestamp is None:
            continue
        val = dv.Value.Value
        if val is None or isinstance(val, (dict, list, bool)):
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        out.append((dv.SourceTimestamp.timestamp() * 1000.0, num))
    out.sort(key=lambda p: p[0])
    return out


def missing_windows(points, start_ms, end_ms, tol_ms=DB_TOL_MS, gap_ms=GAP_MS, max_fill=MAX_FILL):
    """Segmente in [start_ms, end_ms], die in `points` fehlen — für OPC-UA-Nachladen.

    Berücksichtigt Anfang/Ende (mit Toleranz) und die größten Mittellücken
    (durch Collector-Ausfälle), begrenzt auf max_fill Segmente.
    """
    if not points:
        return [(start_ms, end_ms)]
    windows = []
    first, last = points[0][0], points[-1][0]
    if first - start_ms > tol_ms:
        windows.append((start_ms, first))
    if end_ms - last > tol_ms:
        windows.append((last, end_ms))
    gaps = []
    for i in range(1, len(points)):
        d = points[i][0] - points[i - 1][0]
        if d > gap_ms:
            gaps.append((d, points[i - 1][0], points[i][0]))
    gaps.sort(reverse=True)
    for _d, a, b in gaps[: max(0, max_fill - len(windows))]:
        windows.append((a, b))
    return sorted(windows)


def merge_points(db_points, filled) -> list:
    """DB-Punkte + nachgeladene Punkte zusammenführen (nach ts dedupliziert, aufsteigend)."""
    seen = {}
    for ts, val in list(db_points) + list(filled):
        seen[round(float(ts))] = val
    return sorted(seen.items())


async def read_history(url: str, node_id: str, start, end) -> list:
    """Rohe History-Werte via OPC UA. Rückgabe: [(ts_ms, value), ...] aufsteigend."""
    client = Client(url=url, timeout=30)
    await client.connect()
    try:
        node = client.get_node(node_id)
        try:
            values = await node.read_raw_history(starttime=start, endtime=end, numvalues=MAX_RAW)
        except Exception:
            return []
        return _dv_to_points(values)
    finally:
        await client.disconnect()


async def read_histories(url: str, items, start_ms: int, end_ms: int) -> dict:
    """Mehrere Sensor-Historien in EINER Verbindung lesen (für Aggregation).

    items: [(signal_id, node_id), ...] → {signal_id: [(ts_ms, value), ...]}
    """
    client = Client(url=url, timeout=60)
    await client.connect()
    try:
        start = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
        end = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc)
        out: dict = {}
        for sid, nid in items:
            pts = []
            try:
                node = client.get_node(nid)
                values = await node.read_raw_history(starttime=start, endtime=end, numvalues=MAX_RAW)
                pts = _dv_to_points(values)
            except Exception:
                pts = []
            out[sid] = pts
        return out
    finally:
        await client.disconnect()


def lttb(points: list, threshold: int) -> list:
    """Largest-Triangle-Three-Buckets-Downsampling (z.B. 50k → 1500).

    points: [(x, y)] aufsteigend sortiert; behält die Kurvenform exakt.
    """
    if len(points) <= threshold or threshold < 2:
        return points
    threshold = min(threshold, len(points))
    sampled = [points[0]]
    every = (len(points) - 2) / (threshold - 2)
    a = 0
    for i in range(threshold - 2):
        avg_start = min(int((i + 1) * every) + 1, len(points))
        avg_end = min(int((i + 2) * every) + 1, len(points))
        avg_range = points[max(0, avg_start - 1):avg_end]
        if not avg_range:
            continue
        avg_x = sum(p[0] for p in avg_range) / len(avg_range)
        avg_y = sum(p[1] for p in avg_range) / len(avg_range)
        range_offs = min(int(i * every) + 1, len(points) - 1)
        range_to = min(int((i + 1) * every) + 1, len(points))
        a_x, a_y = points[a]
        max_area = -1.0
        chosen = range_offs
        for j in range(range_offs, range_to):
            x, y = points[j]
            area = abs((a_x - x) * (avg_y - a_y) - (a_x - avg_x) * (y - a_y))
            if area > max_area:
                max_area = area
                chosen = j
        sampled.append(points[chosen])
        a = chosen
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def compute_stats(points: list) -> dict:
    if not points:
        return {"count": 0}
    vals = [p[1] for p in points]
    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "avg": sum(vals) / len(vals),
        "last": vals[-1],
    }


def compute_energy_wh(points: list):
    """Trapez-Integration über ein W-Signal → Wh (für Stromverbrauch)."""
    if len(points) < 2:
        return None
    wh = 0.0
    for i in range(1, len(points)):
        dt_h = (points[i][0] - points[i - 1][0]) / 3_600_000.0
        wh += (points[i][1] + points[i - 1][1]) * 0.5 * dt_h
    return wh


# ── DB-first: Charts aus dem lokalen sensor_values-Store ─────────

async def read_history_db_first(server_url, node_id, signal_id, start_ms, end_ms):
    """Ein Signal: DB lesen, fehlende Fenster per OPC UA nachladen + archivieren.

    Rückgabe: (points, meta) mit meta = {source, db_points, filled_points, gap_windows}.
    source: 'db' | 'db+opcua' | 'opcua'
    """
    from . import db

    dbp = await db.read_values(signal_id, start_ms, end_ms)
    windows = missing_windows(dbp, start_ms, end_ms)
    filled = []
    if windows and node_id:
        for a, b in windows:
            try:
                pts = await read_history(
                    server_url, node_id,
                    datetime.fromtimestamp(a / 1000.0, tz=timezone.utc),
                    datetime.fromtimestamp(b / 1000.0, tz=timezone.utc),
                )
            except Exception:
                pts = []
            if pts:
                filled.extend(pts)
                try:
                    await db.insert_values(signal_id, pts)
                except Exception:
                    pass  # Archivierung darf die Antwort nicht verhindern
    points = merge_points(dbp, filled)
    source = "db" if not filled else ("db+opcua" if dbp else "opcua")
    meta = {
        "source": source,
        "db_points": len(dbp),
        "filled_points": len(filled),
        "gap_windows": len(windows),
    }
    return points, meta


async def read_histories_db_first(url, items, start_ms, end_ms):
    """Mehrere Signale (Aggregation): DB-first, Lücken in EINER OPC-UA-Verbindung.

    items: [(signal_id, node_id), ...] → ({sid: points}, {sid: meta})
    """
    from . import db

    out: dict = {}
    metas: dict = {}
    need = []  # (sid, node_id, windows)
    for sid, nid in items:
        dbp = await db.read_values(sid, start_ms, end_ms)
        wins = missing_windows(dbp, start_ms, end_ms)
        out[sid] = dbp
        metas[sid] = {"source": "db", "db_points": len(dbp), "filled_points": 0, "gap_windows": len(wins)}
        if wins and nid:
            need.append((sid, nid, wins))
    if need:
        start = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
        end = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc)
        client = Client(url=url, timeout=60)
        try:
            await client.connect()
            for sid, nid, wins in need:
                filled = []
                try:
                    node = client.get_node(nid)
                    for a, b in wins:
                        try:
                            values = await node.read_raw_history(
                                starttime=datetime.fromtimestamp(a / 1000.0, tz=timezone.utc),
                                endtime=datetime.fromtimestamp(b / 1000.0, tz=timezone.utc),
                                numvalues=MAX_RAW,
                            )
                            filled.extend(_dv_to_points(values))
                        except Exception:
                            continue
                except Exception:
                    pass
                if filled:
                    try:
                        await db.insert_values(sid, filled)
                    except Exception:
                        pass
                    out[sid] = merge_points(out[sid], filled)
                    metas[sid]["filled_points"] = len(filled)
                    metas[sid]["source"] = "db+opcua" if out[sid] and len(out[sid]) > len(filled) else "opcua"
        finally:
            await client.disconnect()
    return out, metas