"""관리자 로그인용 토큰 생성·검증(표준 라이브러리만 사용)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Final

_MAX_SKEW_SEC: Final[int] = 120


def create_admin_token(secret: str, ttl_seconds: int = 8 * 3600) -> str:
    """만료 시각이 포함된 Bearer 토큰 문자열을 만듭니다."""
    if not secret:
        raise ValueError("ADMIN_JWT_SECRET 또는 ADMIN_PASSWORD가 필요합니다.")
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"admin:{exp}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_admin_token(token: str, secret: str) -> bool:
    """Bearer 토큰이 유효하고 만료되지 않았는지 검사합니다."""
    if not token or not secret:
        return False
    padded = token + "=" * ((4 - len(token) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    parts = raw.split(":", 2)
    if len(parts) != 3 or parts[0] != "admin":
        return False
    try:
        exp = int(parts[1])
    except ValueError:
        return False
    sig = parts[2]
    payload = f"admin:{exp}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not secrets.compare_digest(sig, expected):
        return False
    now = int(time.time())
    if exp < now - _MAX_SKEW_SEC:
        return False
    return True


def constant_time_equal_password(expected: str, given: str) -> bool:
    """관리자 비밀번호 비교(길이가 다르면 즉시 False)."""
    e = expected.encode("utf-8")
    g = given.encode("utf-8")
    if len(e) != len(g):
        return False
    return secrets.compare_digest(e, g)
