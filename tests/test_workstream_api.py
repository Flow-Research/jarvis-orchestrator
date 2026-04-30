import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from workstream.api import create_workstream_app
from workstream.api.auth import GardenOperatorAuthenticator
from workstream.api.runtime import create_default_app, runtime_configuration
from workstream.api.settings import load_workstream_api_settings
from workstream.models import (
    OperatorStats,
    OperatorSubmissionEnvelope,
    OperatorSubmissionReceipt,
    WorkstreamTask,
)
from workstream.stats import InMemoryOperatorStats
from workstream.store import InMemoryWorkstream


class FakeIntake:
    def __init__(self):
        self.submitted: list[OperatorSubmissionEnvelope] = []

    def submit(self, envelope: OperatorSubmissionEnvelope) -> OperatorSubmissionReceipt:
        self.submitted.append(envelope)
        return OperatorSubmissionReceipt(
            submission_id=envelope.submission_id,
            task_id=envelope.task_id,
            operator_id=envelope.operator_id,
            accepted_count=len(envelope.records),
            rejected_count=0,
            status="accepted",
        )


def _client() -> tuple[TestClient, InMemoryWorkstream, InMemoryOperatorStats]:
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    app = create_workstream_app(workstream=workstream, intake=FakeIntake(), stats=stats)
    return TestClient(app), workstream, stats


def _client_with_intake() -> tuple[
    TestClient,
    InMemoryWorkstream,
    InMemoryOperatorStats,
    FakeIntake,
]:
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    intake = FakeIntake()
    app = create_workstream_app(workstream=workstream, intake=intake, stats=stats)
    return TestClient(app), workstream, stats, intake


async def _fake_garden_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    assert url == "http://garden.test/api/internal/auth/verify"
    assert headers["authorization"] == "Bearer service-token"
    assert timeout == 5.0
    user_id = str(payload.get("user_id") or "")
    if not user_id:
        return {"ok": False}
    return {
        "ok": True,
        "verification_method": "user_id",
        "user": {
            "id": user_id,
            "email": f"{user_id}@example.com",
            "name": user_id,
        },
        "session": None,
        "personal_workspace": {
            "id": "workspace_1",
        },
    }


def _garden_authenticator() -> GardenOperatorAuthenticator:
    return GardenOperatorAuthenticator(
        service_auth_token="service-token",
        verify_url="http://garden.test/api/internal/auth/verify",
        post_json=_fake_garden_post_json,
    )


def _garden_headers(user_id: str = "garden_user_1") -> dict[str, str]:
    return {
        "x-garden-user-id": user_id,
        "x-garden-workspace-id": "workspace_1",
    }


def test_workstream_api_lists_open_tasks():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    listed = client.get("/v1/tasks")

    assert listed.status_code == 200
    assert listed.json()[0]["task_id"] == "task_1"
    assert "subnet" not in listed.json()[0]


def test_workstream_api_get_task_hides_internal_route():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={
                "task_id": "task_1",
                "source": "X",
                "submission_schema": "internal.adapter.Schema",
            },
        )
    )

    response = client.get("/v1/tasks/task_1")

    assert response.status_code == 200
    assert "subnet" not in response.json()
    assert "submission_schema" not in response.json()["contract"]


def test_workstream_dashboard_renders_human_runtime_view():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X", "label": "#bittensor"},
        )
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flow Workstream" in response.text
    assert "task_1" in response.text
    assert "#bittensor" in response.text
    assert "Auth" in response.text
    assert "/dashboard/tasks" in response.text
    assert "Load more tasks" in response.text
    assert "Live view refreshes every 10 seconds" in response.text


def test_workstream_dashboard_tasks_endpoint_paginates_runtime_cards():
    client, workstream, _stats = _client()
    for index in range(3):
        workstream.publish(
            WorkstreamTask(
                task_id=f"task_{index}",
                route_key="sn13",
                source="X",
                contract={
                    "task_id": f"task_{index}",
                    "source": "X",
                    "label": f"#topic{index}",
                },
            )
        )

    response = client.get("/dashboard/tasks?offset=1&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["offset"] == 1
    assert payload["limit"] == 1
    assert payload["loaded_count"] == 2
    assert payload["next_offset"] == 2
    assert payload["has_more"] is True
    assert payload["summary"]["total_tasks"] == 3
    assert "task_1" in payload["task_html"]
    assert "task_0" not in payload["task_html"]


def test_workstream_dashboard_tasks_endpoint_hides_expired_tasks():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_expired",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_expired", "source": "X", "label": "#old"},
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    workstream.publish(
        WorkstreamTask(
            task_id="task_active",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_active", "source": "X", "label": "#now"},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )

    response = client.get("/dashboard/tasks?offset=0&limit=25")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["open_tasks"] == 1
    assert payload["summary"]["expired_tasks"] == 1
    assert payload["has_more"] is False
    assert "task_active" in payload["task_html"]
    assert "task_expired" not in payload["task_html"]


def test_workstream_api_accepts_submission_request_without_internal_route():
    client, workstream, _stats, intake = _client_with_intake()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {
                        "tweet_id": "1",
                        "username": "alice",
                        "text": "Bittensor subnet data",
                        "url": "https://x.com/example/status/1",
                        "timestamp": "2026-04-22T10:02:00+00:00",
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1
    assert intake.submitted[0].route_key == "sn13"


def test_workstream_api_rejects_public_submission_with_internal_route_field():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "route_key": "sn13",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {"text": "valid shape"},
                }
            ],
        },
    )

    assert response.status_code == 422


