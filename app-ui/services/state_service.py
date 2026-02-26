"""State service — in-memory device state cache (no file persistence)."""
from datetime import datetime
from typing import Any


class StateService:
    """In-memory cache of SSS2 device state.

    State is populated via GET_ALL_SETTINGS over J1939 CAN.
    No JSON file is written; the SSS2 is always the source of truth.
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] | None = None

    def get_state(self) -> dict[str, Any]:
        """Return current cached state, or default if not yet populated."""
        if self._state is None:
            return self._default_state()
        return self._state

    def set_state(self, state: dict[str, Any]) -> None:
        """Replace entire cached state (called after GET_ALL_SETTINGS)."""
        state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self._state = state

    def update_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge partial updates into the cached state."""
        state = self.get_state()
        self._deep_merge(state, updates)
        state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self._state = state
        return state

    def clear(self) -> None:
        """Clear cached state (call on disconnect)."""
        self._state = None

    def _deep_merge(self, base: dict[str, Any], updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _default_state(self) -> dict[str, Any]:
        return {
            "sss2_sa": None,
            "last_updated": None,
            "ignition": False,
            "potentiometers": {},
            "potentiometer_power_groups": {},
            "vouts": {},
            "pwms": {},
            "can": {},
            "j1708": {},
        }
