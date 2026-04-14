import hashlib
import hmac
import secrets

from fastapi import Cookie, HTTPException, status

import database


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, key_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return hmac.compare_digest(key.hex(), key_hex)


async def make_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    await database.create_session(token, user_id)
    return token


async def get_current_user(session_token: str = Cookie(default=None)):
    """FastAPI dependency — returns the session row or raises 401."""
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    row = await database.get_session(session_token)
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return row


def require_role(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles."""
    async def _dep(session_token: str = Cookie(default=None)):
        if not session_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        row = await database.get_session(session_token)
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if row["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Insufficient permissions")
        return row
    return _dep
