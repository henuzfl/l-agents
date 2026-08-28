from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.api.dependencies import get_auth_service, get_current_user
from app.auth import AuthenticatedUser, AuthenticationError, AuthService
from app.schemas import CurrentUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, service: AuthService, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=service.refresh_token_seconds,
        httponly=True,
        secure=service.secure_cookie,
        samesite="lax",
        path="/",
    )


def _token_response(service: AuthService, access_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        expires_in=service.access_token_seconds,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        access, refresh = await service.login(request.username, request.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_refresh_cookie(response, service, refresh)
    return _token_response(service, access)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="缺少刷新凭据。")
    try:
        access, next_refresh = await service.refresh(refresh_token)
    except AuthenticationError as exc:
        response.delete_cookie(REFRESH_COOKIE, path="/")
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_refresh_cookie(response, service, next_refresh)
    return _token_response(service, access)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    await service.logout(refresh_token)
    response.delete_cookie(REFRESH_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=CurrentUser)
async def me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> CurrentUser:
    return CurrentUser(id=str(user.id), username=user.username)
