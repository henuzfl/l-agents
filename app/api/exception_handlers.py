from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AgentApplicationError


async def agent_application_error_handler(
    _request: Request,
    exc: AgentApplicationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"type": exc.__class__.__name__, "message": str(exc)}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AgentApplicationError, agent_application_error_handler)
