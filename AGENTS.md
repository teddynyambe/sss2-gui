# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

Web control system for the **SSS2** (Smart Sensor Simulation 2) hardware device: a FastAPI backend ([app-ui/](app-ui/)) talking to the device, and a Svelte 5 frontend ([ui/](ui/)). The backend serves the built UI in production. Target deployment is a Raspberry Pi.

> **README is partially stale.** [README.md](README.md) describes the original **serial** (`serial_asyncio`) architecture. The codebase has since been rewritten to communicate over **J1939 CAN bus** (see commit `c962fda`). There is no serial service anymore — control goes through [services/can_service.py](app-ui/services/can_service.py). Trust the code over the README for anything transport-related, and note the README still lists CAN as "future work" when it is in fact the current implementation.

## Commands

Backend (run from [app-ui/](app-ui/)):
```bash
python main.py                          # run backend on :8000 (serves API + built UI)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload   # dev with reload
pytest tests/                           # run all backend tests
pytest tests/test_state_roundtrip.py    # single test file
pytest tests/test_health.py -k health   # single test by name
pip install -r requirements.txt
```

Frontend (run from [ui/](ui/)):
```bash
npm run dev        # vite dev server on :5173, proxies /api -> http://127.0.0.1:8000
npm run build      # static build
npm run check      # svelte-check type checking
npm run lint       # prettier --check + eslint
npm run format     # prettier --write
```
There is **no frontend test runner**; `npm run build` succeeding is the bar (per [.cursorrules](.cursorrules)).

### Deployment (Raspberry Pi, single service)

Production runs **one systemd service**, `sss2-backend` (FastAPI/uvicorn, `app-ui`), which serves **both** the API (`/api`) and the built UI (`/`) on port 8000. The UI is built with `@sveltejs/adapter-static` into a client-rendered SPA, then copied into `app-ui/static/ui/`. Because UI and API share one origin, the relative `VITE_API_BASE=/api` default just works — no node server, reverse proxy, or CORS. Code flows dev → GitHub → Pi:

```bash
./scripts/deploy.sh "message"   # on dev/Mac: commit + push to the 'org' remote (SystemsCyber/SSS2-GUI)
./scripts/deploy-pi.sh          # on the Pi: git pull -> npm build + copy to static/ui -> pip install -> restart backend
```

- Backend unit file: [scripts/systemd/sss2-backend.service](scripts/systemd/sss2-backend.service) (edit `User=`/paths per host).
- FastAPI's catch-all in [main.py](app-ui/main.py) serves `static/ui/` files (`index.html`, `_app/*`) and falls back to `index.html` for client-side routes.
- SSR is disabled ([ui/src/routes/+layout.ts](ui/src/routes/+layout.ts)) — required for the static SPA build.
- `scripts/build-ui.sh` does the local equivalent (build → copy into `app-ui/static/ui/`).
- Note: `client.ts`/`wsClient.ts` still support an absolute `VITE_API_BASE`, but the wsClient path-composition assumes the relative default — keep `/api` unless you also fix that.

## Backend architecture

Strict layering, enforced by [.cursorrules](.cursorrules) — keep new code in the right layer:

```
routers/      FastAPI route handlers, all mounted under /api (main.py)
   ↓
middleware/   orchestrator.py — single coordinator object; owns service lifecycle,
              routes commands to services, schedules asyncio background tasks
   ↓
services/     business logic (CAN, state, ECU, catalog, monitor)
   ↓
store/        files.py FileStore — JSON persistence (no database, by design)
```

Singletons (`Orchestrator`, `MonitorService`) are created in the `lifespan` handler in [main.py](app-ui/main.py) and exposed via `get_*_instance()`. Routers reach services through the orchestrator, not directly.

### Two distinct CAN roles — don't conflate them
- **[services/can_service.py](app-ui/services/can_service.py)** — the *active* J1939 node. Claims an address on `can0` at startup (`GUI_SA = 0x82`), and controls the SSS2 by sending the SSS2 service PGN `0xEF00` (settings 1–93). Ignition and potentiometer commands from [routers/sss2.py](app-ui/routers/sss2.py) flow through here. Auto-connects on boot when `CAN_AUTO_CONNECT` is set ([core/config.py](app-ui/core/config.py)).
- **[services/monitor_service.py](app-ui/services/monitor_service.py)** — *receive-only*. Opens additional CAN buses that **never transmit**; tags frames with their source channel and pushes them to the UI over WebSocket. Used for passive multi-bus monitoring.

