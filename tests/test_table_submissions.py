"""Opt-in real Azurite transaction semantics; never touches cloud storage."""

import concurrent.futures
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest

pytest.importorskip("azure.data.tables")
from azure.core.exceptions import (
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.data.tables import TableServiceClient

from groundtruth.services.product_submissions import DuplicateSubmission
from groundtruth.services.table_submissions import SubmissionTable


@pytest.fixture
def store():
    value = os.environ.get("TEST_TABLE_EMULATOR_CONNECTION_STRING", "")
    allowed = [f"TableEndpoint=http://127.0.0.1:{port}/localmetrik" for port in (26402, 27402)]
    allowed.append("TableEndpoint=http://metrik-c-table:10002/localmetrik")
    if not any(endpoint in value for endpoint in allowed):
        pytest.skip("Owned loopback Azurite fixture required")
    svc = TableServiceClient.from_connection_string(
        value, retry_total=0, connection_timeout=2, read_timeout=3
    )
    client = svc.create_table("BudgetTest" + uuid4().hex)
    yield SubmissionTable(client)
    fresh = TableServiceClient.from_connection_string(
        value, retry_total=0, connection_timeout=2, read_timeout=3
    )
    fresh.delete_table(client.table_name)


def test_concurrency_and_rolling_window_keep_history(store):
    now = datetime.now(UTC)
    body = {"message": "concurrent synthetic submission"}

    def send(_):
        try:
            store.append("contact", body, window_seconds=300, now=now)
            return "saved"
        except DuplicateSubmission:
            return "duplicate"

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        out = list(pool.map(send, range(24)))
    assert out.count("saved") == 1 and out.count("duplicate") == 23
    store.append("contact", body, window_seconds=300, now=now + timedelta(seconds=301))
    assert len(store.records()) == 2


def test_failed_batch_leaves_no_orphan_guard(store):
    old = {"PartitionKey": "contact", "RowKey": "existing", "RecordType": "submission"}
    store.client.create_entity(old)
    with pytest.raises(HttpResponseError):
        store.client.submit_transaction(
            [("create", {"PartitionKey": "contact", "RowKey": "new-guard"}), ("create", old)]
        )
    with pytest.raises(ResourceNotFoundError):
        store.client.get_entity("contact", "new-guard")


def test_fail_before_commit_is_retryable(store):
    payload = {"message": "failed before transaction"}
    with (
        patch.object(
            store.client, "submit_transaction", side_effect=ServiceRequestError("synthetic outage")
        ),
        pytest.raises(ServiceRequestError),
    ):
        store.append("contact", payload, window_seconds=300)
    assert store.records() == []
    store.append("contact", payload, window_seconds=300)
    assert len(store.records()) == 1


def test_lost_success_reply_does_not_duplicate(store):
    real = store.client.submit_transaction

    def lost(*args, **kwargs):
        real(*args, **kwargs)
        raise ServiceResponseError("synthetic lost reply")

    payload = {"message": "commit before network failure"}
    with (
        patch.object(store.client, "submit_transaction", side_effect=lost),
        pytest.raises(ServiceResponseError),
    ):
        store.append("contact", payload, window_seconds=300)
    with pytest.raises(DuplicateSubmission):
        store.append("contact", payload, window_seconds=300)
    assert len(store.records()) == 1


def test_import_preserves_ids_payloads_timestamps_and_is_restartable(store):
    now = datetime.now(UTC)
    payload = {"name": "Synthetic", "message": "legacy row", "ts": now.isoformat()}
    rows = [
        {"id": 1, "kind": "contact", "payload": payload, "created_at": now, "updated_at": now},
        {"id": 2, "kind": "contact", "payload": payload, "created_at": now, "updated_at": now},
    ]
    store.import_legacy(rows)
    store.import_legacy(rows)
    assert sorted(r["LegacyId"] for r in store.records()) == [1, 2]
    with pytest.raises(DuplicateSubmission):
        store.append("contact", {k: v for k, v in payload.items() if k != "ts"}, window_seconds=300)
    with pytest.raises(ValueError):
        store.import_legacy([{**rows[0], "payload": {"message": "conflicting"}}])
    assert len(store.records()) == 2


def test_real_loopback_emulator_restart_preserves_record_and_retry_guard(store):
    """Actual SDK writes and process restart; never runs against Azure."""
    import subprocess
    import time
    from pathlib import Path

    script = os.environ.get("TEST_TABLE_RESTART_SCRIPT", "")
    owned = Path(__file__).resolve().parent / "table_emulator.ps1"
    if os.name != "nt" or not script or Path(script).resolve() != owned:
        pytest.skip("Owned Windows loopback emulator restart control required")
    body = {"message": "publication safety isolated restart verification"}
    store.append("event", body, window_seconds=300)
    before = store.records()
    # Azurite's local Loki backing store autosaves on a timer. This is emulator
    # disk persistence, not a claim about Azure's durability implementation.
    time.sleep(6)
    # A long-lived child must not inherit Popen's captured pipe handles on Windows.
    with (owned.parent.parent / ".tmp/table-emulator/restart-test.log").open("w") as log:
        subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(owned), "-Mode", "Restart"],
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
    # Recreate the application client too; don't reuse sockets from the stopped process.
    service = TableServiceClient.from_connection_string(
        os.environ["TEST_TABLE_EMULATOR_CONNECTION_STRING"],
        retry_total=0,
        connection_timeout=2,
        read_timeout=3,
    )
    restarted = SubmissionTable(service.get_table_client(store.client.table_name))
    for attempt in range(20):
        try:
            after = restarted.records()
            break
        except Exception:
            if attempt == 19:
                raise
            time.sleep(0.5)
    assert after == before
    with pytest.raises(DuplicateSubmission):
        restarted.append("event", body, window_seconds=300)
    assert restarted.records() == before
