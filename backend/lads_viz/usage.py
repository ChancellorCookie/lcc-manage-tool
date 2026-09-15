"""Nutzungsanalyse: Hysterese auf der Summen-Serie mehrerer Indikator-Signale.

Logik (ein Gerät, mehrere Plugs/Sensoren):
  - Summe aller Signale W = Trigger-Kurve (Step-Interpolation)
  - Wert >= Startschwelle  -> Gerät "aktiv" (Nutzung beginnt)
  - Wert <= Unterschwelle  -> Gerät "ruhend" (Nutzung endet)
  - Startschwelle muss > Unterschwelle sein (Hysterese gegen Flackern)
  - Lücken > 30 min gelten als offline (zählen weder online noch Aktivzeit)
  - Auslastung % = Aktivzeit / Online-Zeit der Sensoren
"""
import logging

from . import db, history

log = logging.getLogger("lads_viz.usage")

GAP_MS = 30 * 60_000  # > 30 min ohne Daten = offline


async def usage_analysis(signal_ids, start_ms, end_ms, start_threshold, stop_threshold):
    if start_threshold <= 0:
        raise ValueError("start_threshold muss > 0 sein")
    if stop_threshold >= start_threshold:
        raise ValueError("stop_threshold muss kleiner als start_threshold sein")

    d = await db.get_db()
    ph = ",".join("?" * len(signal_ids))
    cur = await d.execute(
        f"""SELECT s.id, s.node_id, s.browse_name, s.engineering_unit AS unit,
                   dev.component_name AS device, dev.hierarchical_location AS location,
                   srv.url AS server_url
            FROM signals s
            JOIN devices dev ON dev.id = s.device_id
            JOIN servers srv ON srv.id = dev.server_id
            WHERE s.id IN ({ph})""",
        list(signal_ids),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        raise KeyError("keine Signale gefunden")
    if len(rows) < len(signal_ids):
        found = {r["id"] for r in rows}
        missing = [i for i in signal_ids if i not in found]
        raise KeyError(f"Signale nicht gefunden: {missing}")

    by_url: dict = {}
    for r in rows:
        by_url.setdefault(r["server_url"], []).append((r["id"], r["node_id"]))
    raw: dict = {}
    for url, items in by_url.items():
        rr, _ = await history.read_histories_db_first(url, items, start_ms, end_ms)
        raw.update(rr)

    return analyze(raw, rows, start_ms, end_ms, start_threshold, stop_threshold)


def analyze(raw, rows, start_ms, end_ms, s_thr, p_thr):
    """raw: {signal_id: [(ts_ms, value), ...]} -> Schritt-Summen-Serie + Intervalle."""
    # Events sortiert; Summe je Zeitpunkt = Summe der letzten bekannten Werte aller Signale
    last: dict = {}
    cur_sum = 0.0
    last_data_ms = None
    steps = []  # (from_ms, to_ms, sum)
    merged = []
    for row in rows:
        for ts, val in raw.get(row["id"], []):
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            merged.append((int(ts), row["id"], v))
    merged.sort(key=lambda e: e[0])

    ids_seen: set = set()  # noqa (nur zur Klarheit, nicht genutzt)
    for ts, sid, v in merged:
        if last_data_ms is not None and ts > last_data_ms:
            steps.append((last_data_ms, ts, cur_sum))
        if sid in last:
            cur_sum += v - last[sid]
        else:
            cur_sum += v
        last[sid] = v
        last_data_ms = ts

    # Rest bis end_ms (nur wenn letzter Datenpunkt nah genug dran ist)
    if last_data_ms is not None and last_data_ms < end_ms:
        d = end_ms - last_data_ms
        if d <= GAP_MS:
            steps.append((last_data_ms, end_ms, cur_sum))

    # Hysterese über die Step-Summen
    intervals = []
    state = False
    cur_start = None
    prev_from = None
    for i, (f, t, s) in enumerate(steps):
        if prev_from is not None and f - prev_from > GAP_MS:
            # Lücke -> Zyklus zurücksetzen
            if state and cur_start is not None:
                intervals.append({"start": cur_start, "end": steps[i - 1][1]})
                state = False
                cur_start = None
        prev_from = f
        if not state and s >= s_thr:
            state = True
            cur_start = f
        elif state and s <= p_thr:
            intervals.append({"start": cur_start, "end": t})
            state = False
            cur_start = None
    if state and cur_start is not None:
        last_end = steps[-1][1] if steps else end_ms
        intervals.append({"start": cur_start, "end": last_end})

    # Kennzahlen
    active_s = sum((iv["end"] - iv["start"]) for iv in intervals) / 1000.0
    online_s = sum((t - f) for f, t, _ in steps) / 1000.0
    count = len(intervals)
    pct = (active_s / online_s * 100.0) if online_s > 0 else 0.0
    current_w = cur_sum
    current_active = state and last_data_ms is not None and (end_ms - last_data_ms <= GAP_MS)

    return {
        "intervals": [{"start": iv["start"], "end": iv["end"]} for iv in intervals],
        "stats": {
            "active_s": round(active_s, 1),
            "online_s": round(online_s, 1),
            "count": count,
            "avg_s": round(active_s / count, 1) if count else 0.0,
            "pct": round(pct, 1),
            "current_w": round(current_w, 1),
            "current_active": current_active,
        },
        "signals": [
            {"id": r["id"], "device": r["device"], "browse_name": r["browse_name"], "unit": r["unit"]}
            for r in rows
        ],
        "window": {"start": start_ms, "end": end_ms},
    }