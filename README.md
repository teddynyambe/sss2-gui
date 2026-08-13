# SSS2 Control System

Smart Sensor Simulation 2 (SSS2) Control System with FastAPI backend and Svelte 5 frontend.

## Overview

The SSS2 Control System is a web-based interface for configuring and controlling the Smart Sensor Simulation 2 hardware device. The system provides real-time control of 16 potentiometers, ECU pin configurations, and hardware state management with snapshot capabilities.

**Backend:** FastAPI (Python) with asyncio for serial communication  
**Frontend:** Svelte 5 with Runes, Tailwind CSS  
**Storage:** JSON file-based storage (no database required)  
**Target Platform:** Raspberry Pi (optimized for small footprint)

## Project Structure

```
sss2-gui/
├── app-ui/              # FastAPI backend
│   ├── main.py         # Application entry point
│   ├── routers/        # API route handlers
│   ├── services/       # Business logic layer
│   ├── middleware/     # Orchestrator for service coordination
│   ├── store/          # File-based JSON storage
│   └── tests/          # pytest tests
├── ui/                 # Svelte frontend
│   ├── src/
│   │   ├── lib/
│   │   │   ├── api/           # API client
│   │   │   ├── components/    # Reusable components
│   │   │   ├── pages/         # Page components
│   │   │   └── stores/        # Svelte stores (state management)
│   │   └── routes/            # SvelteKit routes
│   └── static/                # Static assets (served by backend in production)
└── scripts/            # Build scripts
```

## Features Implemented

### ✅ Core Functionality

- **State Management**
  - JSON file-based state storage (source of truth)
  - Automatic state synchronization on hardware connection
  - State persistence across restarts
  - Snapshot system (create/list/revert/delete configurations)

- **Serial Communication**
  - Asynchronous serial I/O with `serial_asyncio`
  - Automatic connection detection and retry
  - WebSocket-based connection status updates
  - Fire-and-forget command sending (non-blocking)
  - Command queueing and response handling

### ✅ Potentiometer Control

- **16 Potentiometers (U1-U16)**
  - Individual wiper position control (0-255 → 0-5V or 0-12V)
  - Real-time slider control with debouncing
  - On/Off toggle buttons for each potentiometer
  - Visual status indicators (green/red circles) in collapsed view

- **Power Group Configuration**
  - Potentiometers grouped in pairs (1-2, 3-4, ..., 15-16)
  - Shared power voltage selection per group (+5V or +12V)
  - Voltage calculation scales automatically based on power setting
  - Radio button controls for power selection

- **Hardware Commands**
  - Wiper position: `{port},{value}` (e.g., `1,128`)
  - Enable/Disable: `51,{7|3}` for ports 1-16 (7=on, 3=off)
  - Power groups: `{25-32},{0|1}` (25-32 for groups 1-8, 0=5V, 1=12V)

### ✅ ECU Functions Management

- **ECU Configuration**
  - Create/Read/Update/Delete ECU configurations
  - ECU metadata: name, model, serial number, pictures
  - Pin-by-pin configuration for J18 and J24 connectors
  - Wire color and ECU function descriptions per pin

- **Pin Configuration**
  - View/edit modes for individual pins
  - Pin dropdown excludes already-configured pins
  - Delete pin configurations to make pins available again
  - Selected ECU displays wire color and function on potentiometer cards

### ✅ User Interface

- **Touch-Friendly Design**
  - Minimum 44px hit targets
  - Large toggle buttons and sliders
  - High-contrast dark theme
  - Responsive layout

- **Real-Time Updates**
  - WebSocket connection status
  - Live potentiometer value updates
  - Automatic state refresh on connection

- **Navigation**
  - Dashboard view
  - Settings page (Potentiometers, ECU Functions)
  - History page (Snapshots)
  - ECU selector in header

### ✅ State Synchronization

- **On Connection Sync**
  - When hardware connects, backend state is automatically applied to hardware
  - UI fetches latest state from backend when connection is established
  - Ensures Backend ↔ Hardware ↔ UI are all in sync
  - Source of truth: Backend JSON file storage

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 16+ (only for development, not needed in production)
- npm or yarn

