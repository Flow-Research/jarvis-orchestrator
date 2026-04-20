"""Unit tests for the protocol observation helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from listener.protocol_observer import (
    ProtocolObserver,
    describe_schema,
    extract_payload,
    extract_timeout_seconds,
    extract_validator_hotkey,
    json_safe,
)


class DummyDendrite:
    def __init__(self, hotkey: str = "5abc", timeout: float = 12.5):
        self.hotkey = hotkey
        self.timeout = timeout


class DummySynapse:
    def __init__(self):
        self.name = "GetDataEntityBucket"
        self.timeout = 30
        self.dendrite = DummyDendrite()
        self.axon = {"ip": "127.0.0.1", "port": 8091}
        self.data_entity_bucket_id = {
            "source": "X",
            "time_bucket_id": 1845,
            "label": "$BTC",
            "expected_count": 1200,
        }
        self.bucket_ids = [{"source": "X", "time_bucket_id": 1845, "label": "$BTC"}]


class ProtocolObserverTests(unittest.TestCase):
    def test_json_safe_handles_nested_objects(self) -> None:
        value = DummySynapse()
        safe = json_safe(value)
        self.assertIsInstance(safe, dict)
        self.assertEqual(safe["name"], "GetDataEntityBucket")
        self.assertEqual(safe["dendrite"]["hotkey"], "5abc")

    def test_extract_payload_excludes_transport_fields(self) -> None:
        payload = extract_payload(
            {
                "dendrite": {"hotkey": "5abc"},
                "axon": {"ip": "127.0.0.1"},
                "timeout": 30,
                "data_entity_bucket_id": {"label": "$BTC"},
            }
        )
        self.assertEqual(payload, {"data_entity_bucket_id": {"label": "$BTC"}})

    def test_schema_description_is_recursive(self) -> None:
        schema = describe_schema({"items": [{"label": "$BTC", "count": 2}]})
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["fields"]["items"]["type"], "array")
        self.assertEqual(
            schema["fields"]["items"]["items"]["fields"]["label"]["type"],
            "str",
        )

    def test_extractors_find_hotkey_and_timeout(self) -> None:
        synapse = DummySynapse()
        self.assertEqual(extract_validator_hotkey(synapse), "5abc")
        self.assertEqual(extract_timeout_seconds(synapse), 30.0)

    def test_record_persists_event_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observer = ProtocolObserver(capture_dir=tmpdir)
            synapse = DummySynapse()

            observation = observer.record(
                query_type="GetDataEntityBucket",
                synapse=synapse,
                response_payload={"data_entities": [{"content": "hello"}]},
                latency_ms=8.75,
                notes=["test capture"],
                extra={"stage": "unit-test"},
            )

            self.assertEqual(observation.validator_hotkey, "5abc")
            self.assertEqual(observation.payload["data_entity_bucket_id"]["label"], "$BTC")
            self.assertEqual(observation.response_schema["fields"]["data_entities"]["type"], "array")

            summary = json.loads((Path(tmpdir) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["total_queries"], 1)
            self.assertEqual(summary["counts_by_query_type"]["GetDataEntityBucket"], 1)

            lines = (Path(tmpdir) / "queries.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["query_id"], observation.query_id)


if __name__ == "__main__":
    unittest.main()
