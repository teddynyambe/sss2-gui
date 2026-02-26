"""CAN connection status — REST and WebSocket endpoints."""
import asyncio
import logging
from typing import Any, Set

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from middleware.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connection", tags=["connection"])

_active_ws: Set[WebSocket] = set()


# ---------- Models ----------

class CANStatusResponse(BaseModel):
    connected: bool
    interface: str
    channel: str
    bitrate: int
    sa: int
    address_claimed: bool
    state: str


# ---------- Dependency ----------

def get_orchestrator() -> Orchestrator:
    from main import get_orchestrator_instance
    return get_orchestrator_instance()


# ---------- Broadcast helpers ----------

def broadcast_can_status(status: dict[str, Any]) -> None:
    """Broadcast CAN status to all WebSocket clients."""
    payload = {"type": "can_status", **status}
    disconnected: Set[WebSocket] = set()
    for ws in _active_ws.copy():
        try:
            asyncio.create_task(ws.send_json(payload))
        except Exception as e:
            logger.debug(f"WS send failed: {e}")
            disconnected.add(ws)
    for ws in disconnected:
        _active_ws.discard(ws)


def broadcast_node_discovered(sa: int, node_info: dict[str, Any]) -> None:
    """Broadcast a newly discovered J1939 node to all WebSocket clients."""
    payload = {
        "type": "node_discovered",
        "sa": sa,
        **node_info,
    }
    for ws in _active_ws.copy():
        try:
            asyncio.create_task(ws.send_json(payload))
        except Exception:
            pass


def broadcast_state_fetched(sss2_sa: int, settings: dict[int, int]) -> None:
    """Broadcast state_fetched after GET_ALL_SETTINGS completes."""
    payload = {
        "type": "state_fetched",
        "sss2_sa": sss2_sa,
        "settings": {str(k): v for k, v in settings.items()},
    }
    for ws in _active_ws.copy():
        try:
            asyncio.create_task(ws.send_json(payload))
        except Exception:
            pass


async def _broadcast_ecu_frame(frame: dict[str, Any]) -> None:
    """Broadcast an ECU CAN frame to all connected WebSocket clients."""
    payload = {"type": "ecu_frame", "frame": frame}
    for ws in _active_ws.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            pass


_ecu_callback_registered = False


# ---------- REST ----------

@router.get("/status", response_model=CANStatusResponse)
async def get_status(orchestrator: Orchestrator = Depends(get_orchestrator)):
    """Return current CAN connection status."""
    return orchestrator.can_status()


# ---------- WebSocket ----------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _active_ws.add(websocket)
    logger.info(f"WS client connected. Total: {len(_active_ws)}")

    orchestrator = get_orchestrator()

    def _on_can_state(status: dict[str, Any]) -> None:
        try:
            asyncio.create_task(websocket.send_json({"type": "can_status", **status}))
        except Exception:
            pass

    def _on_node_discovered(sa: int, node_info: dict[str, Any]) -> None:
        try:
            asyncio.create_task(websocket.send_json({
                "type": "node_discovered",
                "sa": sa,
                **node_info,
            }))
        except Exception:
            pass

    orchestrator.register_connection_callback(_on_can_state)
    if orchestrator.can_service:
        orchestrator.can_service.register_node_callback(_on_node_discovered)
        # Register the broadcast ECU frame callback once (shared across all WS clients)
        global _ecu_callback_registered
        if not _ecu_callback_registered:
            orchestrator.can_service.set_ecu_ws_callback(_broadcast_ecu_frame)
            _ecu_callback_registered = True

    try:
        # Send current status immediately
        await websocket.send_json({"type": "can_status", **orchestrator.can_status()})

        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception as e:
        logger.error(f"WS error: {e}", exc_info=True)
    finally:
        _active_ws.discard(websocket)
        orchestrator.unregister_connection_callback(_on_can_state)
        if orchestrator.can_service:
            orchestrator.can_service.unregister_node_callback(_on_node_discovered)
        logger.info(f"WS client gone. Total: {len(_active_ws)}")
