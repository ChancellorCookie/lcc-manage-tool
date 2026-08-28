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

Backend-Änderungen auf dem Host bereitstellen und neu bauen:

```bash
# Dateien per SFTP nach /home/administrator/lcc-tools/backend/ kopieren
cd /home/administrator/lcc-tools
docker compose -p lcc-tools build api
docker compose -p lcc-tools up -d api
```