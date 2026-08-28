from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.exception_handlers import register_exception_handlers
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.web import router as web_router
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    container = Container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_application: FastAPI):  # type: ignore[no-untyped-def]
        await container.startup()
        try:
            yield
        finally:
            await container.shutdown()

    application = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    application.state.container = container
    application.include_router(health_router)
    application.include_router(chat_router)
    application.include_router(auth_router)
    application.include_router(knowledge_router)
    application.include_router(web_router)
    register_exception_handlers(application)
    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    return application


app = create_app()
