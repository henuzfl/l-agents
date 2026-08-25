from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path("app/templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="chat.html")


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="knowledge.html")
