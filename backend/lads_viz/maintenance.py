"""Periodischer Auto-Rediscover: heilt ns-Rebuilds ohne manuelles Discover.

Server können ihren Adressraum (Namespace-Indizes) bei Neustart neu aufbauen —
gespeicherte node_ids werden dann stale (BadNodeIdUnknown). Dieser Task re-browst
regelmäßig alle Server und repariert die node_ids automatisch.
"""
import asyncio
import logging

from . import db, sync

log = logging.getLogger("lads_viz.maintenance")

INTERVAL_S = 600  # alle 10 Minuten


async def run(interval: int = INTERVAL_S) -> None:
    log.info("Auto-Rediscover gestartet (alle %ss)", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            d = await db.get_db()
            cur = await d.execute("SELECT id FROM servers")
            servers = [r["id"] for r in await cur.fetchall()]
            for sid in servers:
                await sync.rediscover(sid)
            if servers:
                log.info("Auto-Rediscover abgeschlossen (%d Server)", len(servers))
        except Exception:
            log.exception("Auto-Rediscover fehlgeschlagen (non-fatal)")