### Option 1: Development Mode (Frontend + Backend Separate)

**Terminal 1 - Backend:**
```bash
cd app-ui
pip install -r requirements.txt
python main.py
```

Backend runs on `http://localhost:8000`

**Terminal 2 - Frontend (Hot Reload):**
```bash
cd ui
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` (Vite default) and proxies API calls to `http://localhost:8000`

### Option 2: Production Mode (Single Server)

**Build UI and copy to backend:**
```bash
./scripts/build-ui.sh
```

**Run backend (serves API + static UI):**
```bash
cd app-ui
pip install -r requirements.txt
python main.py
```

Or using uvicorn directly:
```bash
cd app-ui
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Access the application at `http://localhost:8000`

## Configuration

### Serial Port

**Auto-detect (default):** The backend automatically detects the SSS2 device by scanning for `tty.usbmodem*` / `cu.usbmodem*` on macOS and `ttyACM*` on Linux. No configuration needed when using a single SSS2.

**Override:** To use a specific port, set the environment variable:

```bash
export SSS2_SERIAL_PORT=/dev/tty.usbmodem40787801  # Mac example
# or
export SSS2_SERIAL_PORT=/dev/ttyACM0               # Linux/Pi example
```

Or create a `.env` file in `app-ui/`:
```
SSS2_SERIAL_PORT=/dev/tty.usbmodem40787801
```

When unset or empty, the service uses auto-detect. When set, the configured port is used only if it exists.

## API Endpoints

### Device Control
- `GET /api/sss2/state` - Get current device state
- `PUT /api/sss2/state` - Update device state
- `POST /api/sss2/ignition` - Toggle ignition (body: `{"on": true/false}`)

### Catalog & Configuration
- `GET /api/catalog` - Get peripheral catalog
- `GET /api/health` - Health check

### Snapshots
- `GET /api/snapshots` - List all snapshots
- `POST /api/snapshots` - Create snapshot (body: `{"label": "optional"}`)
- `POST /api/snapshots/{id}/revert` - Revert to snapshot
- `DELETE /api/snapshots/{id}` - Delete snapshot

### ECU Functions
- `GET /api/ecus` - List all ECUs
- `GET /api/ecus/{id}` - Get ECU details
- `POST /api/ecus` - Create new ECU
- `PUT /api/ecus/{id}` - Update ECU
- `DELETE /api/ecus/{id}` - Delete ECU

### Connection
- `GET /api/connection/status` - Get connection status (REST)
- `WS /api/connection/ws` - WebSocket for connection status updates

## Architecture

### Backend Architecture

```
┌─────────────┐
│   FastAPI   │  ← HTTP/WebSocket API
│   Routers   │
└──────┬──────┘
       │
┌──────▼──────────┐
│  Orchestrator   │  ← Service coordination layer
└──────┬──────────┘
       │
   ┌───┴────┬────────────┬──────────────┐
   │        │            │              │
┌──▼──┐ ┌──▼─────┐ ┌────▼─────┐ ┌─────▼─────┐
│State│ │Serial  │ │ECU       │ │Snapshot   │
│Svc  │ │Service │ │Service   │ │Service    │
└──┬──┘ └──┬─────┘ └────┬─────┘ └─────┬─────┘
   │       │            │              │
   │    ┌──▼───┐        │              │
   │    │ SSS2 │        │              │
   │    │Hardw │        │              │
   │    └──────┘        │              │
   │                    │              │
┌──▼────────────────────▼──────────────▼──┐
│        FileStore (JSON Files)           │
│  - device_state.json                    │
│  - peripheral_catalog.json              │
│  - ecus/*.json                          │
│  - snapshots/*.json                     │
└─────────────────────────────────────────┘
```

### State Synchronization Flow

```
Hardware Connects
    ↓
SerialService detects connection
    ↓
Orchestrator._on_connection_changed() called
    ↓
Orchestrator.sync_state_to_hardware() triggered
    ↓
StateService.get_state() loads from file (source of truth)
    ↓
Apply all settings to hardware:
  - Power groups (commands 25-32)
  - Potentiometer enabled states (51,7/51,3)
  - Potentiometer wiper positions (port,value)
    ↓
WebSocket broadcasts connection status to UI
    ↓
UI detects connection established
    ↓
UI calls fetchState() to get latest backend state
    ↓
All three systems synchronized: Backend ↔ Hardware ↔ UI
```

