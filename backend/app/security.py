import hashlib
import hmac
import os
import secrets
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db

bearer = HTTPBearer(auto_error=False)


def _secret():
    return os.environ["JWT_SECRET"]


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(test, h)


def make_token(uid: int) -> str:
    return jwt.encode({"sub": str(uid), "exp": int(time.time()) + 7 * 86400}, _secret(), "HS256")


def optional_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        return None
    try:
        uid = int(jwt.decode(creds.credentials, _secret(), algorithms=["HS256"])["sub"])
    except Exception:
        return None
    return db.one(
        "SELECT id, username, email, display_name, affiliation, field, bio, orcid, verified, reputation "
        "FROM users WHERE id=:i", i=uid)


def current_user(u=Depends(optional_user)):
    if not u:
        raise HTTPException(401, "Login required")
    return u
