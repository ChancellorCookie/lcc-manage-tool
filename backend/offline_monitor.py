"""Offline-Device-Monitor fuer LCC Tools.

Ueberwacht Geräte, die per Checkbox (offline_monitor) freigegeben wurden, und
meldet Offline-Zeiten per E-Mail:

  * Stunden-Digest: wird NUR versendet, wenn in der letzten Stunde mindestens
    ein Gerät die Offline-Schwelle überschritten hat ("neu fällig"). Die Mail
    listet die neuen fälligen Geräte + alle weiterhin offline befindlichen.
  * Tagglicher Digest (9:00 Uhr): Liste ALLER überwachten Geräte, die gerade
    offline sind — unabhängig davon, ob schon ein Stunden-Alarm kam.

Kein Sofort-Alarm: "erste Benachrichtigungen" werden gebuendelt im
Stunden-Digest zugestellt.

Läuft als asyncio-Hintergrundtask im FastAPI-Prozess.
"""

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")

from . import device_cache as dc
from .notifier.channels import build_channel
from .notifier.config import load_config

log = logging.getLogger("offline_monitor")

_DEFAULTS = {
    "enabled": True,
    "threshold_minutes": 30,
    "digest_interval_minutes": 60,
    "daily_digest": "09:00",
    "channels": [],
    "check_interval_seconds": 60,
}


def _now():
    return datetime.now(TZ)


def _fmt_ts(ts):
    if not ts:
        return "?"
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


def _fmt_duration(seconds):
    if not seconds:
        return "?"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes / 60.0
    if hours < 24:
        return f"{hours:.1f} h"
    days = hours / 24.0
    return f"{days:.1f} d"


def _channel_map(cfg: dict):
    return {
        name: build_channel(name, ccfg)
        for name, ccfg in cfg.get("channels", {}).items()
    }


def offline_stats(config_path: str) -> dict:
    """Return offline-monitoring stats for the dashboard tile.

    Reads the threshold live from config (so a UI change is reflected) and
    reports both the number of monitored devices currently offline and how
    many of those have already crossed the threshold (due).
    """
    cfg = load_config(config_path)
    om = {**_DEFAULTS, **(cfg.get("offline_monitor") or {})}
    threshold_minutes = int(om.get("threshold_minutes", 30))
    devices = dc.get_monitored_devices()
    now = time.time()
    offline = [d for d in devices if d["online"] == 0]
    due = [
        d for d in offline
        if d["offlineSince"]
        and (now - d["offlineSince"]) >= threshold_minutes * 60
    ]
    return {
        "offline": len(offline),
        "due": len(due),
        "thresholdMinutes": threshold_minutes,
        "devices": [
            {"serial": d["serial"], "name": d["name"], "offlineSince": d["offlineSince"]}
            for d in offline
        ],
    }


