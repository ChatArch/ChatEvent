"""Authentication primitives for ChatEvent."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .model import utc_now

UserRole = Literal["admin", "member"]

_TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_TOKEN_LENGTH = 32
_TOKEN_PREFIX = "arch_"
_TOKEN_HASH_CONTEXT = "chatevent-auth-v1:"
_PASSWORD_PREFIX = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 260_000


class UserRecord(BaseModel):
    """Stored user identity without exposing credential hashes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    username: str = Field(min_length=1)
    display_name: str | None = None
    role: UserRole = "member"
    enabled: bool = True
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("id", "username")
    @classmethod
    def strip_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


def generate_arch_token() -> str:
    """Generate a ChatArch-style bearer token shown once to the operator."""

    suffix = "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LENGTH))
    return f"{_TOKEN_PREFIX}{suffix}"


def token_digest(token: str) -> str:
    """Return a stable digest for token lookup without storing the token itself."""

    return hashlib.sha256(f"{_TOKEN_HASH_CONTEXT}{token}".encode("utf-8")).hexdigest()


def password_digest(password: str, *, salt: bytes | None = None) -> str:
    """Hash a human login password for storage."""

    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return f"{_PASSWORD_PREFIX}${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_digest: str | None) -> bool:
    """Verify a human login password against a stored digest."""

    if not stored_digest:
        return False
    try:
        prefix, iterations, salt_hex, digest_hex = stored_digest.split("$", 3)
        if prefix != _PASSWORD_PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)
