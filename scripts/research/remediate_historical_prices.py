"""Execute the exact approved private historical price batches; dry-run by default."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from groundtruth.services.historical_price_remediation import (
    BATCHES,
    MANIFEST_SHA,
    apply_batch,
    check_applied,
    check_structure,
    database_fingerprints,
    inspect_targets,
    integrity_checks,
    load_inputs,
    require,
    rollback_batch,
    save_journal,
    sha,
    verify_owned_changes,
)

ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE = "rema_price_remediation_test_20261022"


def guarded_engine(test_database=False):
    url = make_url(dotenv_values("C:/MetrikResearch/config/research.env")["DATABASE_URL"])
    require(
        url.host in {"localhost", "127.0.0.1"} and url.port == 15432 and url.database == "rema",
        "Only local research rema:15432 is authorized",
    )
    if test_database:
        url = url.set(database=TEST_DATABASE)
    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 5,
            "application_name": "groundtruth_historical_price_remediation",
        },
    )
    with engine.connect() as connection:
        require(
            connection.execute(text("SELECT current_database()")).scalar_one()
            == (TEST_DATABASE if test_database else "rema"),
            "Live DB identity differs",
        )
    return engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument(
        "--test-database", action="store_true", help="Use only the named isolated restored test DB"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    require(
        ROOT not in [args.audit_dir.resolve(), *args.audit_dir.resolve().parents],
        "Private journals must be outside Git",
    )
    require(
        args.execution_id and all(c.isalnum() or c in "-_" for c in args.execution_id),
        "Invalid execution ID",
    )
    manifest, snapshot = load_inputs(args.manifest, args.snapshot, args.manifest_sha256)
    targets = manifest["normalized_targets"]
    engine = guarded_engine(args.test_database)
    directory = args.audit_dir / args.execution_id
    if args.apply:
        require(
            args.backup_receipt is not None, "Apply requires verified full-backup/restore receipt"
        )
        receipt = json.loads(args.backup_receipt.read_text(encoding="utf-8"))
        require(receipt.get("restore_verified") is True, "Restore drill has not passed")
        require(receipt["manifest_sha256"] == MANIFEST_SHA, "Backup receipt manifest differs")
        require(sha(receipt["backup"]) == receipt["sha256"], "Backup file changed")
        require(receipt["restore_database"] == TEST_DATABASE, "Unexpected restore database")
        directory.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if args.rollback:
        output = {}
        for batch in reversed(BATCHES):
            path = directory / (batch + ".json")
            if path.exists():
                journal = json.loads(path.read_text(encoding="utf-8"))
                expected_targets = [t for t in targets if t["approval_batch"] == batch]
                require(
                    journal["execution_id"] == args.execution_id and journal["batch"] == batch,
                    "Rollback execution identity differs",
                )
                require(
                    [
                        (c["normalized_id"], c["parsed_listing_id"], c["raw_id"])
                        for c in journal["changes"]
                    ]
                    == [
                        (t["normalized_id"], t["parsed_listing_id"], t["raw_id"])
                        for t in expected_targets
                    ],
                    "Rollback target identity differs from approved manifest",
                )
                output[batch] = rollback_batch(engine, path)
        print(json.dumps({"rollback": output}))
        return
    # No approved batch may write before ALL original target preconditions pass.
    # For a repeat, validate its own post-state rather than the old fingerprints.
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True
    ) as connection:
        require(
            not connection.execute(
                text(
                    "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                    "AND pid<>pg_backend_pid() AND state<>'idle' LIMIT 1"
                )
            ).first(),
            "Other active DB sessions",
        )
        check_structure(connection)
        pending = []
        for batch in BATCHES:
            path = directory / (batch + ".json")
            batch_targets = [t for t in targets if t["approval_batch"] == batch]
            if path.exists():
                journal = json.loads(path.read_text(encoding="utf-8"))
                require(journal["execution_id"] == args.execution_id, "Journal execution differs")
                check_applied(connection, journal)
            else:
                pending.extend(batch_targets)
        pending += [t for t in targets if t["approval_batch"] not in BATCHES]
        inspect_targets(connection, pending, snapshot)
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    "manifest_sha256": MANIFEST_SHA,
                    "approved_batches": BATCHES,
                    "all_target_preconditions": True,
                    "writes": 0,
                }
            )
        )
        return
    baseline_path = directory / "outside_targets_before.json"
    if not baseline_path.exists():
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            baseline = database_fingerprints(connection, targets)
        save_journal(baseline_path, baseline)
    else:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    results = {}
    try:
        for batch in BATCHES:
            path = directory / (batch + ".json")
            results[batch] = apply_batch(
                engine,
                [t for t in targets if t["approval_batch"] == batch],
                snapshot,
                path,
                args.execution_id,
                revision,
            )
            print(json.dumps({"batch": batch, **results[batch]}), flush=True)
        journals = [
            json.loads((directory / (batch + ".json")).read_text(encoding="utf-8"))
            for batch in BATCHES
        ]
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            verify_owned_changes(connection, journals)
            integrity = integrity_checks(connection)
            added = [
                c["invalid_row"]["id"]
                for j in journals
                for c in j["changes"]
                if c.get("invalid_row")
            ]
            after = database_fingerprints(connection, targets, added)
            require(
                after == baseline, "Unrelated database contents changed; rolling back owned changes"
            )
        save_journal(
            directory / "post_write_invariants.json",
            {
                "all_public_base_tables_outside_targets_unchanged": True,
                "full_owned_rows_only_authorized_differences": True,
                "quarantine_additions": len(added),
                "integrity": integrity,
                "fingerprints_after_excluding_owned_changes": after,
            },
        )
        save_journal(
            directory / "execution.json",
            {
                "authorization": "USER_APPROVED_EXACT_MANIFEST",
                "execution_id": args.execution_id,
                "manifest_sha256": MANIFEST_SHA,
                "code_revision": revision,
                "test_database": args.test_database,
                "backup_receipt": str(args.backup_receipt.resolve()),
                "results": results,
            },
        )
    except Exception:
        # Undo any batch known committed when a later batch fails its gates.
        for batch in reversed(BATCHES):
            path = directory / (batch + ".json")
            if path.exists():
                journal = json.loads(path.read_text(encoding="utf-8"))
                if journal["status"] in {"APPLIED", "PREPARED"}:
                    rollback_batch(engine, path)
        raise


if __name__ == "__main__":
    main()
