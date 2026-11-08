"""Password hashing with the standard-library scrypt implementation (no extra dependency)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

_N, _R, _P = 2**15, 8, 1
_MAXMEM = 128 * 1024 * 1024
_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=_KEY_LENGTH
    )
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-work check: an unknown user or malformed hash still pays one scrypt."""
    try:
        if encoded is None:
            raise ValueError
        scheme, n, r, p, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            raise ValueError
        salt_bytes = base64.b64decode(salt, validate=True)
        expected_bytes = base64.b64decode(expected, validate=True)
        n_value, r_value, p_value = int(n), int(r), int(p)
        if (n_value, r_value, p_value) != (_N, _R, _P):
            raise ValueError
        if len(salt_bytes) != 16 or len(expected_bytes) != _KEY_LENGTH:
            raise ValueError
    except (ValueError, binascii.Error):
        hashlib.scrypt(
            password.encode("utf-8"), salt=b"\0" * 16, n=_N, r=_R, p=_P,
            maxmem=_MAXMEM, dklen=_KEY_LENGTH,
        )
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=salt_bytes, n=_N, r=_R, p=_P,
        maxmem=_MAXMEM, dklen=_KEY_LENGTH,
    )
    return hmac.compare_digest(candidate, expected_bytes)


def password_policy_error(password: str, username: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return "PASSWORD_TOO_SHORT"
    if len(password) > MAX_PASSWORD_LENGTH:
        return "PASSWORD_TOO_LONG"
    if password.casefold() == username.casefold():
        return "PASSWORD_EQUALS_USERNAME"
    return None


def generate_password() -> str:
    return secrets.token_urlsafe(18)