def test_workstream_api_rejects_unmodeled_submission_fields():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {"text": "valid shape"},
                    "unexpected": "not accepted by the contract",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_workstream_api_rejects_naive_source_created_at():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00",
                    "content": {
                        "tweet_id": "1",
                        "username": "alice",
                        "text": "Bittensor subnet data",
                        "url": "https://x.com/example/status/1",
                        "timestamp": "2026-04-22T10:02:00+00:00",
                    },
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "timezone offset" in response.text


def test_workstream_api_returns_operator_stats():
    client, _workstream, stats = _client()
    stats.set_operator_stats(
        OperatorStats(
            operator_id="operator_1",
            accepted_scorable=10,
            estimated_reward_units=7.5,
        )
    )

    response = client.get("/v1/operators/operator_1/stats")

    assert response.status_code == 200
    assert response.json()["accepted_scorable"] == 10
    assert response.json()["estimated_reward_units"] == 7.5


def test_workstream_api_requires_valid_garden_identity_when_authenticator_is_configured():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    authenticator = _garden_authenticator()
    app = create_workstream_app(
        workstream=workstream,
        intake=FakeIntake(),
        stats=stats,
        authenticator=authenticator.authenticate,
    )
    client = TestClient(app)

    unauthenticated = client.get("/v1/tasks")
    garden_verified = client.get("/v1/tasks", headers=_garden_headers())

    assert unauthenticated.status_code == 401
    assert garden_verified.status_code == 200


def test_workstream_dashboard_shows_auth_required_when_authenticator_is_configured():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    authenticator = _garden_authenticator()
    app = create_workstream_app(
        workstream=workstream,
        intake=FakeIntake(),
        stats=stats,
        authenticator=authenticator.authenticate,
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "required" in response.text


def test_workstream_api_rejects_garden_operator_mismatch():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    authenticator = _garden_authenticator()
    app = create_workstream_app(
        workstream=workstream,
        intake=FakeIntake(),
        stats=stats,
        authenticator=authenticator.authenticate,
    )
    client = TestClient(app)
    body = json.dumps(
        {
            "task_id": "task_1",
            "operator_id": "operator_2",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {"text": "valid shape"},
                }
            ],
        }
    ).encode("utf-8")

    response = client.post(
        "/v1/submissions",
        content=body,
        headers={
            "content-type": "application/json",
            **_garden_headers("garden_user_1"),
        },
    )

    assert response.status_code == 403


def test_workstream_api_derives_submission_operator_from_garden_identity():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    intake = FakeIntake()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            route_key="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )
    authenticator = _garden_authenticator()
    app = create_workstream_app(
        workstream=workstream,
        intake=intake,
        stats=stats,
        authenticator=authenticator.authenticate,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "records": [
                {
                    "uri": "https://x.com/example/status/1",
                    "source_created_at": "2026-04-22T10:02:00+00:00",
                    "content": {"text": "valid shape"},
                }
            ],
        },
        headers=_garden_headers("garden_user_1"),
    )

    assert response.status_code == 200
    assert response.json()["operator_id"] == "garden_user_1"
    assert intake.submitted[0].operator_id == "garden_user_1"


def test_default_workstream_api_runtime_wires_sqlite_and_sn13(tmp_path):
    app = create_default_app(
        {
            "JARVIS_WORKSTREAM_REQUIRE_AUTH": "0",
            "JARVIS_WORKSTREAM_DB_PATH": str(tmp_path / "workstream.sqlite3"),
            "JARVIS_SN13_DB_PATH": str(tmp_path / "sn13.sqlite3"),
        }
    )
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_workstream_api_runtime_requires_auth_by_default(tmp_path):
    with pytest.raises(ValueError, match="Workstream API auth is required"):
        create_default_app(
            {
                "JARVIS_WORKSTREAM_DB_PATH": str(tmp_path / "workstream.sqlite3"),
                "JARVIS_SN13_DB_PATH": str(tmp_path / "sn13.sqlite3"),
            }
        )


def test_workstream_api_settings_parse_host_port_and_garden_auth():
    settings = load_workstream_api_settings(
        {
            "JARVIS_WORKSTREAM_HOST": "0.0.0.0",
            "JARVIS_WORKSTREAM_PORT": "9898",
            "JARVIS_WORKSTREAM_DB_PATH": "data/custom-workstream.sqlite3",
            "JARVIS_SN13_DB_PATH": "subnets/sn13/data/custom-sn13.sqlite3",
            "GARDEN_BASE_URL": "http://localhost:3000/",
            "GARDEN_SERVICE_AUTH_TOKEN": "service-token",
            "GARDEN_AUTH_TIMEOUT_SECONDS": "7",
        }
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 9898
    assert settings.garden_base_url == "http://localhost:3000"
    assert settings.garden_auth_verify_url == "http://localhost:3000/api/internal/auth/verify"
    assert settings.garden_service_auth_token == "service-token"
    assert settings.garden_auth_timeout_seconds == 7


def test_workstream_api_settings_can_use_garden_service_token_alias():
    settings = load_workstream_api_settings(
        {
            "GARDEN_BASE_URL": "https://garden.example",
            "GARDEN_SERVICE_AUTH_TOKEN": "service-token",
        }
    )

    assert settings.garden_auth_configured is True


def test_runtime_configuration_reports_garden_auth_and_host_port():
    config = runtime_configuration(
        {
            "JARVIS_WORKSTREAM_HOST": "0.0.0.0",
            "JARVIS_WORKSTREAM_PORT": "9898",
            "GARDEN_BASE_URL": "https://garden.example",
            "GARDEN_SERVICE_AUTH_TOKEN": "service-token",
        }
    )

    assert config["host"] == "0.0.0.0"
    assert config["port"] == 9898
    assert config["auth_provider"] == "garden"
    assert config["garden_base_url"] == "https://garden.example"
    assert config["garden_auth_verify_url"] == (
        "https://garden.example/api/internal/auth/verify"
    )
