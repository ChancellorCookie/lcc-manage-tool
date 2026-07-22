"""Fragt die Monitoring-REST-API ab und liefert eine Liste offener Incidents.

Nutzt die geteilte OAuth2-Auth (backend.auth) und den LCC-Basis-Client
(backend.lcc_client) statt eigener Auth-Logik und requests.

Die Zuordnung der JSON-Felder zum Incident-Modell ist komplett ueber die
Konfiguration steuerbar (response.fields), damit der Dienst an die konkrete
API der Monitoring-Software angepasst werden kann, ohne Code zu aendern.
"""
import logging
import time

import httpx

from backend.auth import get_token
from backend.lcc_client import LCC_BASE

from .config import get_by_path
from .models import Incident

log = logging.getLogger("notifier.poller")


class Poller:
    def __init__(self, config: dict):
        self.c = config
        self.url_template = config.get("incident_url_template", "")
        self.query_params = config.get("query_params", {}) or {}
        self.pg = config.get("pagination", {}) or {}
        self.report_cfg = config.get("report_incident", {}) or {}
        self.rooms_cfg = config.get("rooms", {}) or {}
        self._rooms_cache = None  # {"data": [...], "fetched_at": float}

    @property
    def _verify_tls(self) -> bool:
        return self.c.get("verify_tls", False)

    async def _client(self) -> httpx.AsyncClient:
        """Build an AsyncClient with the current OAuth2 bearer token."""
        token = await get_token()
        return httpx.AsyncClient(
            verify=self._verify_tls,
            headers={
                "Authorization": f"Bearer {token}",
                "Host": "lcc.ieu.local",
            },
        )

    async def _fetch_rooms(self):
        if not self.rooms_cfg.get("enabled", False):
            return
        cache_ttl = int(self.rooms_cfg.get("cache_seconds", 300))
        now = time.time()
        if self._rooms_cache and now - self._rooms_cache["fetched_at"] < cache_ttl:
            return

        rooms_url = self.rooms_cfg.get("url", "")
        if not rooms_url:
            return

        log.info("Hole Raum-Daten von %s", rooms_url)
        try:
            client = await self._client()
            try:
                resp = await client.get(
                    rooms_url,
                    timeout=self.c.get("timeout_seconds", 10),
                )
                resp.raise_for_status()
                data = resp.json()
            finally:
                await client.aclose()

            items = get_by_path(data, self.rooms_cfg.get("items_path", "data")) or []
            if not isinstance(items, list):
                log.warning("rooms items_path lieferte kein Array")
                return
            self._rooms_cache = {"data": items, "fetched_at": now}
            log.info("%d Raeume geladen", len(items))
        except Exception:
            log.exception("Fehler beim Laden der Raum-Daten")

    def _enrich_room(self, inc: Incident):
        cache = self._rooms_cache
        if not cache:
            return

        for room in cache["data"]:
            monitoring = room.get("monitoring") or []
            for mon in monitoring:
                mon_path = mon.get("path", "")
                if not mon_path:
                    continue
                if inc.source.startswith(mon_path) or mon_path.startswith(inc.source):
                    contact = room.get("contact") or {}
                    inc.room_name = room.get("name", "")
                    inc.room_number = room.get("number", "")
                    inc.room_contact_name = contact.get("name", "")
                    inc.room_contact_email = contact.get("email", "")
                    inc.room_contact_details = contact.get("details", "")
                    return

    async def report_incident(self, incident_id: str, comment: str = ""):
        """Markiert einen Incident in der LCC API als 'reported'
        (Eskalations-Schritt dokumentiert).

        POST /lads/alarms/{incidentId}/report"""
        enabled = bool(self.report_cfg.get("enabled", False))
        if not enabled:
            log.debug("report_incident deaktiviert, ueberspringe %s", incident_id)
            return

        url_tpl = self.report_cfg.get(
            "url_template", "{base_url}/lads/alarms/{incident_id}/report"
        )
        base = self.c.get("url", LCC_BASE).replace("/api/v2/incidents", "")
        url = url_tpl.format(base_url=base, incident_id=incident_id)

        payload = {"comment": comment} if comment else {}

        log.info("report_incident: POST %s (comment=%s)", url, comment or "-")
        try:
            client = await self._client()
            try:
                resp = await client.post(
                    url,
                    json=payload if payload else None,
                    timeout=self.c.get("timeout_seconds", 10),
                )
            finally:
                await client.aclose()

            if resp.status_code in (200, 204):
                log.info(
                    "Incident %s erfolgreich als reported markiert", incident_id
                )
            else:
                log.warning(
                    "report_incident fehlgeschlagen: HTTP %s - %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception:
            log.exception("report_incident fuer %s fehlgeschlagen", incident_id)

    async def fetch(self):
        await self._fetch_rooms()

        c = self.c
        rcfg = c.get("response", {})
        fields = rcfg.get("fields", {})
        allowed = set(c.get("severities", [])) or None

        all_items = []
        offset = 0
        limit = self.pg.get("page_size", 0)

        client = await self._client()
        try:
            while True:
                params = dict(self.query_params)
                if limit > 0:
                    params[self.pg.get("offset_param", "offset")] = offset
                    params[self.pg.get("limit_param", "limit")] = limit

                resp = await client.request(
                    c.get("method", "GET"),
                    c["url"],
                    params=params or None,
                    timeout=c.get("timeout_seconds", 10),
                )
                resp.raise_for_status()
                data = resp.json()

                items = get_by_path(data, rcfg.get("items_path", "")) or []
                if not isinstance(items, list):
                    log.warning("items_path lieferte kein Array, ignoriere Antwort")
                    return []

                for item in items:
                    inc = self._map(item, fields)
                    if allowed and inc.severity not in allowed:
                        continue
                    self._enrich_room(inc)
                    all_items.append(inc)

                if limit <= 0:
                    break

                total_path = self.pg.get("total_path", "")
                total = get_by_path(data, total_path) if total_path else 0
                if not total:
                    total = len(items)
                offset += len(items)
                if offset >= total:
                    break
        finally:
            await client.aclose()

        return all_items

    def _map(self, item: dict, fields: dict) -> Incident:
        def f(name, default=""):
            path = fields.get(name)
            if not path:
                return default
            val = get_by_path(item, path)
            return default if val is None else val

        def fbool(name, default=False):
            path = fields.get(name)
            if not path:
                return default
            val = get_by_path(item, path)
            return bool(val) if val is not None else default

        def ffloat(name, default=None):
            path = fields.get(name)
            if not path:
                return default
            val = get_by_path(item, path)
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        inc = Incident(
            id=str(f("id")),
            title=str(f("title", "Unbenannter Incident")),
            severity=str(f("severity", "info")).lower(),
            source=str(f("source", "")),
            description=str(f("description", "")),
            timestamp=f("timestamp", None),
            status=str(f("status", "open")),
            url=str(f("url", "")),
            raw=item,

            max_severity=str(f("max_severity", "")).lower(),
            help=str(f("help", "")),
            comment=str(f("comment", "")),
            acknowledged=fbool("acknowledged"),
            confirmed=fbool("confirmed"),
            reported=fbool("reported"),
            flap_count=int(f("flap_count", 0) or 0),
            strict_audited=fbool("strict_audited"),
            active=fbool("active", True),
            event_id=str(f("event_id", "")),
            high_high_limit=ffloat("high_high_limit"),
            high_limit=ffloat("high_limit"),
            low_limit=ffloat("low_limit"),
            low_low_limit=ffloat("low_low_limit"),
        )
        if not inc.url and self.url_template:
            inc.url = self.url_template.format(id=inc.id)
        return inc
