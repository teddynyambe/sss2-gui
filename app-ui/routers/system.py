"""On-device system administration for the kiosk appliance (PIN-gated).

Powers the UI Admin panel: exit the kiosk to a console or the desktop, restart the
GUI or the whole app, pull an update, reboot, or shut down.

Security model:
- The backend never holds broad root. Every privileged action is dispatched to a
  single ROOT-OWNED helper (`KIOSK_ADMIN_HELPER`) that is allowed via a narrow
  sudoers rule and validates its own argument. Editing the repo can't escalate.
- The API is reachable on the LAN, so every call requires the admin PIN
  (constant-time compared). If no PIN is configured, admin actions are disabled.
"""
import asyncio
import hmac
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system"])

# Actions performed by the root-owned helper (it re-validates them itself).
HELPER_ACTIONS = {"exit-console", "exit-desktop", "restart-gui", "restart-app", "reboot", "shutdown"}
# Actions that tear down the service handling THIS request → run detached so the
# HTTP response returns before the backend/kiosk goes away.
DETACHED_ACTIONS = {"restart-app", "reboot", "shutdown", "update"}
ALL_ACTIONS = HELPER_ACTIONS | {"update"}


class ActionRequest(BaseModel):
    action: str
    pin: str


def _check_pin(pin: str) -> None:
    configured = settings.SYSTEM_ADMIN_PIN or ""
    if not configured:
        raise HTTPException(status_code=503, detail="Admin actions are disabled (SYSTEM_ADMIN_PIN not set)")
    if not hmac.compare_digest(str(pin), configured):
        raise HTTPException(status_code=403, detail="Invalid PIN")


async def _spawn(cmd: list[str], *, detached: bool) -> None:
    if detached:
        # start_new_session detaches from the backend's process group so it
        # survives the very restart/reboot it triggers.
        await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        return
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        detail = (err or out).decode(errors="replace").strip() or "action failed"
        raise HTTPException(status_code=500, detail=detail)


@router.get("/status")
async def system_status() -> dict:
    """Whether the admin panel is usable (a PIN is configured)."""
    return {"admin_enabled": bool(settings.SYSTEM_ADMIN_PIN)}


@router.post("/action")
async def system_action(req: ActionRequest) -> dict:
    """Run a PIN-gated maintenance action."""
    _check_pin(req.pin)
    action = req.action
    if action not in ALL_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")

    if action == "update":
        # student-level build + privileged restart, in one detached script
        cmd = ["/bin/bash", str(settings.BASE_DIR.parent / "deploy" / "scripts" / "kiosk-update.sh")]
    else:
        cmd = ["sudo", "-n", settings.KIOSK_ADMIN_HELPER, action]

    detached = action in DETACHED_ACTIONS
    logger.warning(f"Admin action requested: {action} (detached={detached})")
    await _spawn(cmd, detached=detached)
    return {"ok": True, "action": action, "detached": detached}
