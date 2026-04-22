import json
import time

import pytest
from fastapi.testclient import TestClient

from workstream.api import create_workstream_app
from workstream.api.auth import HMACOperatorAuthenticator, sign_operator_request
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
    def submit(self, envelope: OperatorSubmissionEnvelope) -> OperatorSubmissionReceipt:
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


def _signed_headers(
    *,
    secret: str,
    operator_id: str,
    method: str,
    path_with_query: str,
    body: bytes = b"",
    nonce: str = "nonce_1",
) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "x-jarvis-operator": operator_id,
        "x-jarvis-timestamp": str(timestamp),
        "x-jarvis-nonce": nonce,
        "x-jarvis-signature": sign_operator_request(
            secret=secret,
            method=method,
            path_with_query=path_with_query,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
        ),
    }


def test_workstream_api_lists_open_tasks():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            subnet="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    listed = client.get("/v1/tasks", params={"subnet": "sn13"})

    assert listed.status_code == 200
    assert listed.json()[0]["task_id"] == "task_1"


def test_workstream_api_accepts_submission_envelope():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            subnet="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "subnet": "sn13",
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


def test_workstream_api_rejects_unmodeled_submission_fields():
    client, workstream, _stats = _client()
    workstream.publish(
        WorkstreamTask(
            task_id="task_1",
            subnet="sn13",
            source="X",
            contract={"task_id": "task_1", "source": "X"},
        )
    )

    response = client.post(
        "/v1/submissions",
        json={
            "task_id": "task_1",
            "operator_id": "operator_1",
            "subnet": "sn13",
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


def test_workstream_api_requires_valid_signature_when_authenticator_is_configured():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    authenticator = HMACOperatorAuthenticator(secrets={"operator_1": "secret"})
    app = create_workstream_app(
        workstream=workstream,
        intake=FakeIntake(),
        stats=stats,
        authenticator=authenticator.authenticate,
    )
    client = TestClient(app)

    unsigned = client.get("/v1/tasks")
    signed = client.get(
        "/v1/tasks",
        headers=_signed_headers(
            secret="secret",
            operator_id="operator_1",
            method="GET",
            path_with_query="/v1/tasks",
        ),
    )

    assert unsigned.status_code == 401
    assert signed.status_code == 200


def test_workstream_api_rejects_signed_operator_mismatch():
    workstream = InMemoryWorkstream()
    stats = InMemoryOperatorStats()
    authenticator = HMACOperatorAuthenticator(secrets={"operator_1": "secret"})
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
            "subnet": "sn13",
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
            **_signed_headers(
                secret="secret",
                operator_id="operator_1",
                method="POST",
                path_with_query="/v1/submissions",
                body=body,
            ),
        },
    )

    assert response.status_code == 403


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


def test_workstream_api_settings_parse_host_port_and_operator_map():
    settings = load_workstream_api_settings(
        {
            "JARVIS_WORKSTREAM_HOST": "0.0.0.0",
            "JARVIS_WORKSTREAM_PORT": "9898",
            "JARVIS_WORKSTREAM_DB_PATH": "data/custom-workstream.sqlite3",
            "JARVIS_SN13_DB_PATH": "subnets/sn13/data/custom-sn13.sqlite3",
            "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON": (
                '{"operator_1":"secret1","operator_2":"secret2"}'
            ),
            "JARVIS_WORKSTREAM_MAX_CLOCK_SKEW_SECONDS": "120",
        }
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 9898
    assert settings.configured_operator_count == 2
    assert settings.configured_operator_ids == ["operator_1", "operator_2"]
    assert settings.max_clock_skew_seconds == 120


def test_runtime_configuration_reports_operator_ids_and_host_port():
    config = runtime_configuration(
        {
            "JARVIS_WORKSTREAM_HOST": "0.0.0.0",
            "JARVIS_WORKSTREAM_PORT": "9898",
            "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON": (
                '{"operator_1":"secret1","operator_2":"secret2"}'
            ),
        }
    )

    assert config["host"] == "0.0.0.0"
    assert config["port"] == 9898
    assert config["configured_operator_count"] == 2
    assert config["configured_operator_ids"] == ["operator_1", "operator_2"]