### J1939 / SPN decode database
[j1939db/](app-ui/j1939db/) holds `j1939.json` (NAME fields) and `spn_db.json` (PGN→SPN definitions), **generated** from the SAE J1939 Digital Annex spreadsheet ([j1939da/](app-ui/j1939da/)) by [j1939db/parse_da.py](app-ui/j1939db/parse_da.py). Regenerate with `python parse_da.py` (needs `openpyxl`, which is not in requirements.txt). `can_service` loads `j1939.json` at import. The frontend does its own SPN decode in [ui/src/lib/utils/spnDecode.ts](ui/src/lib/utils/spnDecode.ts) against the same data served via `/api/can/spn-db`.

### Persistence
JSON files under [app-ui/store/data/](app-ui/store/data/): `peripheral_catalog.json` (committed), plus gitignored `current_device_state.json`, `snapshots/*.json`, and `ecus/`. State file is the source of truth; snapshots are revertable saved configs.

### API surface (all under `/api`)
- `sss2.py` — `GET/PUT /sss2/state`, `POST /sss2/ignition`
- `can.py` — `/can/connect|disconnect|status|scan|nodes|frames|spn-db|interfaces` and `/can/monitor/*` (receive-only buses)
- `connection.py` — `GET /connection/status`, `WS /connection/ws` (broadcasts CAN state + frames)
- `ecu.py` — CRUD `/ecus`, `catalog.py` — `GET /catalog`, `health.py` — `GET /health`

## Frontend architecture

SvelteKit + **Svelte 5 runes** (required by [.cursorrules](.cursorrules) — use runes, not legacy stores syntax). Tailwind **v4** via the `@tailwindcss/vite` plugin (no `tailwind.config`-based PostCSS pipeline; compiles at build time only).

- [ui/src/lib/stores/deviceStore.svelte.ts](ui/src/lib/stores/deviceStore.svelte.ts) — runes-based central state (note `.svelte.ts` extension, required for runes in a module).
- [ui/src/lib/api/client.ts](ui/src/lib/api/client.ts) (REST) and `wsClient.ts` (WebSocket) — the only places that talk to the backend.
- `lib/components/` — UI; `lib/pages/` — Dashboard/Settings; `routes/` — SvelteKit entry (`+page.svelte`, `+layout.svelte`).

UI must stay **touch-friendly**: sliders for ranged values, large toggles, ≥44px hit targets, high-contrast dark theme.

## Hardware domain model (from .cursorrules — important context)

The SSS2 exposes two **physical** connectors, **J18** and **J24**, each with numbered pins addressed as `"J24:1"`, `"J18:7"`. Distinct from this, a potentiometer "Port" is a **logical firmware index** (1–30), *not* a USB/serial port. Pin assignments are fixed by hardware and must not be edited in the UI. Per potentiometer: identity fields (Name, Pin, Port, Resistance) and electrical limits (ECM Fault High/Low) are read-only; only Application, terminal connects (A/B/Wiper), Wiper Position, and Wire Color are editable. Wiper Position is constrained by the ECM Fault Low/High settings.

## Constraints (from .cursorrules — non-negotiable)

- Only two top-level app folders: `app-ui/` and `ui/`. Do not add other top-level frameworks.
- No database servers, no Docker requirement for production, no large JS/UI component kits. Prefer stdlib + small libs (Raspberry Pi footprint).
- Serial port / CAN channel must stay configurable via env (`SSS2_SERIAL_PORT` historically; CAN settings via `core/config.py` env vars like `CAN_CHANNEL`, `CAN_BITRATE`, `CAN_AUTO_CONNECT`).

## Notes

- [console-sss2/](console-sss2/) is a standalone CLI utility with its own venv — separate from the web app.
- [scripts/sync_ui.sh](scripts/sync_ui.sh) copies `ui/` out of the shared VM folder to a local path before `npm install` (avoids node_modules on `/vm_shared`); it refuses to run inside the shared folder.
