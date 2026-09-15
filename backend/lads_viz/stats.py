"""Verbrauchs-Statistiken: kWh-/Kosten-Aggregation in Zeit-Buckets (Tag/Woche/Monat).

Basis: rohe OPC-UA-HistoryRead-Werte (history.read_histories). Keine Zeitreihen-DB —
TimescaleDB würde später nur diese Schicht ersetzen. Tages-/Wochen-/Monatsgrenzen
in Europe/Berlin; Segmente werden an Bucket-Grenzen geclippt, Lücken über einer
Schwelle werden NICHT als Energie überbrückt (Gap-Guard) und markieren 'partial'.
"""
import bisect
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
GAP_MAX_MS = 30 * 60 * 1000  # Lücken > 30 min gelten als Unterbrechung (kein Phantom-Strom)

# TTL-Cache (Millisekunden): wiederholte Abfragen frisch aus dem Speicher
_CACHE: dict = {}
_CACHE_TTL_MS = 60_000


def _floor_local(ms: int, bucket: str) -> int:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=TZ)
    if bucket == "hour":
        dt = dt.replace(minute=0, second=0, microsecond=0)
    elif bucket == "day":
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif bucket == "week":
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=dt.weekday())
    elif bucket == "month":
        dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(dt.timestamp() * 1000)


def _next(ms: int, bucket: str) -> int:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=TZ)
    if bucket == "hour":
        ndt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif bucket == "day":
        ndt = dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif bucket == "week":
        d = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=dt.weekday())
        ndt = d + timedelta(days=7)
    else:  # month
        ndt = (dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
    return int(ndt.timestamp() * 1000)


def _label(ms: int, bucket: str) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=TZ)
    if bucket == "hour":
        return dt.strftime("%a %d.%m. %H:00")
    if bucket == "day":
        return dt.strftime("%a %d.%m.")
    if bucket == "week":
        return f"KW{dt.isocalendar()[1]} ({dt.strftime('%d.%m.')})"
    return dt.strftime("%b %Y")


def gen_bounds(start_ms: int, end_ms: int, bucket: str):
    """Kalender-bündige Buckets, die [start,end] überdecken, auf das Fenster geclippt."""
    bounds = []
    cur = _floor_local(start_ms, bucket)
    while cur < end_ms:
        nxt = _next(cur, bucket)
        bs = max(cur, start_ms)
        be = min(nxt, end_ms)
        if be > bs:
            bounds.append((bs, be, _label(cur, bucket)))
        cur = nxt
    return bounds


def auto_bucket(start_ms: int, end_ms: int) -> str:
    span_days = (end_ms - start_ms) / 86_400_000.0
    if span_days <= 2:
        return "hour"
    if span_days <= 90:
        return "day"
    if span_days <= 400:
        return "week"
    return "month"


def _interp(t0, t1, v0, v1, t):
    if t1 == t0:
        return v1
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def energy_avg_per_bucket(points, bounds, start_ms, end_ms, gap_max_ms=GAP_MAX_MS):
    """→ (wh[], avg[], partial[], coverage_h[]): Trapez-kWh je Bucket, geclippt.

    - Segmente, die über eine Bucket-Grenze laufen, werden aufgeteilt/interpoliert
    - Segmente außerhalb des Zeitfensters werden beschnitten
    - Lücke > gap_max_ms → keine Energie, Bucket wird 'partial'
    """
    n = len(bounds)
    wh = [0.0] * n
    tavg = [0.0] * n
    cov = [0.0] * n  # Abdeckungsstunden je Bucket
    partial = [False] * n
    bstarts = [b[0] for b in bounds]
    if not points or len(points) < 2:
        return wh, [None] * n, partial, cov
    for i in range(1, len(points)):
        t0 = points[i - 1][0]
        t1 = points[i][0]
        if t1 <= start_ms or t0 >= end_ms or t1 <= t0:
            continue
        s = max(t0, start_ms)
        e = min(t1, end_ms)
        if e <= s:
            continue
        gap = (t1 - t0) > gap_max_ms
        i0 = max(0, bisect.bisect_right(bstarts, s) - 1)
        i1 = min(n - 1, bisect.bisect_right(bstarts, e) - 1)
        if i0 > i1:
            continue
        for bi in range(i0, i1 + 1):
            bs, be, _ = bounds[bi]
            ss = max(s, bs)
            ee = min(e, be)
            if ee <= ss:
                continue
            vss = _interp(t0, t1, points[i - 1][1], points[i][1], ss)
            vee = _interp(t0, t1, points[i - 1][1], points[i][1], ee)
            dt_h = (ee - ss) / 3_600_000.0
            if not gap:
                wh[bi] += 0.5 * (vss + vee) * dt_h
            tavg[bi] += 0.5 * (vss + vee) * dt_h
            cov[bi] += dt_h
            if gap:
                partial[bi] = True
    avgs = [(tavg[k] / cov[k]) if cov[k] > 0 else None for k in range(n)]
    return wh, avgs, partial, cov


