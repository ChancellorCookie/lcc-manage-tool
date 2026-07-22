"""FastAPI router for the Incident Notifier — replaces Flask Web-UI.

Exposes:
  GET  /api/notifier/status     – dashboard stats
  GET  /api/notifier/incidents  – current open incidents
  GET  /api/notifier/config     – full YAML config as JSON
  POST /api/notifier/config     – save config
  GET  /api/notifier/templates  – templates + placeholder metadata
  POST /api/notifier/templates  – save templates
"""

import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter

from .config import load_config
from .formatting import (
    PLACEHOLDER_GROUPS,
    PLACEHOLDER_HELP,
    SAMPLE_VALUES,
    _ALERT_BODY_DEFAULT,
    _ALERT_SUBJECT_DEFAULT,
    _RESOLVED_BODY_DEFAULT,
    _RESOLVED_SUBJECT_DEFAULT,
)
from .poller import Poller
from .state import StateStore

log = logging.getLogger("notifier.api")
router = APIRouter(prefix="/api/notifier", tags=["notifier"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = str(_PROJECT_ROOT / "config" / "config.yaml")


# ── config read/write (inlined from deleted web.helpers) ──────────────

def _save_yaml_config(data: dict) -> None:
    path = _CONFIG_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ── serialisation ────────────────────────────────────────────────────

def _incident_to_dict(inc) -> dict:
    """Convert an Incident dataclass to a JSON-safe dict."""
    d = asdict(inc)
    d.pop("raw", None)
    d["device_name"] = inc.device_name
    return d


# ── helpers ──────────────────────────────────────────────────────────

def _get_state() -> StateStore:
    cfg = load_config(_CONFIG_PATH)
    db_path = cfg.get("state", {}).get("db_path", str(_PROJECT_ROOT / "data" / "state.db"))
    return StateStore(db_path)


def _build_stats(cfg: dict, state: StateStore) -> dict:
    active = state.active()
    digest_pending = state.digest_pending()
    history = state.get_history(50)

    recent = []
    for item in history[:10]:
        recent.append({
            "time": datetime.fromtimestamp(item["sent_at"]).strftime("%d.%m.%Y %H:%M:%S"),
            "incident": item.get("incident_title") or item["incident_id"][:12],
            "severity": item.get("severity", "-"),
            "channel": item.get("channel", "-"),
            "kind": item.get("kind", "-"),
        })

    last = history[0] if history else None

    return {
        "active_incidents": len(active),
        "digest_pending": len(digest_pending),
        "total_sent": len(history),
        "channels": len(cfg.get("channels", {})),
        "last_time": datetime.fromtimestamp(last["sent_at"]).strftime("%H:%M") if last else "-",
        "last_date": datetime.fromtimestamp(last["sent_at"]).strftime("%d.%m.%Y") if last else "",
        "recent": recent,
    }


# ── GET /status ─────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    cfg = load_config(_CONFIG_PATH)
    state = _get_state()
    try:
        return _build_stats(cfg, state)
    finally:
        state.close()


# ── GET /incidents ──────────────────────────────────────────────────

@router.get("/incidents")
async def get_incidents(limit: Optional[int] = None):
    cfg = load_config(_CONFIG_PATH)
    poll_cfg = cfg.get("poll", {})
    poller = Poller(poll_cfg)
    try:
        incidents = await poller.fetch()
    except Exception as e:
        log.warning("Incident fetch failed: %s", e)
        return {"incidents": [], "error": str(e)}
    if limit:
        incidents = incidents[:limit]
    return {"incidents": [_incident_to_dict(inc) for inc in incidents]}


# ── GET /config ─────────────────────────────────────────────────────

def _mask_secrets(data, depth=0):
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if k in ("password", "token", "client_secret", "auth_token",
                     "access_token", "refresh_token", "account_sid", "secret_key"):
                masked[k] = "***" if v else ""
            elif isinstance(v, str) and v.startswith("${"):
                masked[k] = "***"
            elif isinstance(v, (dict, list)):
                masked[k] = _mask_secrets(v, depth + 1)
            else:
                masked[k] = v
        return masked
    if isinstance(data, list):
        return [_mask_secrets(v, depth + 1) for v in data]
    return data


@router.get("/config")
async def get_config():
    cfg = load_config(_CONFIG_PATH)
    return _mask_secrets(cfg)


# ── POST /config ────────────────────────────────────────────────────

@router.post("/config")
async def post_config(body: dict):
    _save_yaml_config(body)
    return {"status": "ok", "path": _CONFIG_PATH}


# ── GET /templates ──────────────────────────────────────────────────

@router.get("/templates")
async def get_templates():
    cfg = load_config(_CONFIG_PATH)
    tpl = cfg.get("templates", {})
    defaults = {
        "alert_subject": _ALERT_SUBJECT_DEFAULT,
        "alert_body": _ALERT_BODY_DEFAULT,
        "resolved_subject": _RESOLVED_SUBJECT_DEFAULT,
        "resolved_body": _RESOLVED_BODY_DEFAULT,
    }
    return {
        "templates": tpl,
        "defaults": defaults,
        "placeholder_groups": PLACEHOLDER_GROUPS,
        "placeholder_help": PLACEHOLDER_HELP,
        "sample_values": SAMPLE_VALUES,
    }


# ── POST /templates ─────────────────────────────────────────────────

@router.post("/templates")
async def post_templates(body: dict):
    cfg = load_config(_CONFIG_PATH)
    tpl = cfg.setdefault("templates", {})

    for key in ("alert_subject", "alert_body", "resolved_subject", "resolved_body"):
        val = body.get(key, "").strip() if isinstance(body.get(key), str) else ""
        if val or key in body:
            if val:
                tpl[key] = val
            else:
                tpl.pop(key, None)

    _save_yaml_config(cfg)
    return {"status": "ok", "templates": tpl}
