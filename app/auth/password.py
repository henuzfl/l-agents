from pwdlib import PasswordHash


class PasswordService:
    def __init__(self) -> None:
        self._passwords = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._passwords.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._passwords.verify(password, password_hash)
