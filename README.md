# LCC Tools

Zentrale Verwaltung für das Waldner Lab Control Center: Räume, OPC-UA-Sensoren,
Incident-Monitoring mit Benachrichtigungen und Offline-Device-Alarme.

## Konfiguration

Kopiere die Beispiel-Konfiguration als Ausgangspunkt und trage deine echten Werte ein:

```
cp config/config.example.yaml config/config.yaml
```

Die `config.yaml` auf dem Deployment-Host enthält die tatsächlichen Settings
(SMTP-Zugang, Empfänger, Templates). Geheimnisse (Passwörter, Tokens) sollten
per `${VAR}` gesetzt werden; die Substitution übernimmt `backend/notifier/config.py`.

### Nachrichtentemplates

Die Sektion `templates` in `config.yaml` definiert Betreff + Body für
Incident-Mails. Verfügbare Platzhalter (siehe `backend/notifier/formatting.py`,
`PLACEHOLDER_GROUPS`):

| Platzhalter | Bedeutung |
|---|---|
| `{component_name}` | Sprechender Gerätename aus OPC UA (z. B. "Gefrierschrank 1004") |
| `{location}` | Hierarchischer Standort ohne `IEU/` (z. B. `R111-114`) |
| `{severity_label}` | Severity als Label (WARNUNG, ALARM, ...) |
| `{title}` / `{description}` | Incident-Titel / Beschreibung |
| `{url}` | Link zur Fehlerhistorie |
| `{room_name}`, `{room_number}` | Raum (falls angereichert) |
| ... weitere | siehe `formatting.py` |

Felder, die in der Mail nicht erscheinen sollen, einfach aus dem Template
weglassen (kein Zwang zu Kontakt oder Handlungsempfehlung).

**Hinweis:** Im Template-Editor (UI) gespeicherte Templates überschreiben
diese Config-Defaults zur Laufzeit.

### Offline-Device-Monitor

Die Sektion `offline_monitor` steuert das Offline-Alarmsystem:

- `threshold_minutes`: ab dieser Offline-Dauer gilt ein Gerät als fällig
- `digest_interval_minutes`: Stunden-Digest, wird **nur** gesendet, wenn
  mindestens ein Gerät neu fällig wurde
- `daily_digest`: Tagesbericht, wird **nur** gesendet, wenn überwachte Geräte
  offline sind

Überwachte Geräte werden im Sensors-Tab per Checkbox aktiviert. Offline-Mails
erscheinen zusätzlich im Benachrichtigungsverlauf.

### Deployment (Firmen-Docker-Host 10.89.11.30)

Das Dev-Projekt (`lcc-tools-dev`, Port 9999/9712) und die Produktion
(`lcc-tools`, Port 8999/8702) liegen als Git-Checkout auf dem Host:

```bash
cd /home/administrator/lcc-tools-dev        # bzw. lcc-tools (Prod)
git pull
docker compose -p lcc-tools-dev -f docker-compose.dev.yml up -d --build
```

### Speicher-Kachel (Docker-Host)

Die Startseite zeigt freien Speicherplatz + `docker system df`. Die Host-Werte
kommen aus `data-dev/storage.json`, geschrieben von `storage_check.py`:

```bash
# einmalig auf dem Host einrichten
chmod +x storage_check.py
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/bin/python3 $PWD/storage_check.py >/dev/null 2>&1") | crontab -
```

Ohne diese Datei fällt das Backend auf `shutil.disk_usage` im Container zurück
(zeigt die Host-Partition des Overlay-Dateisystems, aber ohne Docker-Aufschlüsselung).

### Dashboards & gespeicherte Kanäle

Der Collector schreibt **alle historisierenden Signale** (`historizing=1`) alle
30 s append-only in `sensor_values` — unabhängig vom `monitored`-Flag. Dieses
Flag steuert nur, welche Signale im Sensors-Tab als „überwachte Sensoren“
gelistet werden; der Widget-Dialog bietet seit dem Ausbau **alle gespeicherten
Kanäle** an (`GET /api/viz/signals`, Badge „aufgezeichnet“ = historizing).

Die Dashboard-Kacheln der Startseite lesen Verbrauchswerte aus dem lokalen
Store (`GET /api/viz/dashboards/stats?window_h=24`), nicht per OPC-UA-Read.