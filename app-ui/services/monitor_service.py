"""Receive-only CAN bus monitor for passive monitoring of additional buses."""
import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _pgn_str(mid: int) -> str:
    """Return the PGN as a 5-char hex string from a 29-bit J1939 arb ID."""
    pf = (mid >> 16) & 0xFF
    ps = (mid >> 8) & 0xFF
    dp = (mid >> 24) & 0x01
    if pf < 0xF0:
        return f"{(dp << 17) | (pf << 8):05X}"
    return f"{(dp << 17) | (pf << 8) | ps:05X}"


class MonitorService:
    """
    Lightweight receive-only manager for additional CAN buses.

    Opened buses never transmit any frames — they only receive.
    Frames are tagged with their source channel and delivered via ws_callback.
    """

    def __init__(self, ws_callback: Optional[Callable] = None) -> None:
        self._buses: dict = {}
        self._tasks: dict = {}
        self._ws_callback = ws_callback

    async def connect(self, channel: str, bitrate: int) -> dict:
        """Open a CAN bus for passive monitoring (receive-only)."""
        if channel in self._buses:
            return {"channel": channel, "status": "already_connected"}
        try:
            import can
            bus = can.Bus(
                interface="socketcan",
                channel=channel,
                bitrate=bitrate,
                receive_own_messages=False,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to open monitor bus {channel}: {e}") from e

        self._buses[channel] = bus
        self._tasks[channel] = asyncio.create_task(self._rx_loop(channel, bus))
        logger.info(f"Monitor bus connected: {channel} @ {bitrate}")
        return {"channel": channel, "status": "connected"}

    async def disconnect(self, channel: str) -> None:
        """Stop monitoring and close a CAN bus."""
        if task := self._tasks.pop(channel, None):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if bus := self._buses.pop(channel, None):
            try:
                bus.shutdown()
            except Exception:
                pass
        logger.info(f"Monitor bus disconnected: {channel}")

    async def _rx_loop(self, channel: str, bus) -> None:
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, lambda: bus.recv(timeout=0.5))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor RX error on {channel}: {e}")
                break
            if msg is None:
                continue
            if not msg.is_extended_id:
                continue
            mid = msg.arbitration_id
            sa = mid & 0xFF
            frame = {
                "channel": channel,
                "ts": round(time.time(), 4),
                "arb_id": f"{mid:08X}",
                "pgn": _pgn_str(mid),
                "sa": f"{sa:02X}",
                "data": msg.data.hex().upper(),
            }
            if self._ws_callback:
                asyncio.create_task(self._ws_callback(frame))

    def status(self) -> list:
        return [{"channel": c, "status": "connected"} for c in self._buses]

    async def shutdown(self) -> None:
        for ch in list(self._buses):
            await self.disconnect(ch)
