"""ELN-Kanal (Electronic Lab Notebook) - 'labnote lite' Notifications.

API: POST {base_url}/v1/notifications (Body-Schema: NotificationCreate).
API-Doku: alle Anfragen benoetigen 'Authorization: Bearer <token>'.
Drei Auth-Methoden werden unterstuetzt:
  - api_key         Org-Key 'lk_live_...' fuer Server-zu-Server (read|write|admin).
  - personal_token  User-Token 'lp_...' mit zusaetzlicher org_id
                    (Header 'X-Org-Id' oder Query-Param '?org_id=...').
  - oauth2          Authorization Code Flow + Refresh Token.
                    Initialer Login erfolgt einmalig manuell im Browser;
                    access_token + refresh_token werden in der Config
                    hinterlegt. Refresh laeuft automatisch im Hintergrund.
  - bearer          generischer Bearer (manuelles Access Token).

Empfaenger-Konfiguration (genau EINE der drei Optionen erforderlich):
  - recipient_user_id:    einzelne User-UUID
  - recipient_user_ids:   Liste von 1-500 User-UUIDs
  - recipient_role:       Rollenname (z.B. 'admin')
"""
import logging
import time

import requests

from .base import Channel
from ..formatting import body as _body, resolved_body, resolved_subject, subject as _subject
from ..models import Incident


log = logging.getLogger("notifier.eln")

_TITLE_MAX = 200
_BODY_MAX = 2000