def window_summary(points, start_ms, end_ms, gap_max_ms=GAP_MAX_MS):
    """Ein einzelnes Fenster: (wh, avg_w, partial, coverage_h) — Wrapper um energy_avg_per_bucket."""
    bounds = [(start_ms, end_ms, "window")]
    wh, avg, partial, cov = energy_avg_per_bucket(points, bounds, start_ms, end_ms, gap_max_ms)
    return wh[0] if wh else 0.0, avg[0] if avg else None, (partial[0] if partial else False), (cov[0] if cov else 0.0)


def consumption(signals_meta, raw, start_ms, end_ms, bucket, eur_kwh):
    """Aggregiert zu Verbrauchs-Buckets. signals_meta: [{id, unit, device, location}]."""
    if bucket == "auto":
        bucket = auto_bucket(start_ms, end_ms)
    bounds = gen_bounds(start_ms, end_ms, bucket)
    n = len(bounds)
    total_wh = [0.0] * n
    partial = [False] * n
    per_signal_bucket = {}
    signal_stats = []
    for m in signals_meta:
        sid = m["id"]
        u = (m.get("unit") or "").lower()
        is_power = u in ("w", "kw", "wh", "mwh")
        pts = raw.get(sid, [])
        wh_pts, _, part_pts, _cov = energy_avg_per_bucket(pts, bounds, start_ms, end_ms)
        col = wh_pts if is_power else [None] * n
        per_signal_bucket[sid] = col
        mysum = sum(v for v in col if v is not None)
        signal_stats.append({
            "id": sid,
            "device": m.get("device") or m.get("browse_name") or f"Sensor {sid}",
            "location": m.get("location") or "",
            "unit": m.get("unit") or "",
            "wh": round(mysum, 3),
            "kwh": round(mysum / 1000.0, 4),
            "cost": round(mysum / 1000.0 * eur_kwh, 2),
        })
        for k in range(n):
            if is_power and col[k] is not None:
                total_wh[k] += col[k]
            if part_pts[k]:
                partial[k] = True
    buckets = []
    for k in range(n):
        bs, be, label = bounds[k]
        by_signal = {
            str(sid): (round(per_signal_bucket[sid][k] / 1000.0, 4) if per_signal_bucket[sid][k] is not None else 0)
            for sid in per_signal_bucket
        }
        buckets.append({
            "t": label,
            "ts": bs,
            "end": be,
            "kwh": round(total_wh[k] / 1000.0, 4),
            "wh": round(total_wh[k], 3),
            "cost": round(total_wh[k] / 1000.0 * eur_kwh, 2),
            "partial": partial[k],
            "by_signal": by_signal,
        })
    # Raum-Gruppierung
    locs = {}
    for s in signal_stats:
        loc = s["location"] or "(ohne Standort)"
        locs.setdefault(loc, {"kwh": 0.0, "cost": 0.0})
        locs[loc]["kwh"] += s["kwh"]
        locs[loc]["cost"] += s["cost"]
    by_location = [{"location": k, "kwh": round(v["kwh"], 4), "cost": round(v["cost"], 2)}
                   for k, v in locs.items()]
    total_wh_sum = sum(total_wh)
    return {
        "bucket": bucket,
        "eur_kwh": eur_kwh,
        "start": start_ms,
        "end": end_ms,
        "buckets": buckets,
        "signals": signal_stats,
        "by_location": by_location,
        "totals": {
            "kwh": round(total_wh_sum / 1000.0, 4),
            "wh": round(total_wh_sum, 3),
            "cost": round(total_wh_sum / 1000.0 * eur_kwh, 2),
        },
    }


