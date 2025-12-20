import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from .database import get_session
from .models import User


ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")
SESSION_SECRET = os.getenv("SESSION_SECRET")
SESSION_COOKIE_NAME = "bv_session"


def _require_session_secret() -> str:
    if not SESSION_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SESSION_SECRET não configurado",
        )
    return SESSION_SECRET


def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000)
    return "pbkdf2_sha256$150000$" + base64.urlsafe_b64encode(salt).decode("utf-8") + "$" + base64.urlsafe_b64encode(dk).decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("utf-8"))
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def sign_session(user_id: int) -> str:
    secret = _require_session_secret().encode("utf-8")
    payload = f"{user_id}:{int(datetime.now(tz=timezone.utc).timestamp())}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload).decode("utf-8") + "." + base64.urlsafe_b64encode(sig).decode("utf-8")


def unsign_session(token: str) -> int | None:
    try:
        secret = _require_session_secret().encode("utf-8")
        payload_b64, sig_b64 = token.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        sig = base64.urlsafe_b64decode(sig_b64.encode("utf-8"))
        expected = hmac.new(secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        user_id_s, _ts = payload.decode("utf-8").split(":", 1)
        return int(user_id_s)
    except Exception:
        return None


def bootstrap_admin_user() -> None:
    if not ADMIN_USER or not ADMIN_PASS:
        return
    with get_session() as db:
        existing_admin = db.execute(select(User).where(User.role == "admin").limit(1)).scalar_one_or_none()
        if existing_admin is not None:
            return
        u = User(username=ADMIN_USER, password_hash=hash_password(ADMIN_PASS), role="admin", status="ativo")
        db.add(u)
        db.commit()


def get_current_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = unsign_session(token)
    if not user_id:
        return None
    with get_session() as db:
        u = db.get(User, user_id)
        if not u or u.status != "ativo":
            return None
        return u


def require_role(*roles: str):
    def _dep(request: Request) -> User:
        u = get_current_user(request)
        if not u:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login necessário")
        if roles and u.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        return u

    return _dep
