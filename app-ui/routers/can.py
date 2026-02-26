"""CAN bus management endpoints."""
import json
import logging
import pathlib
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from middleware.orchestrator import Orchestrator
from services.monitor_service import MonitorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/can", tags=["can"])


# ---------- Models ----------

class ConnectRequest(BaseModel):
    interface: str
    channel: str
    bitrate: int = 250000


class ScanRequest(BaseModel):
    timeout_ms: int = 1250


class MonitorConnectRequest(BaseModel):
    channel: str
    bitrate: int = 250000


# ---------- Dependencies ----------

def get_orchestrator() -> Orchestrator:
    from main import get_orchestrator_instance
    return get_orchestrator_instance()


def get_monitor_service() -> MonitorService:
    from main import get_monitor_service_instance
    return get_monitor_service_instance()


# ---------- Endpoints ----------

@router.get("/interfaces")
async def list_interfaces(
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> list[dict[str, Any]]:
    """List available CAN interfaces detected on this host."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    return orchestrator.can_service.list_interfaces()


@router.get("/status")
async def get_status(
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Get current CAN connection status."""
    return orchestrator.can_status()


@router.post("/connect")
async def connect(
    req: ConnectRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Connect to a CAN interface and begin J1939 address claiming."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    try:
        result = await orchestrator.can_service.connect(req.interface, req.channel, req.bitrate)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/disconnect")
async def disconnect(
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Disconnect from CAN bus."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    return await orchestrator.can_service.disconnect()


@router.post("/scan")
async def scan_nodes(
    req: ScanRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Scan the J1939 network for nodes. Returns discovered nodes keyed by SA."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    try:
        nodes = await orchestrator.can_service.scan_nodes(timeout_ms=req.timeout_ms)
        return {"nodes": {str(sa): info for sa, info in nodes.items()}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/nodes")
async def get_nodes(
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Return cached node discovery results."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    nodes = orchestrator.can_service.get_nodes()
    return {"nodes": {str(sa): info for sa, info in nodes.items()}}


@router.get("/frames")
async def get_ecu_frames(
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Return buffered ECU CAN frames (up to 500 most recent)."""
    if not orchestrator.can_service:
        raise HTTPException(status_code=503, detail="CAN service not initialized")
    return {"frames": orchestrator.can_service.get_ecu_frames()}


@router.get("/spn-db")
async def get_spn_db() -> JSONResponse:
    """Return the J1939 SPN database generated from the J1939DA Excel."""
    p = pathlib.Path(__file__).parent.parent / "j1939db/spn_db.json"
    return JSONResponse(json.loads(p.read_text()) if p.exists() else {})


# ---------- Monitor bus endpoints ----------

@router.post("/monitor/connect")
async def monitor_connect(
    req: MonitorConnectRequest,
    monitor: MonitorService = Depends(get_monitor_service),
) -> dict:
    """Open an additional CAN bus for receive-only monitoring."""
    try:
        return await monitor.connect(req.channel, req.bitrate)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/monitor/{channel}")
async def monitor_disconnect(
    channel: str,
    monitor: MonitorService = Depends(get_monitor_service),
) -> dict:
    """Stop monitoring a CAN bus."""
    await monitor.disconnect(channel)
    return {"status": "disconnected", "channel": channel}


@router.get("/monitor/status")
async def monitor_status(
    monitor: MonitorService = Depends(get_monitor_service),
) -> list:
    """Return connection status for all active monitor buses."""
    return monitor.status()
