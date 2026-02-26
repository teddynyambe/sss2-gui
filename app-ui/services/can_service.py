"""J1939 CAN bus service for SSS2 communication."""
import asyncio
import json
import logging
import pathlib
import struct
import sys
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

# ---------- J1939 NAME database ----------
_J1939_DB_PATH = pathlib.Path(__file__).parent.parent / "j1939db" / "j1939.json"
_J1939_DB: Dict[str, Any] = json.loads(_J1939_DB_PATH.read_text()) if _J1939_DB_PATH.exists() else {}

logger = logging.getLogger(__name__)

# ---------- GUI J1939 identity ----------
GUI_SA = 0x82
GUI_NAME = 0x81008109E9000001
GUI_NAME_BYTES = bytes([0x01, 0x00, 0x00, 0xE9, 0x09, 0x81, 0x00, 0x81])  # LSB-first

# ---------- SSS2 J1939 service command bytes (PGN 0xEF00) ----------
J1939_SVC_SET_SETTING = 0x01
J1939_SVC_GET_SETTING = 0x02
J1939_SVC_RESPONSE    = 0x80
J1939_SVC_STATUS_OK   = 0x00

# Number of SSS2 settings (1-93)
SSS2_SETTING_COUNT = 93


class CANState(str, Enum):
    DISCONNECTED  = "disconnected"
    CONNECTING    = "connecting"
    CLAIMING      = "claiming"
    CLAIMED       = "claimed"
    CANNOT_CLAIM  = "cannot_claim"


# ---------- CAN ID helpers ----------

def _j1939_pgn1_id(priority: int, dp: int, pf: int, ps: int, sa: int) -> int:
    """Build a 29-bit J1939 PDU1 CAN arbitration ID."""
    return (
        ((priority & 0x7) << 26)
        | ((dp & 0x1) << 24)
        | ((pf & 0xFF) << 16)
        | ((ps & 0xFF) << 8)
        | (sa & 0xFF)
    )


# Pre-computed IDs used by the GUI
_ADDR_CLAIM_ID   = _j1939_pgn1_id(6, 0, 0xEE, 0xFF, GUI_SA)   # 18EEFF82
_CANNOT_CLAIM_ID = _j1939_pgn1_id(6, 0, 0xEE, 0xFF, 0xFE)     # 18EEFFFE
_REQUEST_AC_ID   = _j1939_pgn1_id(6, 0, 0xEA, 0xFF, GUI_SA)   # 18EAFF82
_REQUEST_AC_DATA = bytes([0x00, 0xEE, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])


def _svc_req_id(sss2_sa: int) -> int:
    return _j1939_pgn1_id(3, 0, 0xEF, sss2_sa, GUI_SA)


def _is_addr_claim(msg_id: int) -> bool:
    """True if msg is an Address Claim (PF=0xEE, PS=0xFF, any SA)."""
    pf = (msg_id >> 16) & 0xFF
    ps = (msg_id >> 8) & 0xFF
    return pf == 0xEE and ps == 0xFF


def _is_request_pgn(msg_id: int) -> bool:
    """True if msg is a J1939 Request PGN (PF=0xEA) — broadcast or addressed to us."""
    pf = (msg_id >> 16) & 0xFF
    ps = (msg_id >> 8) & 0xFF
    return pf == 0xEA and (ps == 0xFF or ps == GUI_SA)


def _requested_pgn_is_ac(data: bytes) -> bool:
    """True if the 3-byte requested PGN (LE) is the Address Claim PGN (0x00EE00)."""
    if len(data) < 3:
        return False
    pgn = data[0] | (data[1] << 8) | (data[2] << 16)
    return pgn == 0x00EE00


def _is_svc_response(msg_id: int) -> bool:
    """True if this is a J1939 Prop-A response (PF=0xEF) addressed to GUI_SA."""
    pf = (msg_id >> 16) & 0xFF
    da = (msg_id >> 8) & 0xFF
    return pf == 0xEF and da == GUI_SA


def _sa_from_id(msg_id: int) -> int:
    return msg_id & 0xFF


