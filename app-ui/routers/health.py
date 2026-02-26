"""Health check endpoint."""
import logging
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from core.config import settings
from middleware.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    connected: bool


def get_orchestrator() -> Orchestrator:
    """Dependency to get orchestrator."""
    from main import get_orchestrator_instance
    return get_orchestrator_instance()


@router.get("", response_model=HealthResponse)
async def health_check(
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """Health check endpoint."""
    logger.info(
        f"Health check requested fromtesting {request.client.host if request.client else 'unknown'}")

    is_connected = orchestrator.is_connected() if orchestrator else False
    response = HealthResponse(
        status="ok",
        version=settings.VERSION,
        connected=is_connected
    )

    logger.info(
        f"Health check response: {response.status}, connected={response.connected}")
    return response
