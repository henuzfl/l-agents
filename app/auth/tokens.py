import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt

from app.auth.models import AuthenticationError, UserAccount


class TokenCodec:
    ALGORITHM = "HS256"

    def __init__(self, secret: str, issuer: str, audience: str) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def encode(
        self,
        *,
        user: UserAccount,
        token_type: str,
        jti: UUID,
        expires: datetime,
        family_id: UUID | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "sub": str(user.id),
            "username": user.username,
            "type": token_type,
            "jti": str(jti),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": datetime.now(UTC),
            "exp": expires,
        }
        if family_id is not None:
            payload["family"] = str(family_id)
        return jwt.encode(payload, self._secret, algorithm=self.ALGORITHM)

    def decode(self, token: str, expected_type: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self.ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("认证凭据无效或已过期。") from exc
        if payload.get("type") != expected_type:
            raise AuthenticationError("认证凭据类型无效。")
        return payload

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
