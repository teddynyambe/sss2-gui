"""SSS2 device control endpoints (J1939 CAN transport)."""
import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from middleware.orchestrator import Orchestrator
from services.can_service import CANConnectionError, CANTimeoutError, GUI_SA
from services.state_service import StateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sss2", tags=["sss2"])


# ---------- Models ----------

class IgnitionRequest(BaseModel):
    on: bool
    sss2_sa: int = 0x80  # default SSS2 SA


class IgnitionResponse(BaseModel):
    accepted: bool
    executed: bool
    detail: str
    ignition: bool


class StateUpdate(BaseModel):
    state: dict[str, Any]
    sss2_sa: int = 0x80


# ---------- Dependencies ----------

def get_orchestrator() -> Orchestrator:
    from main import get_orchestrator_instance
    return get_orchestrator_instance()


def get_state_service(orchestrator: Orchestrator = Depends(get_orchestrator)) -> StateService:
    if not orchestrator.state_service:
        raise HTTPException(status_code=503, detail="State service not initialized")
    return orchestrator.state_service


# ---------- Helpers: settings → state dict ----------

def _settings_to_state(settings: dict[int, int], sss2_sa: int) -> dict[str, Any]:
    """
    Convert raw settings dict {1..93: int16} to GUI state structure.

    Mapping (from SSS2 firmware documentation):
      1-16  → potentiometer wiper positions (po1-po16)
      17-24 → DAC outputs (vouts)
      25-32 → potentiometer power group voltage setting
      33-36 → PWM duty cycles
      50    → ignition relay
      51-66 → potentiometer terminal connection modes (enabled flag)
    """
    pots: dict[str, Any] = {}
    power_groups: dict[str, Any] = {}

    # Wiper positions (settings 1-16)
    for i in range(1, 17):
        pot_id = f"po{i}"
        wiper = settings.get(i, 0)
        pots[pot_id] = {"wiper_position": wiper, "voltage": 0.0, "enabled": False}

    # Potentiometer power groups (settings 25-32 → groups 1-8)
    for i in range(25, 33):
        group_id = i - 24  # 25→1, …, 32→8
        voltage_val = settings.get(i, 0)
        group_key = f"group_{group_id}"
        power_groups[group_key] = {
            "group_id": group_key,
            "voltage_setting": "12V" if voltage_val else "5V",
            "potentiometers": [f"po{(group_id - 1)*2 + 1}", f"po{(group_id - 1)*2 + 2}"],
        }

    # Update voltages from power groups
    for group_id in range(1, 9):
        group_key = f"group_{group_id}"
        max_v = 12.0 if power_groups[group_key]["voltage_setting"] == "12V" else 5.0
        for pot_num in [(group_id - 1)*2 + 1, (group_id - 1)*2 + 2]:
            pot_id = f"po{pot_num}"
            wiper = pots[pot_id]["wiper_position"]
            pots[pot_id]["voltage"] = (wiper / 255.0) * max_v

    # Enabled state from terminal connection modes (settings 51-66)
    for i in range(51, 67):
        port = i - 50  # 51→1, …, 66→16
        pot_id = f"po{port}"
        mode_val = settings.get(i, 3)
        pots[pot_id]["enabled"] = mode_val == 7

    ignition = bool(settings.get(50, 0))

    return {
        "sss2_sa": sss2_sa,
        "last_updated": None,  # filled by state_service.set_state()
        "ignition": ignition,
        "potentiometers": pots,
        "potentiometer_power_groups": power_groups,
        "vouts": {},
        "pwms": {},
        "can": {},
        "j1708": {},
    }


# ---------- Endpoints ----------

@router.get("/state")
async def get_state(
    sss2_sa: int = Query(default=0x80, description="SSS2 source address"),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    state_service: StateService = Depends(get_state_service),
) -> dict[str, Any]:
    """
    Fetch all SSS2 settings via J1939 GET_SETTING and return as state dict.
    If CAN is not claimed, return cached state.
    """
    if not orchestrator.can_service or not orchestrator.can_service.is_connected():
        logger.info("CAN not claimed — returning cached state")
        return state_service.get_state()

    try:
        settings = await orchestrator.can_service.get_all_settings(sss2_sa)
        new_state = _settings_to_state(settings, sss2_sa)
        state_service.set_state(new_state)
        return state_service.get_state()
    except Exception as e:
        logger.warning(f"Failed to fetch settings from SSS2: {e}")
        return state_service.get_state()


@router.put("/state")
async def update_state(
    update: StateUpdate,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    state_service: StateService = Depends(get_state_service),
) -> dict[str, Any]:
    """Apply state changes to SSS2 hardware via CAN SET_SETTING."""
    if not orchestrator.can_service or not orchestrator.can_service.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CAN bus not connected / address not claimed",
        )
    try:
        updated_state = state_service.update_state(update.state)
        asyncio.create_task(
            orchestrator.apply_state_changes(update.sss2_sa, update.state)
        )
        return updated_state
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ignition", response_model=IgnitionResponse)
async def set_ignition(
    request: Request,
    req: IgnitionRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> IgnitionResponse:
    """Set ignition ON or OFF via J1939 SET_SETTING(50, 0/1)."""
    logger.info(f"Ignition request: on={req.on}, sss2_sa=0x{req.sss2_sa:02X}")

    if not orchestrator.can_service or not orchestrator.can_service.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CAN bus not connected / address not claimed",
        )

    try:
        if req.on:
            ok = await orchestrator.engine_start(req.sss2_sa)
            detail = "SSS2 ignition relay ON (setting 50,1) executed."
        else:
            ok = await orchestrator.engine_stop(req.sss2_sa)
            detail = "SSS2 ignition relay OFF (setting 50,0) executed."

        return IgnitionResponse(
            accepted=True,
            executed=ok,
            detail=detail,
            ignition=req.on,
        )

    except CANConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"CAN not connected: {e}",
        ) from e

    except CANTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Command timed out: {e}",
        ) from e

    except Exception as e:
        logger.error(f"Ignition request failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
