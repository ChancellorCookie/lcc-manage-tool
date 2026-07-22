# LCC Tools — Merge-Plan

> **Ziel:** `lcc-manage-tool` + `incident-notifier` → ein Monorepo mit einheitlichem Backend + Svelte-Frontend.
> **Session:** Clean start nach diesem Plan.

**Gemeinsame Basis:** Beide nutzen dieselbe LCC-API (`10.89.11.52`), denselben OAuth2-Client (`iuta-notification / YF72ojKY99U`). Manager hat schon `auth.py` + `lcc_client.py`.

## Ziel-Architektur

```
lcc-tools/
├── backend/
│   ├── auth.py              # geteilt: OAuth2 (von manager)
│   ├── lcc_client.py        # geteilt: LCC REST-Client (von manager)
│   ├── main.py              # FastAPI (Manager + Notifier-Routen)
│   ├── opcua_client.py      # asyncua-Wrapper (von manager)
│   ├── device_cache.py      # SQLite-Cache (von manager)
│   ├── models.py            # Pydantic-Modelle
│   └── notifier/            # ← VOM NOTIFICATION-SERVICE
│       ├── service.py       # Poll-Hauptschleife
│       ├── poller.py        # Incident-Fetcher (requests → httpx)
│       ├── state.py         # SQLite State-Tracking
│       ├── models.py        # Incident-Model
│       ├── formatting.py    # Message-Templates
│       ├── config.py        # YAML-Config-Loader (bleibt)
│       └── channels/
│           ├── base.py, email.py
│           ├── whatsapp_twilio.py, whatsapp_meta.py
│           └── eln.py
├── frontend/                # Svelte 5 (existiert + neue Pages)
│   └── src/lib/pages/
│       ├── Dashboard.svelte, Rooms.svelte     (existiert)
│       ├── Servers.svelte, Sensors.svelte     (existiert)
│       ├── Incidents.svelte                   (NEU)
│       └── NotifierConfig.svelte              (NEU: Templates + Config)
├── config/                  # Notifier YAML-Config
│   └── config.yaml
├── data/                    # SQLite-Datenbanken
├── docker-compose.yml       # Vereint: API + Frontend
└── pyproject.toml
```

---

## Task 1: Basis klonen & Struktur anlegen (15 min)

```bash
cd /opt/data/projects
git clone https://github.com/ChancellorCookie/lcc-manage-tool.git lcc-tools
cd lcc-tools

# Notifier-Code holen
git clone https://github.com/ChancellorCookie/notification_service.git _tmp
cp -r _tmp/incident-notifier/notifier backend/notifier
cp -r _tmp/incident-notifier/config .
cp _tmp/incident-notifier/requirements.txt backend/notifier/
rm -rf _tmp

# Neue Dependencies
uv add pyyaml

# Flask wird nicht mehr gebraucht (WebUI → Svelte + FastAPI)
# twilio optional (WhatsApp-Kanal, nur wenn genutzt)
```

---

## Task 2: Notifier-Code migrieren (75 min)

### 2a. `poller.py` — requests → httpx (20 min)
- `import requests` → `import httpx`
- `requests.get()` → `httpx.Client(verify=False).get()`
- Auth: Statt eigener OAuth2-Logik → `from backend.auth import get_token`
- Basis-URL: `from backend.lcc_client import LCC_BASE`
- Paginierung, Query-Params, Response-Mapping bleiben unverändert

### 2b. Flask-WebUI → FastAPI + Svelte (45 min)
Die 6 Flask-Routen aus `notifier/web/routes.py`:
| Flask | FastAPI | Frontend |
|---|---|---|
| `GET /` Dashboard | `GET /api/notifier/status` | Dashboard-Widget |
| `GET /config` | `GET /api/notifier/config` | NotifierConfig.svelte |
| `POST /config` | `POST /api/notifier/config` | NotifierConfig.svelte |
| `GET /templates` | `GET /api/notifier/templates` | NotifierConfig.svelte |
| `POST /templates` | `POST /api/notifier/templates` | NotifierConfig.svelte |
| `GET /api/incidents` | `GET /api/notifier/incidents` | Incidents.svelte |

- `notifier/web/` komplett entfernen (durch FastAPI + Svelte ersetzt)
- `flask` aus Dependencies streichen

### 2c. Dateien bereinigen (10 min)
- `backend/notifier/__init__.py` anpassen (keine flask-imports mehr)
- `config/secrets.env` → Credentials kommen aus `.env` (einheitlich mit Manager)
- `crash_alert.py` und `run.py` → optional, können bleiben

---

## Task 3: FastAPI-Integration (30 min)

`backend/main.py`:

```python
import asyncio
from backend.notifier.service import run as notifier_run

@app.on_event("startup")
async def start_notifier():
    asyncio.create_task(notifier_run())

# Neue Endpoints:
@app.get("/api/notifier/incidents")
@app.get("/api/notifier/status")
@app.get("/api/notifier/config")
@app.post("/api/notifier/config")
@app.get("/api/notifier/templates")
@app.post("/api/notifier/templates")
```

Notifier-Poll-Loop läuft als Hintergrund-Task im selben Prozess.

---

## Task 4: Svelte-Frontend — Neue Tabs (75 min)

### 4a. Incidents.svelte
- Incident-Tabelle aus `/api/notifier/incidents`
- Filter: Severity (Dropdown), Room (Text), Status
- Detail-Modal mit Historie (`/incidents/{id}/history`)
- Action-Buttons: Acknowledge, Confirm, Report
- Polling alle 30s für Live-Updates

### 4b. NotifierConfig.svelte
- Tabs: "Templates" + "Einstellungen"
- Template-Editor: Subject + Body (Textareas), Live-Vorschau
- Platzhalter-Dropdown (`{severity}`, `{room_name}`, etc.)
- Einstellungen: Poll-Intervall, Severities, Kanäle (read-only fürs Erste)

### 4c. Navigation
- App.svelte: Neue Nav-Items `🔔 Incidents` + `⚙ Notifier`

---

## Task 5: Docker-Compose (15 min)

```yaml
services:
  api:
    build: ./backend
    container_name: lcc-tools
    ports: ["8701:8701"]
    environment:
      - LCC_HOST=10.89.11.52
      - LCC_CLIENT_ID=iuta-notification
      - LCC_CLIENT_SECRET=YF72ojKY99U
      - OPC_URL=opc.tcp://10.89.11.52:4840
    volumes:
      - ./config:/app/config
      - ./data:/app/data

  frontend:
    build: ./frontend
    container_name: lcc-tools-frontend
    ports: ["8999:80"]
    depends_on: [api]
```

Ein Container für beides (API pollt im Hintergrund, served Frontend).

---

## Aufwand

| # | Task | Zeit |
|---|---|---|
| 1 | Basis klonen & Struktur | 15 min |
| 2a | poller.py: requests → httpx | 20 min |
| 2b | Flask → FastAPI + Svelte | 45 min |
| 2c | Cleanup | 10 min |
| 3 | FastAPI-Integration | 30 min |
| 4 | Svelte Tabs (Incidents, Config) | 75 min |
| 5 | Docker-Compose | 15 min |
| **Total** | | **~3 h** |
