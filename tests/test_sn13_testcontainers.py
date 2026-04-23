from datetime import datetime, timezone
from pathlib import Path

import docker
import pyarrow.parquet as pq
import pytest
from testcontainers.core.container import DockerContainer

from subnets.sn13.export import EXPECTED_COLUMNS_X, SN13ExportJob, SN13ParquetExporter
from subnets.sn13.intake import OperatorSubmission, SubmissionProvenance
from subnets.sn13.models import DataSource
from subnets.sn13.storage import SQLiteStorage

pytestmark = pytest.mark.integration

NOW = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)


def _docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _submission() -> OperatorSubmission:
    uri = "https://x.com/macro/status/987654321"
    return OperatorSubmission(
        operator_id="operator_tc",
        source=DataSource.X,
        label="#macrocosmos",
        uri=uri,
        source_created_at=NOW,
        scraped_at=NOW,
        content={
            "tweet_id": "987654321",
            "username": "macro",
            "text": "testcontainers proves export artifacts cross a docker boundary",
            "tweet_hashtags": ["#macrocosmos"],
            "timestamp": NOW.isoformat(),
            "url": uri,
            "scraped_at": NOW.isoformat(),
        },
        provenance=SubmissionProvenance(
            scraper_id="x.custom.v1",
            query_type="label_search",
            query_value="#macrocosmos",
            job_id="job_tc",
        ),
    )


@pytest.mark.skipif(not _docker_available(), reason="Docker is required for Testcontainers")
def test_export_artifact_is_visible_inside_testcontainer(tmp_path):
    storage = SQLiteStorage(tmp_path / "sn13.sqlite3")
    storage.store_submission(_submission())
    exporter = SN13ParquetExporter(
        storage=storage,
        output_root=tmp_path / "exports",
        miner_hotkey="miner_hotkey",
    )

    result = exporter.export_job(
        SN13ExportJob(
            job_id="job_tc",
            source=DataSource.X,
            label="#macrocosmos",
            keyword="docker boundary",
        ),
        now=NOW,
        hex_token="abcdefabcdefabcd",
    )

    table = pq.ParquetFile(result.file_path).read()
    assert tuple(table.column_names) == EXPECTED_COLUMNS_X
    assert table.num_rows == 1

    export_root = Path(tmp_path / "exports").resolve()
    expected_container_path = (
        "/exports/hotkey=miner_hotkey/job_id=job_tc/"
        "data_20260421_120000_1_abcdefabcdefabcd.parquet"
    )

    with DockerContainer("alpine:3.20").with_command("sleep 120").with_volume_mapping(
        export_root,
        "/exports",
        mode="ro",
    ) as container:
        file_check = container.exec(["sh", "-c", f"test -f '{expected_container_path}'"])
        count_check = container.exec(
            [
                "sh",
                "-c",
                "find /exports -name '*.parquet' -type f | wc -l | tr -d ' '",
            ]
        )

    assert file_check.exit_code == 0
    assert count_check.exit_code == 0
    assert count_check.output.decode().strip() == "1"