def _pgn_str(mid: int) -> str:
    """Return the PGN as a 5-char hex string from a 29-bit J1939 arb ID."""
    pf = (mid >> 16) & 0xFF
    ps = (mid >> 8) & 0xFF
    dp = (mid >> 24) & 0x01
    if pf < 0xF0:
        return f"{(dp << 17) | (pf << 8):05X}"
    return f"{(dp << 17) | (pf << 8) | ps:05X}"


def _name_from_bytes(data: bytes) -> int:
    """Decode 8-byte LSB-first NAME to integer."""
    return struct.unpack_from("<Q", data)[0]


def _is_sss2_name(name_int: int) -> bool:
    """
    Identify SSS2 nodes by J1939 NAME.
    SSS2 CAN0 NAME: 0x8122840901600001  (high byte 0x81, Vehicle System Instance 1)
    SSS2 CAN1 NAME: 0x8322840901600001  (high byte 0x83, Vehicle System Instance 2)
    Both share lower 32 bits 0x01600001.
    """
    low32 = name_int & 0xFFFFFFFF
    high8 = (name_int >> 56) & 0xFF
    return low32 == 0x01600001 and high8 in (0x81, 0x83)


def decode_j1939_name(name_int: int) -> Dict[str, str]:
    """
    Decode a 64-bit J1939 NAME integer into human-readable fields.

    Bit layout (J1939-81, 1-based bit numbers, Byte 1 = data[0] = LSB):
      Field 1  Identity Number      bits  1-21   (21 bits)
      Field 2  Manufacturer Code    bits 22-32   (11 bits)
      Field 3  ECU Instance         bits 33-35   ( 3 bits)
      Field 4  Function Instance    bits 36-40   ( 5 bits)
      Field 5  Function Code        bits 41-48   ( 8 bits)
      Field 6  Reserved             bit  49      ( 1 bit )
      Field 7  Device Class (VS)    bits 50-56   ( 7 bits)
      Field 8  Device Class Inst    bits 57-60   ( 4 bits)
      Field 9  Industry Group       bits 61-63   ( 3 bits)
      Field 10 Self-Config Addr     bit  64      ( 1 bit )

    Returns a dict with keys: manufacturer, industry_group, vehicle_system,
    function, label.  Missing DB entries fall back to empty string.
    """
    ig  = (name_int >> 60) & 0x07   # Industry Group      (bits 61-63, shift 60)
    mfr = (name_int >> 21) & 0x7FF  # Manufacturer Code   (bits 22-32, shift 21)
    vs  = (name_int >> 49) & 0x7F   # Device Class        (bits 50-56, shift 49, 7 bits)
    fn  = (name_int >> 40) & 0xFF   # Function Code       (bits 41-48, shift 40)

    ig_str  = str(ig)
    mfr_str = str(mfr)
    vs_str  = str(vs)
    fn_str  = str(fn)

    industry_group   = _J1939_DB.get("industry_groups", {}).get(ig_str, "")
    manufacturer     = _J1939_DB.get("manufacturer_codes", {}).get(mfr_str, "")

    if fn < 128:
        function     = _J1939_DB.get("functions_global", {}).get(fn_str, "")
        vehicle_system = ""
    else:
        ig_data      = _J1939_DB.get("ig_specific", {}).get(ig_str, {})
        vehicle_system = ig_data.get("vehicle_systems", {}).get(vs_str, "")
        function     = ig_data.get("functions", {}).get(vs_str, {}).get(fn_str, "")

    if function and manufacturer:
        label = f"{function} ({manufacturer})"
    elif function:
        label = function
    elif manufacturer:
        label = manufacturer
    else:
        label = ""

    return {
        "manufacturer":    manufacturer,
        "industry_group":  industry_group,
        "vehicle_system":  vehicle_system,
        "function":        function,
        "label":           label,
    }


class CANConnectionError(Exception):
    """Raised when CAN bus is not connected."""


class CANTimeoutError(Exception):
    """Raised when a CAN service request times out."""


