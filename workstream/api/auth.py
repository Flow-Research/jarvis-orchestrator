"""Garden-backed authentication for the Flow Workstream API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
from fastapi import Request

GARDEN_USER_ID_HEADER = "x-garden-user-id"
GARDEN_WORKSPACE_ID_HEADER = "x-garden-workspace-id"
GARDEN_SESSION_TOKEN_HEADER = "x-garden-session-token"


class OperatorAuthError(Exception):
    """Raised when a Workstream request is not authenticated by Garden."""


@dataclass(frozen=True)
class OperatorIdentity:
    """Authenticated personal-operator identity derived from Garden."""

    operator_id: str
    garden_user_id: str
    garden_workspace_id: str | None = None
    email: str | None = None
    name: str | None = None


GardenPostJSON = Callable[
    [str, dict[str, str], dict[str, object], float],
    Awaitable[dict[str, Any]],
]


@dataclass(frozen=True)
class GardenOperatorAuthenticator:
    """Authenticate Workstream calls by verifying Garden identity server-side."""

    service_auth_token: str
    verify_url: str
    request_timeout_seconds: float = 5.0
    require_active_session: bool = False
    post_json: GardenPostJSON | None = None

    async def authenticate(self, request: Request) -> OperatorIdentity:
        payload = self._verification_payload(request)
        response = await self._post_verify(self.verify_url, payload)
        if response.get("ok") is not True:
            raise OperatorAuthError("garden auth verification failed")

        user = response.get("user")
        if not isinstance(user, dict):
            raise OperatorAuthError("garden auth verification missing user")
        garden_user_id = str(user.get("id") or "").strip()
        if not garden_user_id:
            raise OperatorAuthError("garden auth verification missing user id")

        requested_user_id = request.headers.get(GARDEN_USER_ID_HEADER)
        if requested_user_id and requested_user_id.strip() != garden_user_id:
            raise OperatorAuthError("garden auth user mismatch")

        personal_workspace = response.get("personal_workspace")
        verified_workspace_id = None
        if isinstance(personal_workspace, dict):
            verified_workspace_id = str(personal_workspace.get("id") or "").strip() or None
        requested_workspace_id = request.headers.get(GARDEN_WORKSPACE_ID_HEADER)
        if (
            requested_workspace_id
            and verified_workspace_id
            and requested_workspace_id.strip() != verified_workspace_id
        ):
            raise OperatorAuthError("garden auth workspace mismatch")

        return OperatorIdentity(
            operator_id=garden_user_id,
            garden_user_id=garden_user_id,
            garden_workspace_id=verified_workspace_id or _optional_header(
                request, GARDEN_WORKSPACE_ID_HEADER
            ),
            email=_optional_user_text(user, "email"),
            name=_optional_user_text(user, "name"),
        )

    def _verification_payload(self, request: Request) -> dict[str, object]:
        session_token = _optional_header(request, GARDEN_SESSION_TOKEN_HEADER)
        if session_token:
            return {
                "session_token": session_token,
                "require_active_session": True,
            }

        user_id = _optional_header(request, GARDEN_USER_ID_HEADER)
        if not user_id:
            raise OperatorAuthError(
                f"missing {GARDEN_USER_ID_HEADER} header or {GARDEN_SESSION_TOKEN_HEADER} header"
            )
        return {
            "user_id": user_id,
            "require_active_session": self.require_active_session,
        }

    async def _post_verify(self, verify_url: str, payload: dict[str, object]) -> dict[str, Any]:
        headers = {
            "authorization": f"Bearer {self.service_auth_token}",
            "content-type": "application/json",
        }
        if self.post_json is not None:
            return await self.post_json(
                verify_url,
                headers,
                payload,
                self.request_timeout_seconds,
            )

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(verify_url, json=payload, headers=headers) as response:
                    if response.status >= 400:
                        raise OperatorAuthError(
                            f"garden auth verification returned HTTP {response.status}"
                        )
                    data = await response.json()
        except OperatorAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise OperatorAuthError("garden auth verification request failed") from exc

        if not isinstance(data, dict):
            raise OperatorAuthError("garden auth verification returned invalid JSON")
        return data


def _optional_header(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_user_text(user: dict[str, Any], key: str) -> str | None:
    value = user.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
