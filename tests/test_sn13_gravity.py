from datetime import datetime, timezone

import pytest

from subnets.sn13.gravity import (
    GRAVITY_TOTAL_URL,
    GravityFetchError,
    fetch_gravity_records,
    load_gravity_cache,
    refresh_gravity_cache,
    write_gravity_cache,
)


def _records():
    return [
        {
            "id": "gravity_reddit",
            "weight": 1.5,
            "params": {
                "keyword": None,
                "platform": "reddit",
                "label": "r/Bittensor_",
                "post_start_datetime": None,
                "post_end_datetime": None,
            },
        },
        {
            "id": "gravity_x",
            "weight": 4.0,
            "params": {
                "keyword": None,
                "platform": "x",
                "label": "#macrocosmos",
                "post_start_datetime": None,
                "post_end_datetime": None,
            },
        },
    ]


def test_write_and_load_gravity_cache_round_trip(tmp_path):
    fetched_at = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)

    written = write_gravity_cache(
        _records(),
        cache_dir=tmp_path,
        source_url=GRAVITY_TOTAL_URL,
        fetched_at=fetched_at,
    )
    loaded = load_gravity_cache(cache_dir=tmp_path)

    assert written.cache_path.exists()
    assert written.metadata_path.exists()
    assert loaded.metadata.record_count == 2
    assert loaded.metadata.sha256 == written.metadata.sha256
    assert loaded.snapshot.source_ref == GRAVITY_TOTAL_URL
    assert [job.job_id for job in loaded.snapshot.jobs] == ["gravity_reddit", "gravity_x"]


def test_refresh_gravity_cache_uses_fetcher(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from subnets.sn13 import gravity

    monkeypatch.setattr(gravity, "fetch_gravity_records", lambda **kwargs: _records())

    result = refresh_gravity_cache(cache_dir=tmp_path, url="https://example.test/total.json")

    assert result.metadata.source_url == "https://example.test/total.json"
    assert result.metadata.record_count == 2


def test_load_gravity_cache_errors_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="dd refresh"):
        load_gravity_cache(cache_dir=tmp_path)


def test_fetch_gravity_records_rejects_non_list(monkeypatch: pytest.MonkeyPatch):
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"not": "a-list"}'

    monkeypatch.setattr("subnets.sn13.gravity.urlopen", lambda *args, **kwargs: _FakeResponse())

    with pytest.raises(GravityFetchError, match="JSON list"):
        fetch_gravity_records(url="https://example.test/total.json")
