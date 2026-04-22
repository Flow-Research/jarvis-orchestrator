import os
from datetime import datetime, timezone

os.environ.setdefault("ARROW_USER_SIMD_LEVEL", "NONE")
import pyarrow.parquet as pq

from subnets.sn13.export import (
    EXPECTED_COLUMNS_REDDIT,
    EXPECTED_COLUMNS_X,
    SN13ExportJob,
    SN13ParquetExporter,
    UnsupportedExportSourceError,
    build_export_filename,
    expected_columns_for_source,
    extract_record_count_from_filename,
    is_valid_export_filename,
    validate_filename_row_count,
)
from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource, time_bucket_from_datetime
from subnets.sn13.storage import SQLiteStorage

NOW = datetime(2026, 4, 21, 12, 30, tzinfo=timezone.utc)


def _read_table(path):
    return pq.ParquetFile(path).read()


def _x_submission(
    *,
    uri: str = "https://x.com/macro/status/123456789",
    label: str = "#macrocosmos",
    text: str = "macrocosmos builds bittensor data infrastructure",
) -> OperatorSubmission:
    return OperatorSubmission(
        operator_id="operator_x",
        source=DataSource.X,
        label=label,
        uri=uri,
        source_created_at=NOW,
        scraped_at=NOW,
        content={
            "tweet_id": uri.rsplit("/", 1)[-1],
            "username": "macro",
            "text": text,
            "tweet_hashtags": ["#macrocosmos", "#bittensor"],
            "timestamp": NOW.isoformat(),
            "url": uri,
            "view_count": 10,
            "scraped_at": NOW.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value=label,
            job_id="job_x",
        ),
    )


def _reddit_submission() -> OperatorSubmission:
    return OperatorSubmission(
        operator_id="operator_reddit",
        source=DataSource.REDDIT,
        label="bittensor",
        uri="https://www.reddit.com/r/Bittensor/comments/abc1234/example",
        source_created_at=NOW,
        scraped_at=NOW,
        content={
            "id": "abc1234",
            "username": "tao_holder",
            "communityName": "r/Bittensor",
            "body": "subnet 13 data universe discussion",
            "title": "Data Universe",
            "createdAt": NOW.isoformat(),
            "dataType": "post",
            "url": "https://www.reddit.com/r/Bittensor/comments/abc1234/example",
            "score": 42,
            "num_comments": 7,
            "scrapedAt": NOW.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="reddit.custom.v1",
            query_type="subreddit_search",
            query_value="r/Bittensor",
            job_id="job_reddit",
        ),
    )


def test_export_filename_format_and_count_validation():
    filename = build_export_filename(
        record_count=17,
        now=NOW,
        hex_token="0123456789abcdef",
    )

    assert filename == "data_20260421_123000_17_0123456789abcdef.parquet"
    assert is_valid_export_filename(filename)
    assert extract_record_count_from_filename(filename) == 17
    validate_filename_row_count(filename, 17)


def test_export_filename_rejects_invalid_hex_token():
    try:
        build_export_filename(record_count=1, now=NOW, hex_token="not-valid")
    except ValueError as exc:
        assert "hex_token" in str(exc)
    else:
        raise AssertionError("invalid hex token was accepted")


def test_filename_row_count_validation_rejects_mismatch():
    filename = build_export_filename(
        record_count=2,
        now=NOW,
        hex_token="0123456789abcdef",
    )

    try:
        validate_filename_row_count(filename, 1)
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched row count was accepted")


def test_export_writes_x_parquet_with_upstream_schema_and_row_count(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission())
    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(
            job_id="job_x",
            source=DataSource.X,
            label="#bittensor",
            keyword="infrastructure",
        ),
        now=NOW,
        hex_token="aaaaaaaaaaaaaaaa",
    )

    assert result.skipped is False
    assert result.row_count == 1
    assert result.filename == "data_20260421_123000_1_aaaaaaaaaaaaaaaa.parquet"
    assert result.s3_relative_path == "job_id=job_x/data_20260421_123000_1_aaaaaaaaaaaaaaaa.parquet"
    assert result.s3_logical_path == (
        "hotkey=miner_hotkey/job_id=job_x/data_20260421_123000_1_aaaaaaaaaaaaaaaa.parquet"
    )

    table = _read_table(result.file_path)
    assert tuple(table.column_names) == EXPECTED_COLUMNS_X
    assert table.num_rows == 1
    assert table["tweet_id"].to_pylist() == ["123456789"]
    assert table["url"].to_pylist() == ["https://x.com/macro/status/123456789"]


def test_export_writes_reddit_parquet_with_upstream_schema(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_reddit_submission())
    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(
            job_id="job_reddit",
            source=DataSource.REDDIT,
            label="r/Bittensor",
            keyword="universe",
        ),
        now=NOW,
        hex_token="bbbbbbbbbbbbbbbb",
    )

    table = _read_table(result.file_path)
    assert tuple(table.column_names) == EXPECTED_COLUMNS_REDDIT
    assert table.num_rows == 1
    assert table["id"].to_pylist() == ["abc1234"]
    assert table["communityName"].to_pylist() == ["r/Bittensor"]


def test_export_uses_only_accepted_canonical_storage_rows(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    accepted = _x_submission(uri="https://x.com/macro/status/111")
    rejected = _x_submission(uri="https://x.com/macro/status/222")
    storage.store_submission(accepted)
    storage.record_rejection(rejected, ["missing_source_field:url"])

    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(
            job_id="job_x",
            source=DataSource.X,
            label="#macrocosmos",
        ),
        now=NOW,
        hex_token="cccccccccccccccc",
    )

    table = _read_table(result.file_path)
    assert result.row_count == 1
    assert table["tweet_id"].to_pylist() == ["111"]


def test_export_respects_job_time_bucket_and_max_rows(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_x_submission(uri="https://x.com/macro/status/1"))
    storage.store_submission(_x_submission(uri="https://x.com/macro/status/2"))
    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(
            job_id="job_x",
            source=DataSource.X,
            label="#macrocosmos",
            start_time_bucket=time_bucket_from_datetime(NOW),
            end_time_bucket=time_bucket_from_datetime(NOW),
            max_rows=1,
        ),
        now=NOW,
        hex_token="dddddddddddddddd",
    )

    table = _read_table(result.file_path)
    assert result.row_count == 1
    assert table.num_rows == 1


def test_export_skips_empty_job_without_creating_file(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(job_id="empty", source=DataSource.X, label="#missing"),
        now=NOW,
        hex_token="eeeeeeeeeeeeeeee",
    )

    assert result.skipped is True
    assert result.row_count == 0
    assert result.file_path is None


def test_export_rejects_unconfirmed_youtube_schema():
    try:
        expected_columns_for_source(DataSource.YOUTUBE)
    except UnsupportedExportSourceError:
        pass
    else:
        raise AssertionError("unconfirmed YouTube export schema was accepted")
