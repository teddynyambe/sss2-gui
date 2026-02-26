"""Tests for in-memory state service."""
import pytest
from fastapi.testclient import TestClient
from services.state_service import StateService


def test_get_state_returns_default():
    """GET /api/sss2/state returns a dict even when CAN is not connected."""
    from main import app
    client = TestClient(app)

    response = client.get("/api/sss2/state")
    assert response.status_code == 200
    state = response.json()
    assert isinstance(state, dict)
    assert "ignition" in state
    assert "potentiometers" in state


def test_state_service_in_memory():
    """StateService updates are in-memory only (no file persistence between instances)."""
    service = StateService()
    service.update_state({"ignition": True})
    state = service.get_state()
    assert state["ignition"] is True

    # A new instance does NOT see the changes (no file backing)
    service2 = StateService()
    state2 = service2.get_state()
    assert state2["ignition"] is False  # default


def test_state_service_deep_merge():
    """Partial updates are merged into the cached state."""
    service = StateService()
    service.update_state({"potentiometers": {"po1": {"wiper_position": 100}}})
    state = service.get_state()
    assert state["potentiometers"]["po1"]["wiper_position"] == 100


def test_state_service_clear():
    """clear() resets state to default."""
    service = StateService()
    service.update_state({"ignition": True})
    service.clear()
    state = service.get_state()
    assert state["ignition"] is False