class CANService:
    """
    J1939 CAN bus service.

    Implements J1939 address claiming (J1939-81), network scanning,
    and GET/SET setting requests to SSS2 nodes.
    """

    def __init__(self) -> None:
        self._bus = None                              # python-can Bus instance
        self._state = CANState.DISCONNECTED
        self._interface: str = ""
        self._channel: str = ""
        self._bitrate: int = 250000
        self._rx_task: Optional[asyncio.Task] = None
        self._claim_task: Optional[asyncio.Task] = None  # 250ms claiming timer task
        self._nodes: Dict[int, Dict[str, Any]] = {}  # sa → {name_int, name_hex, is_sss2}
        self._svc_waiters: Dict[int, asyncio.Future] = {}
        self._svc_lock = asyncio.Lock()          # serialise service calls
        self._state_callbacks: Set[Callable] = set()
        self._node_callbacks: Set[Callable] = set()
        self._ecu_frames: deque = deque(maxlen=500)
        self._ecu_ws_callback: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("CANService ready (not connected to bus yet)")

    async def stop(self) -> None:
        await self.disconnect()
        logger.info("CANService stopped")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, interface: str, channel: str, bitrate: int) -> Dict[str, Any]:
        """Open CAN bus and begin J1939 address claiming."""
        if self._state not in (CANState.DISCONNECTED, CANState.CANNOT_CLAIM):
            raise CANConnectionError(f"Already in state {self._state}")

        try:
            import can
            self._bus = can.Bus(
                interface=interface,
                channel=channel,
                bitrate=bitrate,
                receive_own_messages=False,
            )
        except Exception as e:
            raise CANConnectionError(f"Failed to open CAN bus: {e}") from e

        self._interface = interface
        self._channel = channel
        self._bitrate = bitrate
        self._nodes.clear()
        self._set_state(CANState.CONNECTING)

        # Start RX loop task
        self._rx_task = asyncio.create_task(self._rx_loop())

        # Send Address Claim and start 250ms claiming task
        self._send_address_claim()
        self._set_state(CANState.CLAIMING)
        self._restart_claim_timer()

        return self.status()

    async def disconnect(self) -> Dict[str, Any]:
        """Cancel tasks and close bus."""
        self._cancel_claim_timer()

        if self._rx_task:
            self._rx_task.cancel()
            try:
                await self._rx_task
            except asyncio.CancelledError:
                pass
            self._rx_task = None

        if self._bus:
            try:
                self._bus.shutdown()
            except Exception:
                pass
            self._bus = None

        for fut in self._svc_waiters.values():
            if not fut.done():
                fut.cancel()
        self._svc_waiters.clear()

        self._set_state(CANState.DISCONNECTED)
        return self.status()

    # ------------------------------------------------------------------
    # Claim timer helpers (use async task, not call_later)
    # ------------------------------------------------------------------

    def _restart_claim_timer(self) -> None:
        """Cancel any existing claim timer and start a fresh 250ms one."""
        self._cancel_claim_timer()
        self._claim_task = asyncio.create_task(self._claiming_delay())

    def _cancel_claim_timer(self) -> None:
        if self._claim_task and not self._claim_task.done():
            self._claim_task.cancel()
        self._claim_task = None

    async def _claiming_delay(self) -> None:
        """Wait 250ms, then claim the address if no contention occurred (J1939-81)."""
        try:
            await asyncio.sleep(0.25)
            if self._state == CANState.CLAIMING:
                logger.info(f"Address 0x{GUI_SA:02X} claimed — no contention in 250ms")
                self._set_state(CANState.CLAIMED)
        except asyncio.CancelledError:
            pass  # Timer was restarted or service is stopping

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def register_state_callback(self, cb: Callable) -> None:
        self._state_callbacks.add(cb)

    def unregister_state_callback(self, cb: Callable) -> None:
        self._state_callbacks.discard(cb)

    def register_node_callback(self, cb: Callable) -> None:
        self._node_callbacks.add(cb)

    def unregister_node_callback(self, cb: Callable) -> None:
        self._node_callbacks.discard(cb)

    # ------------------------------------------------------------------
    # Interface discovery
    # ------------------------------------------------------------------

    def list_interfaces(self) -> list[Dict[str, Any]]:
        """Return available CAN interfaces detected on this host."""
        results: list[Dict[str, Any]] = []
        try:
            import can
            configs = can.detect_available_configs()
            for cfg in configs:
                results.append({
                    "interface": cfg.get("interface", ""),
                    "channel": cfg.get("channel", ""),
                    "bitrate": cfg.get("bitrate", 250000),
                    "description": f"{cfg.get('interface', '')} — {cfg.get('channel', '')}",
                })
        except Exception as e:
            logger.warning(f"can.detect_available_configs() failed: {e}")

        if not results:
            results = self._platform_fallbacks()

        return results

    def _platform_fallbacks(self) -> list[Dict[str, Any]]:
        import os
        fallbacks: list[Dict[str, Any]] = []
        if sys.platform.startswith("linux"):
            try:
                for name in os.listdir("/sys/class/net"):
                    if name.startswith("can"):
                        fallbacks.append({
                            "interface": "socketcan",
                            "channel": name,
                            "bitrate": 250000,
                            "description": f"socketcan — {name}",
                        })
            except Exception:
                pass
        for idx in range(1, 9):
            fallbacks.append({
                "interface": "pcan",
                "channel": f"PCAN_USBBUS{idx}",
                "bitrate": 250000,
                "description": f"PCAN USB Bus {idx}",
            })
        return fallbacks

    # ------------------------------------------------------------------
    # Network scan
    # ------------------------------------------------------------------

    async def scan_nodes(self, timeout_ms: int = 1250) -> Dict[int, Dict[str, Any]]:
        """Send Request for Address Claim, collect responses, return node dict."""
        if self._state not in (CANState.CLAIMED, CANState.CLAIMING):
            raise CANConnectionError("CAN bus not connected / address not claimed")

        self._nodes.clear()

        try:
            import can
            msg = can.Message(
                arbitration_id=_REQUEST_AC_ID,
                data=_REQUEST_AC_DATA,
                is_extended_id=True,
            )
            self._bus.send(msg)
            logger.info("Sent Request for Address Claim (scan)")
        except Exception as e:
            raise CANConnectionError(f"Failed to send scan request: {e}") from e

        await asyncio.sleep(timeout_ms / 1000.0)
        return dict(self._nodes)

    # ------------------------------------------------------------------
    # J1939 service (GET / SET)
    # ------------------------------------------------------------------

    async def get_setting(self, sss2_sa: int, setting: int,
                          timeout: float = 2.0) -> int:
        """Send GET_SETTING request; return int16 value."""
        if self._state != CANState.CLAIMED:
            raise CANConnectionError("Address not claimed")

        async with self._svc_lock:
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._svc_waiters[setting] = fut

            data = bytes([J1939_SVC_GET_SETTING, setting & 0xFF,
                          0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
            try:
                import can
                self._bus.send(can.Message(
                    arbitration_id=_svc_req_id(sss2_sa),
                    data=data,
                    is_extended_id=True,
                ))
            except Exception as e:
                self._svc_waiters.pop(setting, None)
                raise CANConnectionError(f"Failed to send GET_SETTING: {e}") from e

            try:
                return await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                self._svc_waiters.pop(setting, None)
                raise CANTimeoutError(f"GET_SETTING({setting}) timed out")

    async def get_all_settings(self, sss2_sa: int) -> Dict[int, int]:
        """Fetch settings 1-93 sequentially. Returns {1: v, 2: v, ...}."""
        results: Dict[int, int] = {}
        for n in range(1, SSS2_SETTING_COUNT + 1):
            try:
                results[n] = await self.get_setting(sss2_sa, n)
            except Exception as e:
                logger.warning(f"get_setting({n}) failed: {e}")
                results[n] = 0
        return results

    async def set_setting(self, sss2_sa: int, setting: int, value: int,
                          timeout: float = 2.0) -> bool:
        """Send SET_SETTING request; wait for ACK; return True on success."""
        if self._state != CANState.CLAIMED:
            raise CANConnectionError("Address not claimed")

        async with self._svc_lock:
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._svc_waiters[setting] = fut

            lo = value & 0xFF
            hi = (value >> 8) & 0xFF
            data = bytes([J1939_SVC_SET_SETTING, setting & 0xFF, lo, hi, 0xFF, 0xFF, 0xFF, 0xFF])
            try:
                import can
                self._bus.send(can.Message(
                    arbitration_id=_svc_req_id(sss2_sa),
                    data=data,
                    is_extended_id=True,
                ))
            except Exception as e:
                self._svc_waiters.pop(setting, None)
                raise CANConnectionError(f"Failed to send SET_SETTING: {e}") from e

            try:
                await asyncio.wait_for(fut, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                self._svc_waiters.pop(setting, None)
                raise CANTimeoutError(f"SET_SETTING({setting}) timed out")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self._state not in (CANState.DISCONNECTED, CANState.CANNOT_CLAIM),
            "interface": self._interface,
            "channel": self._channel,
            "bitrate": self._bitrate,
            "sa": GUI_SA,
            "address_claimed": self._state == CANState.CLAIMED,
            "state": self._state.value,
        }

    def get_nodes(self) -> Dict[int, Dict[str, Any]]:
        return dict(self._nodes)

    def is_connected(self) -> bool:
        return self._state == CANState.CLAIMED

    def set_ecu_ws_callback(self, cb: Optional[Callable]) -> None:
        self._ecu_ws_callback = cb

    def get_ecu_frames(self) -> list:
        return list(self._ecu_frames)

    # ------------------------------------------------------------------
    # Address claim / cannot-claim TX
    # ------------------------------------------------------------------

    def _send_address_claim(self) -> None:
        if not self._bus:
            return
        try:
            import can
            self._bus.send(can.Message(
                arbitration_id=_ADDR_CLAIM_ID,
                data=GUI_NAME_BYTES,
                is_extended_id=True,
            ))
            logger.info(f"TX Address Claim SA=0x{GUI_SA:02X}  ID=18EEFF{GUI_SA:02X}")
        except Exception as e:
            logger.error(f"Failed to send Address Claim: {e}")

    def _send_cannot_claim(self) -> None:
        if not self._bus:
            return
        try:
            import can
            self._bus.send(can.Message(
                arbitration_id=_CANNOT_CLAIM_ID,
                data=GUI_NAME_BYTES,
                is_extended_id=True,
            ))
            logger.warning("TX Cannot Claim Address  ID=18EEFFFE")
        except Exception as e:
            logger.error(f"Failed to send Cannot Claim: {e}")

    # ------------------------------------------------------------------
    # RX dispatch helpers
    # ------------------------------------------------------------------

    def _handle_addr_claim(self, msg_id: int, data: bytes) -> None:
        """Process an incoming Address Claim (18EEFFxx)."""
        their_sa = _sa_from_id(msg_id)
        if len(data) < 8:
            return

        their_name = _name_from_bytes(data)
        their_name_hex = f"0x{their_name:016X}"
        is_sss2 = _is_sss2_name(their_name)
        decoded = decode_j1939_name(their_name) if not is_sss2 else {}

        self._nodes[their_sa] = {
            "name_int": their_name,
            "name_hex": their_name_hex,
            "is_sss2": is_sss2,
            **decoded,
        }

        for cb in list(self._node_callbacks):
            try:
                cb(their_sa, self._nodes[their_sa])
            except Exception as e:
                logger.error(f"Node callback error: {e}")

        # Contention: another node is claiming our SA
        if their_sa == GUI_SA:
            if their_name < GUI_NAME:
                # They win — we lose the address
                logger.warning(
                    f"Address contention LOST: peer NAME 0x{their_name:016X} < ours → Cannot Claim")
                self._cancel_claim_timer()
                self._send_cannot_claim()
                self._set_state(CANState.CANNOT_CLAIM)
            else:
                # We win — reassert and restart 250ms timer
                logger.info(
                    f"Address contention WON: peer NAME 0x{their_name:016X} > ours → re-asserting")
                self._send_address_claim()
                self._restart_claim_timer()

    def _handle_request_for_ac(self, data: bytes) -> None:
        """
        Respond to a Request for Address Claim (J1939-81 §4.4.2).

        Any node that holds a valid SA must re-send its Address Claim.
        If still in the CLAIMING phase, re-send and restart the 250ms timer.
        If address cannot be claimed, send Cannot Claim.
        """
        if not _requested_pgn_is_ac(data):
            return  # Not asking for Address Claim; ignore

        if self._state in (CANState.CLAIMING, CANState.CLAIMED):
            logger.info("RX Request for AC → re-sending Address Claim")
            self._send_address_claim()
            if self._state == CANState.CLAIMING:
                # Restart the 250ms arbitration window per J1939-81
                self._restart_claim_timer()
        elif self._state == CANState.CANNOT_CLAIM:
            self._send_cannot_claim()

    def _handle_svc_response(self, data: bytes) -> None:
        """Process a J1939 service response (GET or SET ACK) from SSS2."""
        if len(data) < 5:
            return
        if data[0] != J1939_SVC_RESPONSE:
            return

        setting = data[1]
        value = struct.unpack_from("<h", data, 2)[0]  # int16 LE

        fut = self._svc_waiters.pop(setting, None)
        if fut and not fut.done():
            fut.set_result(value)

    # ------------------------------------------------------------------
    # RX loop
    # ------------------------------------------------------------------

    def _recv_one(self):
        """Blocking CAN recv with 0.5 s timeout — intended for run_in_executor."""
        bus = self._bus
        if bus is None:
            return None
        try:
            return bus.recv(timeout=0.5)
        except Exception:
            return None

    async def _rx_loop(self) -> None:
        """
        Async CAN receive loop.

        We deliberately avoid can.Notifier + can.AsyncBufferedReader because
        AsyncBufferedReader calls asyncio.get_event_loop() from the Notifier's
        background thread.  In Python 3.10+ on Linux that returns the *wrong*
        event loop (or raises RuntimeError), so messages are silently lost.

        Instead we drive a blocking bus.recv() call through
        loop.run_in_executor() so it runs in the thread pool but the result
        is delivered back to the correct asyncio event loop.
        """
        logger.info("CAN RX loop started")
        loop = asyncio.get_running_loop()

        while True:
            try:
                msg = await loop.run_in_executor(None, self._recv_one)
            except asyncio.CancelledError:
                logger.info("CAN RX loop cancelled")
                break
            except Exception as e:
                logger.error(f"CAN RX loop error: {e}", exc_info=True)
                break

            if msg is None:
                # recv() timed out — loop again (allows CancelledError to propagate)
                continue

            if not msg.is_extended_id:
                continue

            mid = msg.arbitration_id
            data = bytes(msg.data)

            if _is_addr_claim(mid):
                self._handle_addr_claim(mid, data)
            elif _is_request_pgn(mid):
                self._handle_request_for_ac(data)
            elif _is_svc_response(mid):
                self._handle_svc_response(data)
            else:
                sa = mid & 0xFF
                pf = (mid >> 16) & 0xFF
                if sa not in (GUI_SA, 0x80) and pf not in (0xEE, 0xEA):
                    frame = {
                        "channel": self._channel,
                        "ts": round(time.time(), 4),
                        "arb_id": f"{mid:08X}",
                        "pgn": _pgn_str(mid),
                        "sa": f"{sa:02X}",
                        "data": data.hex().upper(),
                    }
                    self._ecu_frames.append(frame)
                    if self._ecu_ws_callback:
                        asyncio.create_task(self._ecu_ws_callback(frame))

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _set_state(self, new_state: CANState) -> None:
        if self._state == new_state:
            return
        logger.info(f"CAN state: {self._state.value} → {new_state.value}")
        self._state = new_state
        status = self.status()
        for cb in list(self._state_callbacks):
            try:
                cb(status)
            except Exception as e:
                logger.error(f"State callback error: {e}", exc_info=True)
