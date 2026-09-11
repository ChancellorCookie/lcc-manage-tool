"""OPC-UA HistoryRead on-demand + Downsampling (LTTB) + Statistiken.

Keine Zeitreihen-DB: Die Dashboards lesen Historien direkt vom OPC-UA-Server.
Die TimescaleDB ersetzt später nur diese Schicht (gleiche API dahinter).
"""
from datetime import datetime, timezone

from asyncua import Client

MAX_RAW = 60000  # Obergrenze pro HistoryRead (Server liefert die jüngsten N)


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
        out = []
        for dv in values:
            if dv.SourceTimestamp is None:
                continue
            val = dv.Value.Value
            if val is None or isinstance(val, (dict, list)):
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            out.append((dv.SourceTimestamp.timestamp() * 1000.0, num))
        out.sort(key=lambda p: p[0])
        return out
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
                for dv in values:
                    if dv.SourceTimestamp is None:
                        continue
                    val = dv.Value.Value
                    if val is None or isinstance(val, (dict, list)):
                        continue
                    try:
                        num = float(val)
                    except (TypeError, ValueError):
                        continue
                    pts.append((dv.SourceTimestamp.timestamp() * 1000.0, num))
                pts.sort(key=lambda p: p[0])
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