class ElnChannel(Channel):
    def __init__(self, name, config, templates_cfg=None):
        super().__init__(name, config, templates_cfg)
        self.base_url = (config.get("base_url") or "").rstrip("/")
        self.verify_tls = config.get("verify_tls", True)
        self.timeout = int(config.get("timeout_seconds", 10))
        self.session = requests.Session()
        self._access_token = ""
        self._refresh_token = ""
        self._token_expires_at = 0.0

        self.notification_type = config.get("notification_type", "lcc_alarm")
        self.recipient = self._resolve_recipient(config)

        auth = config.get("auth", {}) or {}
        atype = auth.get("type", "none")

        if atype in ("api_key", "personal_token", "bearer"):
            self.session.headers["Authorization"] = f"Bearer {auth.get('token', '')}"
            if atype == "personal_token":
                self._apply_org_id(auth)
        elif atype == "oauth2":
            self._access_token = auth.get("access_token", "")
            self._refresh_token = auth.get("refresh_token", "")
            self._token_expires_at = time.time() + int(auth.get("expires_in", 3600))
            if self._access_token:
                self.session.headers["Authorization"] = f"Bearer {self._access_token}"
            else:
                log.warning("ELN '%s': oauth2 konfiguriert, aber access_token fehlt - "
                            "einmaliger Browser-Login noetig", name)
        else:
            log.warning("ELN '%s': unbekannter auth.type '%s' "
                        "(erwartet: api_key|personal_token|oauth2|bearer|none)", name, atype)

        if self.recipient is None:
            log.warning("ELN '%s': kein Empfaenger konfiguriert "
                        "(recipient_user_id, recipient_user_ids oder recipient_role) - "
                        "send() wird fehlschlagen", name)

    def _resolve_recipient(self, config: dict) -> dict | None:
        """Liest genau eine Empfaenger-Option aus der Config und gibt sie als
        {api_field: value} zurueck (api_field = user_id|user_ids|role).
        None wenn keine oder mehrere gesetzt sind."""
        mapping = {
            "recipient_user_id": "user_id",
            "recipient_user_ids": "user_ids",
            "recipient_role": "role",
        }
        provided = {api: config.get(cfg_key)
                    for cfg_key, api in mapping.items() if config.get(cfg_key)}
        if len(provided) == 0:
            return None
        if len(provided) > 1:
            names = ", ".join(provided.keys())
            log.error("ELN '%s': mehrere Empfaenger-Felder gesetzt (%s) - "
                      "es darf nur genau eines sein", self.name if hasattr(self, "name") else "?", names)
            return None
        api_key, value = next(iter(provided.items()))
        if api_key == "user_ids":
            value = [v for v in value if v]
            if not value:
                return None
            if len(value) > 500:
                log.warning("ELN '%s': recipient_user_ids hat %d Eintraege, API erlaubt max. 500 - "
                            "schneide auf 500", getattr(self, "name", "?"), len(value))
                value = value[:500]
        elif api_key == "user_id" and not isinstance(value, str):
            value = str(value)
        return {api_key: value}

    def _apply_org_id(self, auth: dict):
        org_id = auth.get("org_id", "")
        if not org_id:
            return
        if auth.get("org_id_query", False):
            self.session.params = {"org_id": org_id}
        else:
            header_name = auth.get("org_id_header", "X-Org-Id")
            self.session.headers[header_name] = org_id

    def _refresh_oauth2(self) -> bool:
        auth = self.config.get("auth", {}) or {}
        if not self._refresh_token:
            log.error("ELN '%s': access_token abgelaufen, aber kein refresh_token - "
                      "erneut im Browser einloggen", self.name)
            return False
        token_url = auth.get("token_url", "")
        if not token_url:
            log.error("ELN '%s': oauth2 token_url fehlt in config", self.name)
            return False
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": auth.get("client_id", ""),
            "client_secret": auth.get("client_secret", ""),
        }
        log.info("ELN '%s': refresh oauth2 token", self.name)
        r = requests.post(
            token_url, data=payload,
            timeout=auth.get("timeout_seconds", 10),
            verify=self.verify_tls,
        )
        r.raise_for_status()
        data = r.json()
        self._access_token = data.get("access_token", "")
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        self.session.headers["Authorization"] = f"Bearer {self._access_token}"
        return True

    def _ensure_token(self):
        if self.config.get("auth", {}).get("type") != "oauth2":
            return
        if not self._access_token:
            log.error("ELN '%s': kein access_token - einmaliger Browser-Login noetig", self.name)
            return
        if time.time() >= self._token_expires_at - 10:
            if not self._refresh_oauth2():
                return

    def test_connection(self) -> dict:
        """Prueft nur die Auth gegen die ELN-API, ohne eine Notification zu senden."""
        self._ensure_token()
        endpoint = self.config.get("auth", {}).get("self_endpoint", "/v1/health")
        if not self.base_url:
            return {"ok": False, "status": 0, "detail": "base_url nicht konfiguriert"}
        url = f"{self.base_url}{endpoint}"
        try:
            r = self.session.get(url, timeout=self.timeout, verify=self.verify_tls)
            if r.status_code == 200:
                return {"ok": True, "status": 200, "detail": "Auth OK"}
            if r.status_code in (401, 403):
                return {"ok": False, "status": r.status_code,
                        "detail": f"Auth fehlgeschlagen: {r.text[:200]}"}
            return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
        except requests.RequestException as e:
            return {"ok": False, "status": 0, "detail": f"Verbindungsfehler: {e}"}

    def send(self, inc: Incident, kind: str = "alert", remaining: int = 0) -> None:
        """POST /v1/notifications mit NotificationCreate-Body.

        kind: 'alert' | 'digest' -> nutzt email_subject/email_body.
              'resolved'          -> nutzt resolved_subject/resolved_body.
        remaining: nur fuer kind='resolved' relevant, wird an resolved_body
                    durchgereicht (Anzahl noch offener Incidents).
        Idempotenz: 'Idempotency-Key: lcc-{incident_id}-{kind}'.
        """
        self._ensure_token()
        if not self.base_url:
            log.error("ELN '%s': base_url nicht konfiguriert - send() uebersprungen", self.name)
            return
        if self.recipient is None:
            log.error("ELN '%s': kein Empfaenger konfiguriert (recipient_user_id / "
                      "recipient_user_ids / recipient_role) - send() uebersprungen", self.name)
            return

        if kind == "resolved":
            title = resolved_subject(inc, self.templates_cfg)
            body = resolved_body(inc, self.templates_cfg, remaining=remaining)
        else:
            title = _subject(inc, self.templates_cfg)
            body = _body(inc, self.templates_cfg)

        payload = self._build_payload(title, body, inc)
        url = f"{self.base_url}/v1/notifications"
        headers = {"Idempotency-Key": f"lcc-{inc.id}-{kind}"}

        log.info("ELN '%s': POST /v1/notifications kind=%s incident=%s type=%s",
                 self.name, kind, inc.id, self.notification_type)
        r = self.session.post(url, json=payload, headers=headers,
                              timeout=self.timeout, verify=self.verify_tls)
        r.raise_for_status()
        if r.content:
            log.info("ELN '%s': response %s", self.name, r.json())

    def send_digest(self, incidents: list[Incident], total_active: int = 0) -> None:
        """Pro Incident ein POST /v1/notifications. kind='digest'."""
        for inc in incidents:
            self.send(inc, kind="digest")

    def send_resolved(self, inc: Incident, remaining: int = 0) -> None:
        self.send(inc, kind="resolved", remaining=remaining)

    def _build_payload(self, title: str, body: str, inc: Incident) -> dict:
        title = (title or "").strip()
        body = body or ""
        if len(title) > _TITLE_MAX:
            log.warning("ELN '%s': title zu lang (%d), schneide auf %d",
                        self.name, len(title), _TITLE_MAX)
            title = title[:_TITLE_MAX - 1] + "\u2026"
        if len(body) > _BODY_MAX:
            log.warning("ELN '%s': body zu lang (%d), schneide auf %d",
                        self.name, len(body), _BODY_MAX)
            body = body[:_BODY_MAX - 1] + "\u2026"

        payload: dict = {
            "title": title,
            "notification_type": self.notification_type,
        }
        if body:
            payload["body"] = body
        if inc.url:
            payload["link_url"] = inc.url
        if self.recipient:
            payload.update(self.recipient)
        return payload