class OfflineMonitor:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.cfg = load_config(config_path)
        om = {**_DEFAULTS, **(self.cfg.get("offline_monitor") or {})}
        self.enabled = bool(om["enabled"])
        self.threshold_minutes = int(om.get("threshold_minutes", 30))
        self.digest_interval = int(om.get("digest_interval_minutes", 60)) * 60
        self.daily_time = str(om.get("daily_digest", "09:00"))
        self.check_interval = int(om.get("check_interval_seconds", 60))
        self.channel_names = list(om["channels"]) or list(
            self.cfg.get("channels", {}).keys()
        )
        self._channels = None  # lazy: build from cfg['channels']
        self._last_hourly = 0.0
        self._last_daily_date = None
        self._running = True

    def _reload_threshold(self):
        """Pick up a UI-changed offline threshold without a container restart."""
        cfg = load_config(self.config_path)
        om = cfg.get("offline_monitor") or {}
        try:
            self.threshold_minutes = int(om.get("threshold_minutes", self.threshold_minutes))
        except (TypeError, ValueError):
            pass

    @property
    def channels(self):
        if self._channels is None:
            self._channels = _channel_map(self.cfg)
        return self._channels

    def _send_raw(self, subject: str, body: str):
        ok = 0
        for cname in self.channel_names:
            ch = self.channels.get(cname)
            if ch is None:
                log.error("Offline-Monitor: unbekannter Kanal '%s'", cname)
                continue
            try:
                ch.send_raw(subject, body)
                ok += 1
                log.info("Offline-Digest ueber '%s' versendet", cname)
            except Exception as e:
                log.error("Offline-Digest Kanal '%s' fehlgeschlagen: %s", cname, e)
        return ok > 0

    # ── Digest-Bodenplatten ───────────────────────────────────────

    def _build_hourly_body(self, due_serials, monitored_offline):
        now = time.time()
        lines = ["Offline-Digest — neue fällige Geräte:\n"]
        lines.append(f"Stand: {datetime.fromtimestamp(now, TZ).strftime('%d.%m.%Y %H:%M')}\n")
        lines.append("Neu fällig (Schwelle überschritten):")
        if due_serials:
            for d in due_serials:
                dur = now - d["offlineSince"] if d["offlineSince"] else 0
                lines.append(f"  - {d['name']} ({d['serial']}) — offline seit {_fmt_ts(d['offlineSince'])} ({_fmt_duration(dur)})")
        else:
            lines.append("  (keine)")
        lines.append("")
        lines.append("Weiterhin offline:")
        if monitored_offline:
            for d in monitored_offline:
                dur = now - d["offlineSince"] if d["offlineSince"] else 0
                lines.append(f"  - {d['name']} ({d['serial']}) — offline seit {_fmt_ts(d['offlineSince'])} ({_fmt_duration(dur)})")
        else:
            lines.append("  (keine)")
        return "\n".join(lines)

    def _build_daily_body(self, monitored_offline):
        now = time.time()
        lines = ["Täglicher Offline-Bericht — überwachte Geräte", ""]
        lines.append(f"Stand: {datetime.fromtimestamp(now, TZ).strftime('%d.%m.%Y %H:%M')}\n")
        if monitored_offline:
            lines.append(f"{len(monitored_offline)} überwachte Geräte offline:")
            for d in monitored_offline:
                dur = now - d["offlineSince"] if d["offlineSince"] else 0
                lines.append(f"  - {d['name']} ({d['serial']}) — offline seit {_fmt_ts(d['offlineSince'])} ({_fmt_duration(dur)})")
        else:
            lines.append("Alle überwachten Geräte sind online.")
        return "\n".join(lines)

    # ── Kernlogik ─────────────────────────────────────────────────

    async def tick(self):
        """One monitor pass. Returns nothing; sends digests when due."""
        self._reload_threshold()
        if not self.enabled:
            return
        devices = dc.get_monitored_devices()
        if not devices:
            return
        now = time.time()

        offline = [d for d in devices if d["online"] == 0]
        # newly due = offline, threshold exceeded, not yet first-alerted
        due = [
            d for d in offline
            if d["offlineSince"]
            and (now - d["offlineSince"]) >= self.threshold_minutes * 60
            and not d["firstAlerted"]
        ]

        # Hourly digest: only when at least one NEW device became due
        if now - self._last_hourly >= self.digest_interval:
            if due:
                subject = f"[OFFLINE] {len(due)} Gerät(e) neu fällig offline"
                body = self._build_hourly_body(due, offline)
                if self._send_raw(subject, body):
                    dc.mark_first_alerted([d["serial"] for d in due])
                self._last_hourly = now
            else:
                # no new due devices -> skip this hourly window silently
                self._last_hourly = now

        # Daily digest at configured time (once per day). Skip the day silently
        # when there are no monitored devices offline — no mail for "all ok".
        today = _now().date().isoformat()
        hhmm = _now().strftime("%H:%M")
        if self._last_daily_date != today and hhmm >= self.daily_time:
            daily_offline = offline
            if daily_offline:
                subject = f"[OFFLINE-TAGESBERICHT] {len(daily_offline)} überwachte Geräte offline"
                self._send_raw(subject, self._build_daily_body(daily_offline))
            self._last_daily_date = today

    async def run(self):
        log.info("Offline-Monitor gestartet (Threshold %d min, Digest alle %d min, Tagesbericht %s, Kanäle: %s)",
                 self.threshold_minutes, int(self.digest_interval / 60), self.daily_time,
                 ", ".join(self.channel_names) or "keine")
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                log.exception("Offline-Monitor tick fehlgeschlagen: %s", e)
            await asyncio.sleep(self.check_interval)

    def stop(self):
        self._running = False