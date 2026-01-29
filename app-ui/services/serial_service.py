"""Async serial service for SSS2 communication."""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, Callable, Dict
import serial_asyncio
import serial.tools.list_ports

from core.config import settings

logger = logging.getLogger(__name__)


def _detect_sss2_port() -> Optional[str]:
    """
    Auto-detect SSS2 serial port.
    Prefers tty.usbmodem* on macOS, ttyACM* on Linux. Returns first match, or None.
    """
    candidates = []
    for p in serial.tools.list_ports.comports():
        dev = (p.device or "").lower()
        if "usbmodem" in dev or "ttyacm" in dev:
            candidates.append(p.device)
    if sys.platform == "darwin":
        # Prefer tty over cu on Mac; sort for stable order
        candidates.sort(key=lambda x: (("cu." in x.lower(), x)))
    else:
        candidates.sort()
    return candidates[0] if candidates else None


class SerialConnectionError(Exception):
    """Raised when serial connection is lost or unavailable."""
    pass


class CommandTimeoutError(Exception):
    """Raised when command response times out."""
    pass


class SerialService:
    """Async serial service for SSS2 communication."""

    def __init__(self):
        """Initialize serial service."""
        self._config_port = (settings.SSS2_SERIAL_PORT or "").strip()
        self.port = self._config_port or "auto-detect"
        self.baudrate = settings.SSS2_BAUDRATE
        self.connected = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._command_queue: Optional[asyncio.Queue] = None
        self._command_response_map: Dict[str, asyncio.Future] = {}
        self._command_counter = 0
        self._read_task: Optional[asyncio.Task] = None
        self._write_task: Optional[asyncio.Task] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 5.0  # seconds
        self._command_timeout = 2.0  # seconds
        self._on_connection_changed: Optional[Callable[[bool, str, Optional[str]], None]] = None
        
    def set_connection_callback(self, callback: Callable[[bool, str, Optional[str]], None]) -> None:
        """Set callback for connection status changes.

        Args:
            callback: Function called with (connected: bool, port: str, message: Optional[str])
        """
        self._on_connection_changed = callback

    def _resolve_port(self) -> Optional[str]:
        """Resolve serial port: use configured port if set and present, else auto-detect."""
        if self._config_port:
            p = Path(self._config_port)
            if p.exists():
                return self._config_port
            return None
        return _detect_sss2_port()

    async def start(self) -> None:
        """Start serial service (connect and start background tasks)."""
        if self._connection_task is None:
            self._command_queue = asyncio.Queue()
            self._connection_task = asyncio.create_task(self._connection_loop())
            mode = f"port {self._config_port}" if self._config_port else "auto-detect"
            logger.info(f"Serial service starting ({mode})")
    
    async def stop(self) -> None:
        """Stop serial service (disconnect and clean up tasks)."""
        self.connected = False
        
        # Cancel all tasks
        tasks = [
            self._heartbeat_task,
            self._read_task,
            self._write_task,
            self._connection_task
        ]
        
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close serial connection
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing serial writer: {e}")
            self._writer = None
        
        self._reader = None
        self._read_task = None
        self._write_task = None
        self._connection_task = None
        self._heartbeat_task = None
        
        # Cancel all pending command futures
        for future in self._command_response_map.values():
            if not future.done():
                future.cancel()
        self._command_response_map.clear()
        
        logger.info("Serial service stopped")
    
    async def send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a command to SSS2 and wait for response.
        
        Args:
            command: Command string to send (e.g., "50,1")
            timeout: Optional timeout in seconds (default: self._command_timeout)
            
        Returns:
            Response string from SSS2
            
        Raises:
            SerialConnectionError: If not connected
            CommandTimeoutError: If no response received within timeout
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        if timeout is None:
            timeout = self._command_timeout
        
        # Create future for response
        command_id = f"{command}_{self._command_counter}"
        self._command_counter += 1
        future = asyncio.Future()
        self._command_response_map[command_id] = future
        
        try:
            # Queue command
            if self._command_queue:
                await self._command_queue.put((command, command_id))
            else:
                raise SerialConnectionError("Command queue not initialized")
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
                return response
            except asyncio.TimeoutError:
                self._command_response_map.pop(command_id, None)
                raise CommandTimeoutError(f"Command '{command}' timed out after {timeout}s")
        except Exception as e:
            self._command_response_map.pop(command_id, None)
            raise
    
    async def _connection_loop(self) -> None:
        """Background task for managing serial connection."""
        while True:
            try:
                # Resolve port (configured or auto-detected)
                resolved = self._resolve_port()
                if not resolved:
                    if self.connected:
                        logger.warning("SSS2 device lost or not found")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, "Device not found")
                    self.port = "auto-detect" if not self._config_port else self._config_port
                    await asyncio.sleep(self._heartbeat_interval)
                    continue
                if not Path(resolved).exists():
                    if self.connected:
                        logger.warning(f"Serial port {resolved} no longer exists")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, "Device not found")
                    await asyncio.sleep(self._heartbeat_interval)
                    continue
                self.port = resolved

                # Skip if already connected and tasks are running
                if self.connected and self._reader and self._writer and self._read_task and not self._read_task.done():
                    await asyncio.sleep(1.0)  # Check connection status periodically
                    continue

                # Try to connect (only if not already connected)
                if not self.connected:
                    logger.info(f"Connecting to {self.port} at {self.baudrate} baud...")
                    try:
                        self._reader, self._writer = await serial_asyncio.open_serial_connection(
                            url=self.port,
                            baudrate=self.baudrate
                        )

                        self.connected = True
                        logger.info(f"Connected to {self.port}")

                        if self._on_connection_changed:
                            self._on_connection_changed(True, self.port, "Connected")
                        
                        # Start read and write tasks
                        if self._read_task is None or self._read_task.done():
                            self._read_task = asyncio.create_task(self._read_loop())
                        
                        if self._write_task is None or self._write_task.done():
                            self._write_task = asyncio.create_task(self._write_loop())
                        
                        # Start heartbeat task
                        if self._heartbeat_task is None or self._heartbeat_task.done():
                            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    
                    except serial_asyncio.serial.SerialException as e:
                        logger.error(f"Serial connection error: {e}")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, str(e))
                        
                        # Clean up failed connection
                        if self._writer:
                            try:
                                self._writer.close()
                                await self._writer.wait_closed()
                            except Exception:
                                pass
                            self._writer = None
                        self._reader = None
                        
                        # Cancel tasks
                        for task in [self._read_task, self._write_task, self._heartbeat_task]:
                            if task:
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass
                        
                        self._read_task = None
                        self._write_task = None
                        self._heartbeat_task = None
                        
                        await asyncio.sleep(5)  # Retry after 5 seconds
                        continue
                
                # Wait for connection to fail (read/write tasks will handle errors)
                # Only wait if tasks are running and not done
                if (self._read_task and not self._read_task.done() and
                    self._write_task and not self._write_task.done() and
                    self._heartbeat_task and not self._heartbeat_task.done()):
                    results = await asyncio.gather(
                        self._read_task,
                        self._write_task,
                        self._heartbeat_task,
                        return_exceptions=True
                    )
                    
                    # If any task failed, mark as disconnected and clean up
                    if any(isinstance(r, Exception) for r in results if r is not None):
                        logger.warning("Connection tasks failed, cleaning up...")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, "Connection lost")
                        
                        # Clean up
                        if self._writer:
                            try:
                                self._writer.close()
                                await self._writer.wait_closed()
                            except Exception:
                                pass
                            self._writer = None
                        self._reader = None
                        
                        self._read_task = None
                        self._write_task = None
                        self._heartbeat_task = None
                        
                        await asyncio.sleep(5)  # Retry after 5 seconds
                else:
                    # Tasks not running or done, wait a bit before checking again
                    await asyncio.sleep(1.0)
                    
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Connection loop error: {e}", exc_info=True)
                self.connected = False
                if self._on_connection_changed:
                    self._on_connection_changed(False, self.port, str(e))
                await asyncio.sleep(5)  # Retry after 5 seconds
    
    async def _write_loop(self) -> None:
        """Background task for writing commands to serial port."""
        if self._command_queue is None or self._writer is None:
            return
        
        while self.connected:
            try:
                command, command_id = await asyncio.wait_for(
                    self._command_queue.get(),
                    timeout=1.0
                )
                
                if not self.connected or self._writer is None:
                    break
                
                # Write command with newline
                command_bytes = f"{command}\r\n".encode('ascii')
                self._writer.write(command_bytes)
                await self._writer.drain()
                
                logger.info(f"Sending command: {command}")
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except serial_asyncio.serial.SerialException as e:
                # Device disconnected - handle gracefully
                error_msg = str(e)
                if "Device not configured" in error_msg or "device not configured" in error_msg.lower():
                    logger.info("Device disconnected")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, "Device disconnected")
                else:
                    logger.warning(f"Serial write error: {error_msg}")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, f"Write error: {error_msg}")
                break
            except Exception as e:
                logger.warning(f"Write error: {e}")
                # Mark connection as failed
                self.connected = False
                if self._on_connection_changed:
                    self._on_connection_changed(False, self.port, f"Write error: {e}")
                break
    
    async def _read_loop(self) -> None:
        """Background task for reading responses from serial port."""
        if self._reader is None:
            return
        
        while self.connected:
            try:
                if self._reader is None:
                    break
                
                # Read line with timeout
                try:
                    line = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=1.0
                    )
                    
                    if not line:
                        continue
                    
                    # Decode and strip
                    response = line.decode('ascii', errors='ignore').strip()
                    
                    if not response:
                        continue
                    
                    logger.info(f"Received response: {response}")
                    
                    # Parse and match response to pending command
                    self._parse_response(response)
                    
                except asyncio.TimeoutError:
                    # Timeout is OK, continue reading
                    continue
                except serial_asyncio.serial.SerialException as e:
                    # Device disconnected during read - handle gracefully
                    error_msg = str(e)
                    if "Device not configured" in error_msg or "device not configured" in error_msg.lower():
                        logger.info("Device disconnected")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, "Device disconnected")
                    else:
                        logger.warning(f"Serial read error: {error_msg}")
                        self.connected = False
                        if self._on_connection_changed:
                            self._on_connection_changed(False, self.port, f"Read error: {error_msg}")
                    break
                    
            except asyncio.CancelledError:
                break
            except serial_asyncio.serial.SerialException as e:
                # Device disconnected - handle gracefully
                error_msg = str(e)
                if "Device not configured" in error_msg or "device not configured" in error_msg.lower():
                    logger.info("Device disconnected")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, "Device disconnected")
                else:
                    logger.warning(f"Serial read error: {error_msg}")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, f"Read error: {error_msg}")
                break
            except Exception as e:
                logger.warning(f"Read error: {e}")
                # Mark connection as failed
                self.connected = False
                if self._on_connection_changed:
                    self._on_connection_changed(False, self.port, f"Read error: {e}")
                break
    
    def _parse_response(self, response: str) -> None:
        """Parse response and match to pending command.
        
        Args:
            response: Response string from SSS2
        """
        # Try to match response to pending commands
        # Strategy: Match any pending command, use first one
        # In practice, responses might be echo, "OK", "ACK", or error messages
        
        matched = False
        for command_id, future in list(self._command_response_map.items()):
            if not future.done():
                # Accept response for this command
                # For now, accept any response as confirmation
                future.set_result(response)
                self._command_response_map.pop(command_id, None)
                matched = True
                break
        
        if not matched:
            # No pending command, log as unexpected
            logger.debug(f"Unexpected response (no pending command): {response}")
    
    async def _heartbeat_loop(self) -> None:
        """Background task for monitoring connection health."""
        while self.connected:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                if not self.connected:
                    break
                
                # Check device presence
                port_path = Path(self.port)
                if not port_path.exists():
                    logger.warning(f"Heartbeat: Port {self.port} no longer exists")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, "Device disconnected")
                    break
                
                # Check if writer is still valid
                if self._writer is None or self._writer.is_closing():
                    logger.warning("Heartbeat: Writer is closed")
                    self.connected = False
                    if self._on_connection_changed:
                        self._on_connection_changed(False, self.port, "Connection lost")
                    break
                
                # Connection is healthy
                logger.debug(f"Heartbeat: Connection healthy on {self.port}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)
                self.connected = False
                if self._on_connection_changed:
                    self._on_connection_changed(False, self.port, f"Heartbeat error: {e}")
                break
    
    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        return self.connected
    
    async def engine_start(self) -> str:
        """Send engine start command (ignition ON) and wait for confirmation.
        
        Returns:
            Confirmation response from SSS2
            
        Raises:
            SerialConnectionError: If not connected
            CommandTimeoutError: If no response received
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        return await self.send_command("50,1")
    
    async def engine_stop(self) -> str:
        """Send engine stop command (ignition OFF) and wait for confirmation.
        
        Returns:
            Confirmation response from SSS2
            
        Raises:
            SerialConnectionError: If not connected
            CommandTimeoutError: If no response received
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        return await self.send_command("50,0")
    
    async def set_pot(self, port: int, value: int, wait_for_response: bool = True) -> Optional[str]:
        """Set potentiometer wiper position.
        
        Args:
            port: Potentiometer port (1-16)
            value: Wiper position (0-255)
            wait_for_response: If True, wait for confirmation. If False, fire-and-forget.
            
        Returns:
            Confirmation response from SSS2, or None if wait_for_response is False
            
        Raises:
            SerialConnectionError: If not connected
            CommandTimeoutError: If wait_for_response is True and no response received
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        command = f"{port},{value}"
        
        if wait_for_response:
            return await self.send_command(command)
        else:
            # Fire-and-forget: just queue the command without waiting
            if self._command_queue:
                await self._command_queue.put((command, None))
                logger.info(f"Sent potentiometer command (fire-and-forget): {command}")
                return None
            else:
                raise SerialConnectionError("Command queue not initialized")
    
    async def set_pot_power(self, group_command: int, voltage: int, wait_for_response: bool = False) -> Optional[str]:
        """Set potentiometer power group voltage setting.
        
        Args:
            group_command: Power group command number (25-32)
            voltage: 0 for +5V, 1 for +12V
            wait_for_response: If True, wait for confirmation. If False, fire-and-forget.
            
        Returns:
            Confirmation response from SSS2, or None if wait_for_response is False
            
        Raises:
            SerialConnectionError: If not connected
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        command = f"{group_command},{voltage}"
        
        if wait_for_response:
            return await self.send_command(command)
        else:
            # Fire-and-forget: just queue the command without waiting
            if self._command_queue:
                await self._command_queue.put((command, None))
                logger.info(f"Sent potentiometer power command (fire-and-forget): {command}")
                return None
            else:
                raise SerialConnectionError("Command queue not initialized")
    
    async def set_pot_enabled(self, port: int, enabled: bool, wait_for_response: bool = False) -> Optional[str]:
        """Set potentiometer enabled/disabled state.
        
        Args:
            port: Potentiometer port (1-16)
            enabled: True to enable (on), False to disable (off)
            wait_for_response: If True, wait for confirmation. If False, fire-and-forget.
            
        Returns:
            Confirmation response from SSS2, or None if wait_for_response is False
            
        Raises:
            SerialConnectionError: If not connected
        """
        if not self.connected:
            raise SerialConnectionError(f"Not connected to {self.port}")
        
        # Calculate command port: 51 for pot 1, 52 for pot 2, etc.
        command_port = 50 + port
        value = 7 if enabled else 3  # 7 = on, 3 = off
        command = f"{command_port},{value}"
        
        if wait_for_response:
            return await self.send_command(command)
        else:
            # Fire-and-forget: just queue the command without waiting
            if self._command_queue:
                await self._command_queue.put((command, None))
                logger.info(f"Sent potentiometer enable command (fire-and-forget): {command}")
                return None
            else:
                raise SerialConnectionError("Command queue not initialized")