## Testing

```bash
cd app-ui
pytest tests/
```

## Deployment to Raspberry Pi

1. **On your development machine:**
   ```bash
   ./scripts/build-ui.sh
   ```

2. **Copy `app-ui/` to Raspberry Pi:**
   ```bash
   scp -r app-ui pi@raspberrypi.local:~/sss2-gui/
   ```

3. **On Raspberry Pi:**
   ```bash
   cd ~/sss2-gui/app-ui
   pip install -r requirements.txt
   python main.py
   ```

4. **Access from browser:**
   ```
   http://raspberrypi.local:8000
   ```

**Note:** Node.js is NOT required on the Raspberry Pi. Only Python is needed in production.

## Development

### Backend Structure

- `routers/` - API route handlers (FastAPI routers)
- `services/` - Business logic layer (state, serial, ECU, snapshots)
- `middleware/` - Orchestrator for service coordination and background tasks
- `store/` - File-based JSON storage (FileStore abstraction)
- `tests/` - pytest tests

### Frontend Structure

- `src/lib/api/` - TypeScript API client
- `src/lib/stores/` - Svelte 5 runes-based state stores
- `src/lib/components/` - Reusable Svelte components
- `src/lib/pages/` - Page components (Dashboard, Settings, History)
- `src/routes/` - SvelteKit routes

## Remaining Work / Future Enhancements

### High Priority

- [ ] **VOUTs Configuration**
  - Add VOUTs tab in Settings
  - Implement VOUT control UI
  - Add backend serial commands for VOUTs
  - Create VOUT configuration components

- [ ] **PWM Configuration**
  - Add PWM tab in Settings
  - Implement PWM control UI (frequency, duty cycle)
  - Add backend serial commands for PWM
  - Create PWM configuration components

- [ ] **CAN Bus Configuration**
  - Add CAN tab in Settings
  - Implement CAN message configuration
  - Add CAN scanning/listening capabilities
  - Create CAN message display and editing

- [ ] **J1708 Configuration**
  - Add J1708 tab in Settings
  - Implement J1708 message configuration
  - Add backend serial commands for J1708
  - Create J1708 message display and editing

### Medium Priority

- [ ] **Error Handling & Recovery**
  - Better error messages for serial communication failures
  - Automatic retry logic for failed commands
  - Connection recovery strategies
  - User-facing error notifications

- [ ] **Testing**
  - Frontend component tests
  - Integration tests for state synchronization
  - End-to-end tests with mocked hardware
  - Serial communication mock for testing

- [ ] **Documentation**
  - API documentation (OpenAPI/Swagger)
  - Hardware command protocol documentation
  - Developer guide
  - User manual

### Low Priority / Nice to Have

- [ ] **Advanced Features**
  - Real-time data logging
  - Export/import configurations
  - Configuration templates
  - Batch operations (apply settings to multiple potentiometers)
  - Keyboard shortcuts for common operations

- [ ] **UI Enhancements**
  - Drag-and-drop for ECU pin configurations
  - Visual pin diagram/mapping
  - Settings search/filter
  - Customizable themes

- [ ] **Performance**
  - Optimize serial command batching
  - Reduce state file I/O operations
  - Frontend bundle size optimization
  - Caching strategies

## Known Issues / Limitations

- Serial commands use fire-and-forget mode; timeouts may occur but don't block the API
- State synchronization happens on connection but not on reconnection after brief disconnects
- No real-time monitoring of hardware state changes (read-only operations not implemented)
- ECU images are stored as base64 in JSON files (consider file upload for large images)

## Contributing

For questions or issues, contact Teddy Nyambe teddy@infinityworx.co

## Acknowledgments

Developed with coding assistance from [Claude](https://www.anthropic.com/claude) (Anthropic).

## License

MIT - All Rights Reserved