def cached(fn):
    async def wrapper(*args):
        now = time.time() * 1000
        key = (fn.__name__, args)
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL_MS:
            return hit[1]
        result = await fn(*args)
        _CACHE[key] = (now, result)
        return result
    return wrapper


def clear_cache():
    """Nach Config-Änderungen (z. B. Strompreis) leeren, damit Kachel-Kosten frisch sind."""
    _CACHE.clear()


# ── Widget-Quickinfos (Startseiten-Kacheln) ───────────────────

TYPE_TITLES = {
    "usage": "Nutzungsanalyse",
    "usagestats": "Nutzungs-Kacheln",
    "usageline": "Nutzungs-Historie",
    "linechart": "Linechart",
    "charttable": "Leistung & Tabelle",
    "stat": "Statistik",
    "table": "Tabelle",
}


def widget_quickinfo(widget, sums, eur_kwh):
    """Kurz-Kennzahlen eines Widgets für die Startseiten-Kachel (oberflächlich, DB-first).

    widget: {"type", "title", "config", "signals": [sid]}
    sums:   {sid: {"latest", "is_power", "wh", "unit"}}
    -> {"kind": "usage"|"power"|"value", "metrics": [...], ...} oder None.
    - usage/usagestats/usageline: Summe der letzten Werte vs. Schwellen -> Live-Status
      (bewusst ohne vollen Hysterese-Lauf; state: use/idle/coast/nodata)
    - charttable + bar (Leistung & Tabelle): kWh/Kosten/Leistung im Fenster
    - stat / linechart ohne bar: letzter Wert des ersten Signals
    """
    t = widget.get("type") or ""
    cfg = widget.get("config") or {}
    sids = [s for s in (widget.get("signals") or []) if s in sums]
    pws = [s for s in sids if sums[s]["is_power"]]
    live = [s for s in pws if sums[s].get("latest") is not None]
    if t in ("usage", "usagestats", "usageline"):
        cur = round(sum(sums[s]["latest"] for s in live), 1)
        if not pws or not live:
            state, label = "nodata", "–"
        else:
            st_thr = float(cfg.get("startThreshold") or 600)
            sp_thr = float(cfg.get("stopThreshold") or 100)
            if cur >= st_thr:
                state, label = "use", "In Nutzung"
            elif cur <= sp_thr:
                state, label = "idle", "Ruhend"
            else:
                state, label = "coast", "Auslaufend"
        return {"kind": "usage", "metrics": ["status", "w"],
                "state": state, "state_label": label, "current_w": cur}
    if t in ("charttable", "linechart"):
        bar = t == "charttable" or cfg.get("mode") == "bar"
        if bar and pws:
            kw = round(sum(sums[s]["wh"] for s in pws) / 1000.0, 2)
            return {"kind": "power", "metrics": ["kwh", "cost", "w"],
                    "kwh": kw,
                    "cost": round(kw * eur_kwh, 2),
                    "current_w": round(sum(sums[s]["latest"] for s in live), 1) if live else None}
        if sids:
            s0 = sids[0]
            v = sums[s0].get("latest")
            if v is not None:
                return {"kind": "value", "metrics": ["value"],
                        "value": v, "unit": sums[s0].get("unit") or ""}
    if t == "stat" and sids:
        s0 = sids[0]
        v = sums[s0].get("latest")
        if v is not None:
            return {"kind": "value", "metrics": ["value"],
                    "value": v, "unit": sums[s0].get("unit") or ""}
    return None