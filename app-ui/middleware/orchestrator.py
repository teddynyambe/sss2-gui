"""Orchestrator — coordinates CAN service, state service, and WebSocket broadcast."""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Set

from core.config import settings
from services.can_service import CANService, CANConnectionError, CANTimeoutError
from services.state_service import StateService

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Central coordinator:
    - Manages CANService and StateService lifecycle.
    - Routes hardware commands (ignition, pots) to CAN service.
    - Notifies WebSocket clients on CAN state changes.
    """

    def __init__(self) -> None:
        self.can_service: Optional[CANService] = None
        self.state_service: Optional[StateService] = None
        self._initialized = False
        self._connection_callbacks: Set[Callable] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        if self._initialized:
            return
        logger.info("Initializing orchestrator...")
        self.state_service = StateService()
        self.can_service = CANService()
        self.can_service.register_state_callback(self._on_can_state_changed)
        await self.can_service.start()
        self._initialized = True
        logger.info("Orchestrator initialized")

        # Auto-connect to CAN bus immediately (like firmware claiming address on boot)
        if settings.CAN_AUTO_CONNECT:
            try:
                await self.can_service.connect(
                    settings.CAN_INTERFACE,
                    settings.CAN_CHANNEL,
                    settings.CAN_BITRATE,
                )
                logger.info(
                    f"Auto-connected: {settings.CAN_INTERFACE}/{settings.CAN_CHANNEL} "
                    f"@ {settings.CAN_BITRATE} bps — address claiming started"
                )
            except Exception as e:
                logger.warning(
                    f"CAN auto-connect failed ({settings.CAN_CHANNEL}): {e} "
                    f"— manual connect available in UI"
                )

    async def shutdown(self) -> None:
        if not self._initialized:
            return
        logger.info("Shutting down orchestrator...")
        if self.can_service:
            await self.can_service.stop()
        self._initialized = False
        logger.info("Orchestrator shut down")

    # ------------------------------------------------------------------
    # Connection callbacks (for WebSocket broadcast)
    # ------------------------------------------------------------------

    def register_connection_callback(self, callback: Callable) -> None:
        self._connection_callbacks.add(callback)

    def unregister_connection_callback(self, callback: Callable) -> None:
        self._connection_callbacks.discard(callback)

    def _on_can_state_changed(self, status: Dict[str, Any]) -> None:
        for cb in list(self._connection_callbacks):
            try:
                cb(status)
            except Exception as e:
                logger.error(f"Connection callback error: {e}")

    # ------------------------------------------------------------------
    # Hardware control via CAN
    # ------------------------------------------------------------------

    async def engine_start(self, sss2_sa: int) -> bool:
        """SET setting 50 = 1 (ignition ON)."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")
        result = await self.can_service.set_setting(sss2_sa, 50, 1)
        if result and self.state_service:
            self.state_service.update_state({"ignition": True})
        return result

    async def engine_stop(self, sss2_sa: int) -> bool:
        """SET setting 50 = 0 (ignition OFF)."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")
        result = await self.can_service.set_setting(sss2_sa, 50, 0)
        if result and self.state_service:
            self.state_service.update_state({"ignition": False})
        return result

    async def set_pot(self, sss2_sa: int, port: int, value: int) -> bool:
        """SET potentiometer wiper (settings 1-16)."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")
        if not (1 <= port <= 16):
            raise ValueError(f"Pot port must be 1-16, got {port}")
        return await self.can_service.set_setting(sss2_sa, port, value)

    async def set_pot_power(self, sss2_sa: int, group_id: int, voltage_setting: str) -> bool:
        """SET power group voltage (settings 25-32). group_id 1-8."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")
        setting = 24 + group_id  # group 1 → setting 25, ..., group 8 → setting 32
        voltage_value = 0 if voltage_setting == "5V" else 1
        return await self.can_service.set_setting(sss2_sa, setting, voltage_value)

    async def set_pot_enabled(self, sss2_sa: int, port: int, enabled: bool) -> bool:
        """SET potentiometer terminal connection mode (settings 51-66)."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")
        setting = 50 + port  # pot 1 → setting 51, ..., pot 16 → setting 66
        value = 7 if enabled else 3
        return await self.can_service.set_setting(sss2_sa, setting, value)

    async def apply_state_changes(self, sss2_sa: int, changes: dict) -> None:
        """Apply a dict of state changes to hardware."""
        if not self.can_service:
            raise RuntimeError("Orchestrator not initialized")

        if "ignition" in changes:
            if changes["ignition"]:
                await self.engine_start(sss2_sa)
            else:
                await self.engine_stop(sss2_sa)

        if "potentiometer_power_groups" in changes:
            for group_key, group_data in changes["potentiometer_power_groups"].items():
                if "voltage_setting" in group_data:
                    group_id = int(group_key.replace("group_", ""))
                    await self.set_pot_power(sss2_sa, group_id, group_data["voltage_setting"])

        if "potentiometers" in changes:
            for pot_id, pot_data in changes["potentiometers"].items():
                port = int(pot_id.replace("po", ""))
                if "enabled" in pot_data:
                    await self.set_pot_enabled(sss2_sa, port, pot_data["enabled"])
                if "wiper_position" in pot_data:
                    await self.set_pot(sss2_sa, port, pot_data["wiper_position"])

    # ------------------------------------------------------------------
    # Convenience status
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self.can_service.is_connected() if self.can_service else False

    def can_status(self) -> Dict[str, Any]:
        if self.can_service:
            return self.can_service.status()
        return {
            "connected": False,
            "interface": "",
            "channel": "",
            "bitrate": 250000,
            "sa": 0x82,
            "address_claimed": False,
            "state": "disconnected",
        }
