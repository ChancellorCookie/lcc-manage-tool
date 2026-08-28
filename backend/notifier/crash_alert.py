"""Crash-Alert: sendet eine E-Mail wenn der Dienst unerwartet stoppt.

Aufgerufen von systemd ExecStopPost= (siehe deploy/incident-notifier.service)
mit dem Exit-Status als Argument, oder via:

    python -m notifier.crash_alert <exit_status>

Liest die Config + secrets.env, schickt eine kurze Alarm-Mail an den ersten
E-Mail-Kanal aus der Config.
"""
import os
import re
import smtplib
import ssl
import sys
import socket
import yaml
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


CONF_PATH = os.environ.get(
    "INCIDENT_NOTIFIER_CONFIG",
    "/etc/incident-notifier/config.yaml",
)
SECRETS_PATH = os.environ.get(
    "INCIDENT_NOTIFIER_SECRETS",
    "/etc/incident-notifier/secrets.env",
)


_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _sub_env(value):
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    return value


def _first_email_channel(cfg: dict):
    """Liefert (name, channel_config) des ersten E-Mail-Kanals, oder None."""
    for name, ch in (cfg.get("channels") or {}).items():
        if (ch or {}).get("type") == "email":
            return name, ch
    return None


def _build_message(ch: dict, exit_status: str, hostname: str, now: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = _sub_env(ch.get("from_addr", ""))
    msg["To"] = ", ".join(ch.get("to_addrs") or [])
    msg["Subject"] = f"[CRASH] Incident Notifier auf {hostname} gestoppt (Exit {exit_status})"
    msg.set_content(
        f"Der Incident Notifier auf {hostname} wurde unerwartet beendet.\n\n"
        f"Zeitpunkt: {now}\n"
        f"Exit-Code: {exit_status}\n\n"
        f"Bitte den Dienst ueberpruefen:\n"
        f"  systemctl status incident-notifier\n"
        f"  journalctl -u incident-notifier -n 50\n"
    )
    return msg


def _deliver(ch: dict, msg: EmailMessage) -> None:
    host = ch.get("smtp_host", "")
    port = int(ch.get("smtp_port", 587))
    user = _sub_env(ch.get("username", ""))
    pw = _sub_env(ch.get("password", ""))

    if ch.get("use_ssl"):
        ctx = ssl.create_default_context()
        client = smtplib.SMTP_SSL(host, port, timeout=10, context=ctx)
    else:
        client = smtplib.SMTP(host, port, timeout=10)
        if ch.get("use_starttls", True):
            client.starttls(context=ssl.create_default_context())
    try:
        if user:
            client.login(user, pw)
        client.send_message(msg)
    finally:
        client.quit()


def send_crash_alert(exit_status: str = "unknown", config_path: str = CONF_PATH,
                     secrets_path: str = SECRETS_PATH) -> bool:
    """Versendet die Crash-Alert-Mail. Returnt True bei Erfolg."""
    _load_env(secrets_path)
    if not os.path.exists(config_path):
        print(f"Config nicht gefunden: {config_path}", file=sys.stderr)
        return False
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh) or {}

    found = _first_email_channel(cfg)
    if not found:
        print("Kein E-Mail-Kanal konfiguriert", file=sys.stderr)
        return False
    name, ch = found

    hostname = socket.gethostname()
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    msg = _build_message(ch, exit_status, hostname, now)

    try:
        _deliver(ch, msg)
        print(f"Crash-Alert gesendet an {msg['To']} (Kanal: {name})")
        return True
    except Exception as e:
        print(f"Fehler beim Senden: {e}", file=sys.stderr)
        return False


def main() -> int:
    exit_status = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    return 0 if send_crash_alert(exit_status) else 1


if __name__ == "__main__":
    sys.exit(main())
