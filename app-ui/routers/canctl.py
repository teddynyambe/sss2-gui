"""CAN network-interface control (OS level): bring can0/can1 up & down.

Distinct from routers/can.py — that manages the J1939 *application* bus
(python-can, address claiming) on top of an already-up interface. These endpoints
control the SocketCAN *link* itself by driving the templated `can@.service` units,
so the same mechanism powers boot-time bring-up and the UI start/stop buttons.

Requires a sudoers rule (deploy/sudoers/sss2-can) letting the backend user run
`systemctl start|stop can@canN.service` without a password.
"""
import asyncio
import json
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canctl", tags=["canctl"])

# Allow-list: only these interfaces may be controlled from the API. This is the
# security boundary — the path parameter is matched against it before any command
# runs, so it can never be used to inject an arbitrary interface/command.
ALLOWED_INTERFACES = ("can0", "can1")

SYSTEMCTL = "/usr/bin/systemctl"
IP = "/usr/sbin/ip"


class IfaceState(BaseModel):
    name: str
    present: bool          # interface exists in the kernel (MCP2515 overlay loaded)
    up: bool               # link is administratively UP
    bitrate: int | None = None


class CanCtlStatus(BaseModel):
    interfaces: list[IfaceState]


class IfaceActionResponse(BaseModel):
    name: str
    ok: bool
    up: bool
    detail: str


async def _run(*cmd: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a command; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail=f"Timed out: {' '.join(cmd)}")
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _validate(iface: str) -> str:
    if iface not in ALLOWED_INTERFACES:
        raise HTTPException(status_code=400, detail=f"Interface not allowed: {iface!r}")
    return iface


async def _iface_state(iface: str) -> IfaceState:
    rc, out, _ = await _run(IP, "-details", "-json", "link", "show", iface)
    if rc != 0 or not out.strip():
        return IfaceState(name=iface, present=False, up=False)
    try:
        info = json.loads(out)[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        return IfaceState(name=iface, present=True, up=False)
    # For SocketCAN, IFF_UP shows in flags when the link is brought up; operstate
    # is often UNKNOWN even when up, so trust the flag.
    up = "UP" in info.get("flags", []) or info.get("operstate") == "UP"
    bitrate = None
    info_data = info.get("linkinfo", {}).get("info_data", {})
    if isinstance(info_data, dict):
        bitrate = info_data.get("bitrate")
    return IfaceState(name=iface, present=True, up=up, bitrate=bitrate)


@router.get("/status", response_model=CanCtlStatus)
async def status_all() -> CanCtlStatus:
    """State of every controllable CAN interface."""
    return CanCtlStatus(interfaces=[await _iface_state(i) for i in ALLOWED_INTERFACES])


@router.post("/{iface}/up", response_model=IfaceActionResponse)
async def iface_up(iface: str) -> IfaceActionResponse:
    """Bring an interface UP via `systemctl start can@<iface>`."""
    iface = _validate(iface)
    rc, out, err = await _run("sudo", "-n", SYSTEMCTL, "start", f"can@{iface}.service")
    state = await _iface_state(iface)
    if not state.up:
        detail = (err or out).strip() or f"systemctl exited {rc}"
        raise HTTPException(status_code=500, detail=f"Could not bring up {iface}: {detail}")
    logger.info(f"{iface} brought UP (bitrate={state.bitrate})")
    return IfaceActionResponse(name=iface, ok=True, up=True, detail=f"{iface} is up")


@router.post("/{iface}/down", response_model=IfaceActionResponse)
async def iface_down(iface: str) -> IfaceActionResponse:
    """Bring an interface DOWN via `systemctl stop can@<iface>`."""
    iface = _validate(iface)
    rc, out, err = await _run("sudo", "-n", SYSTEMCTL, "stop", f"can@{iface}.service")
    state = await _iface_state(iface)
    if state.up:
        detail = (err or out).strip() or f"systemctl exited {rc}"
        raise HTTPException(status_code=500, detail=f"Could not bring down {iface}: {detail}")
    logger.info(f"{iface} brought DOWN")
    return IfaceActionResponse(name=iface, ok=True, up=False, detail=f"{iface} is down")
