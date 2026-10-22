"""Fail-closed unit checks and opt-in tests on the full isolated restored database."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from groundtruth.services.historical_price_remediation import (
    BATCHES,
    MANIFEST_SHA,
    MARKER,
    PreconditionError,
    apply_batch,
    capture,
    check_applied,
    inspect_targets,
    integrity_checks,
    load_inputs,
    rollback_batch,
    verify_owned_changes,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "reports/generated/unit_price_historical_impact"


def test_wrong_manifest_hash_fails_before_file_or_database_access(tmp_path):
    with pytest.raises(PreconditionError, match="Authorization hash"):
        load_inputs(tmp_path / "absent.json", tmp_path / "absent_snapshot.json", "0" * 64)


@pytest.fixture
def isolated():
    url = os.environ.get("GROUNDTRUTH_REMEDIATION_TEST_URL")
    if not url:
        pytest.skip("Opt-in full restore drill database not configured")
    parsed = make_url(url)
    if not (
        parsed.host in {"localhost", "127.0.0.1"}
        and parsed.port == 15432
        and parsed.database == "rema_price_remediation_test_20261022"
    ):
        pytest.fail("Only the isolated full restore drill database is permitted")
    manifest, snapshot = load_inputs(
        PRIVATE / "reviewed/remediation_review_manifest_private.json",
        PRIVATE / "frozen_inputs_private.json",
        MANIFEST_SHA,
    )
    engine = create_engine(parsed.set(host="127.0.0.1"), connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == parsed.database
    yield engine, manifest["normalized_targets"], snapshot
    engine.dispose()


def test_isolated_fingerprint_drift_aborts(isolated):
    engine, targets, snapshot = isolated
    selected = [next(t for t in targets if t["approval_batch"] in BATCHES)]
    with engine.connect() as connection:
        tx = connection.begin()
        connection.execute(
            text("UPDATE normalized_listings SET sale_price=sale_price+1 WHERE id=:id"),
            {"id": selected[0]["normalized_id"]},
        )
        with pytest.raises(PreconditionError, match="fingerprint"):
            inspect_targets(connection, selected, snapshot)
        tx.rollback()


def test_isolated_mid_batch_failure_rolls_back(isolated, tmp_path):
    engine, targets, snapshot = isolated
    selected = [t for t in targets if t["approval_batch"] == "PRICE_ONLY_CORRECTION"][:2]
    with engine.connect() as connection:
        before = capture(connection, selected)
    with pytest.raises(RuntimeError, match="failure injection"):
        apply_batch(
            engine,
            selected,
            snapshot,
            tmp_path / "failed.json",
            "test-failure",
            "test",
            fail_after=2,
        )
    with engine.connect() as connection:
        assert capture(connection, selected) == before


def test_isolated_both_batches_idempotency_and_scoped_rollback(isolated, tmp_path):
    engine, targets, snapshot = isolated
    approved = [t for t in targets if t["approval_batch"] in BATCHES]
    with engine.connect() as connection:
        before = capture(connection, approved)
        inspect_targets(connection, targets, snapshot)
    paths = []
    for batch, count in BATCHES.items():
        path = tmp_path / (batch + ".json")
        paths.append(path)
        selected = [t for t in targets if t["approval_batch"] == batch]
        assert apply_batch(engine, selected, snapshot, path, "test-success", "test") == {
            "applied": count,
            "skipped": 0,
            "failed": 0,
        }
        assert apply_batch(engine, selected, snapshot, path, "test-success", "test") == {
            "applied": 0,
            "skipped": count,
            "failed": 0,
        }
    journals = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    with engine.connect() as connection:
        verify_owned_changes(connection, journals)
        assert integrity_checks(connection)["invalid_indexes"] == 0
        for journal in journals:
            check_applied(connection, journal)
    # A later edit to an owned price must abort rollback without partial undo.
    protected = journals[0]["changes"][0]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE normalized_listings SET sale_price=sale_price+1 WHERE id=:id"),
            {"id": protected["normalized_id"]},
        )
    with pytest.raises(PreconditionError, match="prices drifted"):
        rollback_batch(engine, paths[0])
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE normalized_listings SET sale_price=:price WHERE id=:id"),
            {"id": protected["normalized_id"], "price": protected["new_prices"]["sale_price"]},
        )
    # Later unrelated fields and rejection evidence must survive exact rollback.
    selected = approved[0]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE normalized_listings SET city='rollback test unrelated city' WHERE id=:id"),
            {"id": selected["normalized_id"]},
        )
        connection.execute(
            text(
                "UPDATE parsed_listings SET extra_fields=jsonb_set(extra_fields,'{later_unrelated}', 'true'::jsonb) WHERE id=:id"
            ),
            {"id": selected["parsed_listing_id"]},
        )
        later_invalid = connection.execute(
            text(
                "INSERT INTO invalid_listings (parsed_listing_id,stage,error_codes,message) "
                "VALUES (:id,'VALIDATE','[\"test_later_unrelated\"]'::jsonb,'test only') RETURNING id"
            ),
            {"id": selected["parsed_listing_id"]},
        ).scalar_one()
    for path in reversed(paths):
        journal = json.loads(path.read_text(encoding="utf-8"))
        assert rollback_batch(engine, path)["restored"] == len(journal["changes"])
        assert rollback_batch(engine, path)["restored"] == 0
    with engine.connect() as connection:
        after = capture(connection, approved)
    assert (
        next(r for r in after["normalized_listings"] if r["id"] == selected["normalized_id"])[
            "city"
        ]
        == "rollback test unrelated city"
    )
    p = next(r for r in after["parsed_listings"] if r["id"] == selected["parsed_listing_id"])
    assert p["extra_fields"]["later_unrelated"] is True and MARKER not in p["extra_fields"]
    assert any(r["id"] == later_invalid for r in after["invalid_listings"])
    # Undo only these test-created later writes, then prove exact restoration.
    old_n = next(r for r in before["normalized_listings"] if r["id"] == selected["normalized_id"])
    old_p = next(r for r in before["parsed_listings"] if r["id"] == selected["parsed_listing_id"])
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE normalized_listings SET city=:city WHERE id=:id"),
            {"id": old_n["id"], "city": old_n["city"]},
        )
        connection.execute(
            text("UPDATE parsed_listings SET extra_fields=CAST(:extra AS jsonb) WHERE id=:id"),
            {"id": old_p["id"], "extra": json.dumps(old_p["extra_fields"])},
        )
        connection.execute(text("DELETE FROM invalid_listings WHERE id=:id"), {"id": later_invalid})
    with engine.connect() as connection:
        assert capture(connection, approved) == before
