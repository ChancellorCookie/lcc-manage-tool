"""Einheitliche Formatierung der Benachrichtigungstexte.

Unterstuetzt konfigurierbare Templates ueber die config.yaml (Sektion 'templates').
Platzhalter werden als {variable} geschrieben. Ist kein Template konfiguriert,
wird das Built-in-Format verwendet.

Es gibt nur EIN Template pro Nachrichtentyp:
    alert_subject    -> wird in E-Mail-Betreff und ELN-title verwendet
    alert_body       -> wird in E-Mail-Body, WhatsApp-Sandbox-Body und ELN-body verwendet
    resolved_subject -> wird in E-Mail-Betreff und ELN-title verwendet (resolved)
    resolved_body    -> wird in E-Mail-Body und ELN-body verwendet (resolved)

Alle Templates sind reiner Text. Es gibt keine HTML-Alternative.
WhatsApp-Produktivtemplates (per content_sid / template_name) sind davon
nicht betroffen - sie nutzen template_variables().
"""
from .models import Incident


def _component_name_for(inc: Incident) -> str:
    """Look up the cached component name for a device (existing data only).

    Uses the device_cache if present; returns "" when the name was never
    persisted (no live OPC-UA resolution during send).
    """
    try:
        from .. import device_cache as dc
        serial = inc.device_name or ""
        for d in dc.get_cached_devices():
            if d["serial"] == serial or d["nodeId"].endswith(serial):
                return d.get("componentName") or ""
    except Exception:
        pass
    return ""

# Severity -> Anzeige-Label.
# LCC bündelt "error" mit "kritisch" (alle Vorfälle, die Handeln erfordern),
# darum zeigen error und critical denselben Label.
_SEVERITY_LABEL = {"critical": "KRITISCH/FEHLER", "error": "KRITISCH/FEHLER",
                   "alert": "ALARM", "warning": "WARNUNG",
                   "info": "INFO", "notice": "HINWEIS"}


# ---------------------------------------------------------------------------
# Platzhalter-Hilfe (gruppiert fuer den Editor + Beschreibung)
# ---------------------------------------------------------------------------

PLACEHOLDER_GROUPS: list[tuple[str, list[str]]] = [
    ("Vorfall", [
        "severity", "severity_label",
        "max_severity", "max_severity_label",
        "title", "description", "status", "timestamp", "id",
        "source", "device_name", "component_name", "event_id",
    ]),
    ("Raum", [
        "room_name", "room_number",
        "room_contact_name", "room_contact_email", "room_contact_details",
    ]),
    ("Status-Flags", [
        "flags", "flap_count", "flap_warning",
        "acknowledged", "confirmed", "reported", "strict_audited", "active",
        "comment",
    ]),
    ("Schwellwerte", [
        "high_high_limit", "high_limit", "low_limit", "low_low_limit",
        "threshold_list",
    ]),
    ("Handlung", ["help"]),
    ("Links", ["url"]),
]

PLACEHOLDER_HELP: dict[str, str] = {
    # Vorfall
    "severity": "Severity (z.B. error, warning, info)",
    "severity_label": "Severity als Label (z.B. FEHLER, WARNUNG)",
    "max_severity": "Hoechste jemals erreichte Severity",
    "max_severity_label": "Max-Severity als Label",
    "title": "Titel des Incidents",
    "description": "Beschreibungstext",
    "status": "Status (NEW, ACKNOWLEDGED, CONFIRMED, ...)",
    "timestamp": "Zeitpunkt der Erstellung (ISO)",
    "id": "Incident-ID (UUID)",
    "source": "Quelle (Context-Pfad, z.B. DeviceSet/S1-1016939/...)",
    "device_name": "Geraetename (aus Context extrahiert, z.B. S1-1016939)",
    "component_name": "Komponentenname aus dem Geräte-Cache (z.B. Kühleinheit), falls persistiert",
    "event_id": "Ausloesendes Event",
    # Raum
    "room_name": "Raumname (z.B. Entwicklungslabor)",
    "room_number": "Raumnummer (z.B. A-101)",
    "room_contact_name": "Ansprechpartner (z.B. Moriz Walter)",
    "room_contact_email": "E-Mail des Ansprechpartners",
    "room_contact_details": "Durchwahl/Details (z.B. T.345)",
    # Status-Flags
    "flags": "Status-Flags als Text (Quittiert, Bestaetigt, ...)",
    "flap_count": "Flatter-Zaehler (0 = kein Flattern)",
    "flap_warning": "Flattern-Warnung wenn flap_count > 0, sonst leer",
    "acknowledged": "Quittiert? (Ja/Nein)",
    "confirmed": "Bestaetigt? (Ja/Nein)",
    "reported": "Gemeldet? (Ja/Nein)",
    "strict_audited": "Confirm erforderlich? (Ja/Nein)",
    "active": "Condition aktiv? (Ja/Nein)",
    "comment": "Letzter Operator-Kommentar",
    # Schwellwerte
    "high_high_limit": "Kritisch-Hoch-Schwelle",
    "high_limit": "Warnung-Hoch-Schwelle",
    "low_limit": "Warnung-Niedrig-Schwelle",
    "low_low_limit": "Kritisch-Niedrig-Schwelle",
    "threshold_list": "Alle Schwellwerte als Text (kommagetrennt)",
    # Handlung
    "help": "Handlungsempfehlung",
    # Links
    "url": "Direktlink zum Incident im Tool",
}


