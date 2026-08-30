from typing import Annotated, Protocol

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import AuthenticatedUser, AuthenticationError


class CurrentUserService(Protocol):
    async def current_user(self, access_token: str) -> AuthenticatedUser: ...


bearer_scheme = HTTPBearer(auto_error=False)


async def authenticate_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: CurrentUserService,
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="需要登录。")
    try:
        return await service.current_user(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
