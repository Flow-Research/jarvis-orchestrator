"""Operator request signing for the Jarvis workstream API."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Protocol  # noqa: UP035

from fastapi import Request

OPERATOR_ID_HEADER = "x-jarvis-operator"
TIMESTAMP_HEADER = "x-jarvis-timestamp"
NONCE_HEADER = "x-jarvis-nonce"
SIGNATURE_HEADER = "x-jarvis-signature"
SIGNATURE_SCHEME = "JARVIS-OPERATOR-HMAC-SHA256"


class OperatorAuthError(Exception):
    """Raised when an operator request is not authenticated."""


@dataclass(frozen=True)
class OperatorIdentity:
    """Authenticated operator identity."""

    operator_id: str


class NonceStore(Protocol):
    """Replay-prevention store for signed operator requests."""

    def use_nonce(self, operator_id: str, nonce: str, expires_at: int) -> bool:
        """Return True if the nonce has not been used and is now reserved."""


@dataclass
class InMemoryNonceStore:
    """Single-process nonce store for local and single-node deployments."""

    _nonces: dict[tuple[str, str], int] = field(default_factory=dict)

    def use_nonce(self, operator_id: str, nonce: str, expires_at: int) -> bool:
        now = int(time.time())
        self._nonces = {
            key: expiry for key, expiry in self._nonces.items() if expiry >= now
        }
        key = (operator_id, nonce)
        if key in self._nonces:
            return False
        self._nonces[key] = expires_at
        return True


@dataclass(frozen=True)
class HMACOperatorAuthenticator:
    """Authenticate workstream API calls with per-operator HMAC secrets."""

    secrets: dict[str, str]
    max_clock_skew_seconds: int = 300
    nonce_store: NonceStore = field(default_factory=InMemoryNonceStore)

    async def authenticate(self, request: Request) -> OperatorIdentity:
        operator_id = _required_header(request, OPERATOR_ID_HEADER)
        timestamp = _parse_timestamp(_required_header(request, TIMESTAMP_HEADER))
        nonce = _required_header(request, NONCE_HEADER)
        provided_signature = _normalize_signature(
            _required_header(request, SIGNATURE_HEADER)
        )

        now = int(time.time())
        if abs(now - timestamp) > self.max_clock_skew_seconds:
            raise OperatorAuthError("operator signature timestamp outside allowed skew")

        secret = self.secrets.get(operator_id)
        if not secret:
            raise OperatorAuthError("unknown operator")

        body = await request.body()
        expected = sign_operator_request(
            secret=secret,
            method=request.method,
            path_with_query=_path_with_query(request),
            body=body,
            timestamp=timestamp,
            nonce=nonce,
        )
        if not hmac.compare_digest(provided_signature, expected):
            raise OperatorAuthError("operator signature mismatch")

        expires_at = now + self.max_clock_skew_seconds
        if not self.nonce_store.use_nonce(operator_id, nonce, expires_at):
            raise OperatorAuthError("operator signature nonce replayed")

        return OperatorIdentity(operator_id=operator_id)


def sign_operator_request(
    *,
    secret: str,
    method: str,
    path_with_query: str,
    body: bytes,
    timestamp: int,
    nonce: str,
) -> str:
    """Return the hex HMAC signature for a workstream API request."""
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            SIGNATURE_SCHEME,
            method.upper(),
            path_with_query,
            body_hash,
            str(timestamp),
            nonce,
        )
    )
    return hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _required_header(request: Request, name: str) -> str:
    value = request.headers.get(name)
    if not value:
        raise OperatorAuthError(f"missing {name} header")
    return value.strip()


def _parse_timestamp(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise OperatorAuthError("invalid operator signature timestamp") from exc


def _normalize_signature(value: str) -> str:
    prefix = "sha256="
    return value.removeprefix(prefix).strip().lower()


def _path_with_query(request: Request) -> str:
    query = request.url.query
    if query:
        return f"{request.url.path}?{query}"
    return request.url.path