# ---------------------------------------------------------------------------
# Built-in Fallback-Templates (Plain Text, keine HTML)
# ---------------------------------------------------------------------------

_ALERT_SUBJECT_DEFAULT = "[{severity_label}] [{room_name}] {title}"
_ALERT_BODY_DEFAULT = """Severity:    {severity_label}
Titel:       {title}
Raum:        {room_name} ({room_number})
Kontakt:     {room_contact_name} ({room_contact_email}, {room_contact_details})
Quelle:      {source}
Geraet:      {component_name}{device_name}
Zeitpunkt:   {timestamp}
Status:      {status}
Incident-ID: {id}
{threshold_list}
{flap_warning}
{flags}

Zum Quittieren oeffnen: {url}

HANDLUNGSEMPFEHLUNG:
{help}

Beschreibung:
{description}"""

_RESOLVED_SUBJECT_DEFAULT = "[ENTWARNUNG] [{room_name}] {title}"
_RESOLVED_BODY_DEFAULT = """Der folgende Vorfall ist nicht mehr offen (quittiert oder geschlossen):

Titel:       {title}
Raum:        {room_name} ({room_number})
Quelle:      {source}
Geraet:      {component_name}{device_name}
Incident-ID: {id}"""


# ---------------------------------------------------------------------------
# Beispieldaten fuer den Live-Preview im Editor
# ---------------------------------------------------------------------------

SAMPLE_VALUES: dict[str, str] = {
    "severity": "error",
    "severity_label": "KRITISCH/FEHLER",
    "max_severity": "error",
    "max_severity_label": "KRITISCH/FEHLER",
    "title": "Condition is 27.100 and state is HighHigh",
    "source": "DeviceSet/SP2DC900189/FunctionalUnitSet/SensorUnit/FunctionSet/Temperature",
    "device_name": "SP2DC900189",
    "component_name": "Kühleinheit S2-DCC",
    "description": "Temperatur im Kuehlschrank S2-DCC ueberschreitet den Warnungs-Grenzwert.",
    "timestamp": "2026-07-04T21:03:00Z",
    "status": "NEW",
    "id": "75d1ccff-0523-dea1-3c8d-c2b584fdf48a",
    "url": "https://lcc.ieu.local/error-history",
    "event_id": "evt-abc-123",
    "help": "Bitte den Kuehlschrank pruefen und ggf. die Tuere schliessen.",
    "comment": "",
    "acknowledged": "Nein",
    "confirmed": "Nein",
    "reported": "Nein",
    "flap_count": "0",
    "flap_warning": "",
    "strict_audited": "Nein",
    "active": "Ja",
    "high_high_limit": "25.0",
    "high_limit": "23.0",
    "low_limit": "5.0",
    "low_low_limit": "2.0",
    "threshold_list": "Kritisch-Hoch > 25.0, Warnung-Hoch > 23.0, Warnung-Niedrig < 5.0, Kritisch-Niedrig < 2.0",
    "flags": "",
    "room_name": "Entwicklungslabor",
    "room_number": "A-101",
    "room_contact_name": "Moriz Walter",
    "room_contact_email": "m.walter@ieu.local",
    "room_contact_details": "T.345",
}


# ---------------------------------------------------------------------------
# Template-Loading + Substitution
# ---------------------------------------------------------------------------

def _get_template(templates_cfg: dict | None, key: str, default: str) -> str:
    if templates_cfg and templates_cfg.get(key):
        return templates_cfg[key]
    return default


def _substitute(template: str, inc: Incident, vals: dict | None = None) -> str:
    if vals is None:
        vals = _build_vals(inc)
    return _do_substitute(template, vals)


def _do_substitute(template: str, vals: dict) -> str:
    class _FormatDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return template.format_map(_FormatDict(vals))


