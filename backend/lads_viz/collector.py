"""Collector: überwachte Sensoren zyklisch lesen und ins sensor_values-Store schreiben.

Eigenes Zeitreihen-Store als Absicherung (unabhängig vom Server-History-Puffer):
läuft als Hintergrund-Task, liest alle `historizing=1`-Signale (kein manuelles
Anschalten nötig) in EINER OPC-UA-Verbindung und schreibt append-only
(INSERT OR IGNORE). Robuster Umgang mit ns-Wandel/Bad-Status: einzelne Fehler
werden übersprungen, der Loop läuft weiter.
"""
import asyncio
import logging
import time

from asyncua import Client

from . import config, db

log = logging.getLogger("lads_viz.collector")

DEFAULT_INTERVAL_S = 30


async def _read_batch(node_ids) -> dict:
    """Aktuelle Werte mehrerer nodeIds in einer Verbindung → {node_id: (ts_ms, value)}."""
    out: dict = {}
    client = Client(url=config.OPC_URL, timeout=30)
    try:
        await client.connect()
        now_ms = int(time.time() * 1000)
        for nid in node_ids:
            try:
                node = client.get_node(nid)
                dv = await node.read_data_value()
                if not (dv.StatusCode.is_good() if hasattr(dv.StatusCode, "is_good") else True):
                    continue
                val = dv.Value.Value
                if isinstance(val, bool):
                    val = float(val)
                elif not isinstance(val, (int, float)):
                    continue
                ts = dv.SourceTimestamp or dv.ServerTimestamp
                ts_ms = int(ts.timestamp() * 1000) if ts else now_ms
                out[nid] = (ts_ms, float(val))
            except Exception:
                continue  # einzelner Sensor fehlerhaft (Bad/ns-Wandel) → überspringen
    except Exception:
        log.exception("Collector: OPC-UA-Verbindung fehlgeschlagen")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    return out


async def run(interval: int = DEFAULT_INTERVAL_S) -> None:
    """Endlos-Loop: alle N Sekunden überwachte Signale einsammeln."""
    log.info("Viz-Collector gestartet (Interval %ss)", interval)
    while True:
        try:
            sigs = await db.collectable_signals()
            if sigs:
                vals = await _read_batch([s["node_id"] for s in sigs])
                for s in sigs:
                    v = vals.get(s["node_id"])
                    if v is not None:
                        await db.insert_values(s["id"], [v])
        except Exception:
            log.exception("Collector-Zyklus fehlgeschlagen (non-fatal)")
        await asyncio.sleep(interval)
