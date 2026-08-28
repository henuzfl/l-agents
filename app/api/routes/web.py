from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import AuthenticationError

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path("app/templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    if not await _has_session(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="chat.html")


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge(request: Request) -> Response:
    if not await _has_session(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="knowledge.html")


async def _has_session(request: Request) -> bool:
    token = request.cookies.get("refresh_token")
    if not token:
        return False
    try:
        await request.app.state.container.auth_service.validate_refresh(token)
    except AuthenticationError:
        return False
    return True