def _build_vals(inc: Incident) -> dict:
    sev_label = _SEVERITY_LABEL.get(inc.severity, inc.severity.upper())
    max_sev_label = _SEVERITY_LABEL.get(inc.max_severity, inc.max_severity.upper()) if inc.max_severity else ""
    ja_nein = lambda b: "Ja" if b else "Nein"

    flags = []
    if inc.acknowledged:
        flags.append("Quittiert")
    if inc.confirmed:
        flags.append("Bestaetigt")
    if inc.reported:
        flags.append("Gemeldet")
    if inc.strict_audited:
        flags.append("Confirm erforderlich")

    thresholds = []
    if inc.high_high_limit is not None:
        thresholds.append(f"Kritisch-Hoch > {inc.high_high_limit}")
    if inc.high_limit is not None:
        thresholds.append(f"Warnung-Hoch > {inc.high_limit}")
    if inc.low_limit is not None:
        thresholds.append(f"Warnung-Niedrig < {inc.low_limit}")
    if inc.low_low_limit is not None:
        thresholds.append(f"Kritisch-Niedrig < {inc.low_low_limit}")

    return {
        "severity": inc.severity,
        "severity_label": sev_label,
        "max_severity": inc.max_severity,
        "max_severity_label": max_sev_label,
        "title": inc.title,
        "source": inc.source,
        "device_name": inc.device_name,
        "component_name": _component_name_for(inc),
        "description": inc.description,
        "timestamp": inc.timestamp or "-",
        "status": inc.status,
        "id": inc.id,
        "url": inc.url,
        "event_id": inc.event_id,
        "help": inc.help,
        "comment": inc.comment,
        "acknowledged": ja_nein(inc.acknowledged),
        "confirmed": ja_nein(inc.confirmed),
        "reported": ja_nein(inc.reported),
        "flap_count": str(inc.flap_count),
        "flap_warning": f"ALARM FLATTERT {inc.flap_count}x!" if inc.flap_count > 0 else "",
        "strict_audited": ja_nein(inc.strict_audited),
        "active": ja_nein(inc.active),
        "high_high_limit": str(inc.high_high_limit) if inc.high_high_limit is not None else "",
        "high_limit": str(inc.high_limit) if inc.high_limit is not None else "",
        "low_limit": str(inc.low_limit) if inc.low_limit is not None else "",
        "low_low_limit": str(inc.low_low_limit) if inc.low_low_limit is not None else "",
        "threshold_list": ", ".join(thresholds),
        "flags": ", ".join(flags),
        "room_name": inc.room_name,
        "room_number": inc.room_number,
        "room_contact_name": inc.room_contact_name,
        "room_contact_email": inc.room_contact_email,
        "room_contact_details": inc.room_contact_details,
    }


# ---------------------------------------------------------------------------
# Oeffentliche API - einheitlich fuer alle Kanaele
# ---------------------------------------------------------------------------

def subject(inc: Incident, templates_cfg: dict | None = None) -> str:
    """Subject/Title - wird in E-Mail-Betreff und ELN-title verwendet."""
    tpl = _get_template(templates_cfg, "alert_subject", _ALERT_SUBJECT_DEFAULT)
    return _substitute(tpl, inc)


def body(inc: Incident, templates_cfg: dict | None = None) -> str:
    """Body - wird in E-Mail-Body, WhatsApp-Sandbox-Body und ELN-body verwendet."""
    tpl = _get_template(templates_cfg, "alert_body", _ALERT_BODY_DEFAULT)
    return _substitute(tpl, inc)


def resolved_subject(inc: Incident, templates_cfg: dict | None = None) -> str:
    tpl = _get_template(templates_cfg, "resolved_subject", _RESOLVED_SUBJECT_DEFAULT)
    return _substitute(tpl, inc)


def resolved_body(inc: Incident, templates_cfg: dict | None = None, remaining: int = 0) -> str:
    tpl = _get_template(templates_cfg, "resolved_body", _RESOLVED_BODY_DEFAULT)
    result = _substitute(tpl, inc)
    if remaining > 0:
        result += f"\n\n{remaining} Incident(s) weiterhin offen."
    return result


# ---------------------------------------------------------------------------
# WhatsApp-Produktivtemplates (positionale Variablen, separat)
# ---------------------------------------------------------------------------

def template_variables(inc: Incident) -> dict:
    """Variablen fuer ein freigegebenes WhatsApp-Template (Positionen 1..n)."""
    sev = _SEVERITY_LABEL.get(inc.severity, inc.severity.upper())
    return {
        "1": sev,
        "2": inc.title,
        "3": inc.device_name or inc.source or "-",
        "4": str(inc.id),
    }


# ---------------------------------------------------------------------------
# Digest (mehrere Incidents in einer Nachricht)
# ---------------------------------------------------------------------------

def digest_body(incidents: list[Incident], templates_cfg: dict | None = None,
                total_active: int = 0) -> str:
    lines = [f"DIGEST: {len(incidents)} neue Incidents ({total_active} insgesamt offen)\n"]
    for inc in incidents:
        sev = _SEVERITY_LABEL.get(inc.severity, inc.severity.upper())
        lines.append(f"[{sev}] {inc.title}")
        lines.append(f"  Geraet: {inc.device_name}  |  Raum: {inc.room_name or '-'}")
        lines.append(f"  {inc.url}\n")
    return "\n".join(lines)
