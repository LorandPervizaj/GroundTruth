"""Bounded, fail-closed historical Gjirafa correction with private undo journals.

No ETL replay or schema changes. Journals are fsynced before commit; a marker in
the same transaction identifies an applied batch after an interrupted client.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from groundtruth.processing.validation import ListingValidator
from groundtruth.schemas.pipeline import NormalizedListingSchema
from groundtruth.services.parsing import ParsingService

MANIFEST_SHA = "b6126ad97dd3c60f95798eba3af132062f0445e1b76ceae1857e17d90c06b4cf"
SNAPSHOT_SHA = "6a777be1b9cbf5baab0003b0686df6add7b07fb4d0806cc64d08f99e566f024b"
BATCHES = {"PRICE_ONLY_CORRECTION": 402, "QUARANTINE_UNRESOLVED_TOTAL": 256}
MARKER = "historical_price_remediation"


class PreconditionError(RuntimeError):
    """Evidence or current state does not authorize a write."""


def require(condition, message):
    if not condition:
        raise PreconditionError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def json_value(value):
    return json.loads(json.dumps(value, default=str))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def save_journal(path, value):
    """Durable private intent precedes commit, and can reconcile a lost receipt."""
    path = Path(path)
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_inputs(manifest_path, snapshot_path, expected_sha):
    require(expected_sha == MANIFEST_SHA, "Authorization hash is not the approved hash")
    require(sha(manifest_path) == expected_sha, "Manifest bytes changed")
    require(sha(snapshot_path) == SNAPSHOT_SHA, "Frozen input bytes changed")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    targets = manifest["normalized_targets"]
    require(
        Counter(t["approval_batch"] for t in targets) == {**BATCHES, "HOLD_SOURCE_UNIT_OUTLIER": 1},
        "Unexpected batch membership",
    )
    require(len({t["normalized_id"] for t in targets}) == 659, "Duplicate targets")
    require(len({t["parsed_listing_id"] for t in targets}) == 659, "Shared parsed target")
    held = [t for t in targets if t["approval_batch"] not in BATCHES]
    require(
        held[0]["raw_id"] == 23992 and held[0]["normalized_id"] == 272603,
        "Held outlier changed",
    )
    broad_ids = {r["raw_id"] for r in snapshot["broader_syntax_review"]}
    require(len(broad_ids) == 217, "Broader review membership changed")
    require(not broad_ids & {t["raw_id"] for t in targets}, "Excluded syntax overlap")
    require(manifest["frozen_input_sha256"] == SNAPSHOT_SHA, "Wrong snapshot lineage")
    return manifest, snapshot


def projection(connection, snapshot, ids=None):
    sql = snapshot["normalized_sql"]
    params = dict(snapshot["active_params"])
    params["cutoff_date"] = date.fromisoformat(params["cutoff_date"])
    if ids is not None:
        sql = sql.rsplit("ORDER BY nl.id", 1)[0] + " WHERE nl.id=ANY(:ids) ORDER BY nl.id"
        params["ids"] = list(ids)
    return json_value([dict(r) for r in connection.execute(text(sql), params).mappings()])


def rows(connection, table, column, ids):
    # Identifiers are internal constants, never command-line strings.
    require(
        table
        in {
            "normalized_listings",
            "parsed_listings",
            "raw_listings",
            "invalid_listings",
            "data_lineage",
            "listing_sources",
            "listing_observations",
        },
        "Unsupported table",
    )
    require(
        column in {"id", "parsed_listing_id", "normalized_listing_id", "raw_listing_id"},
        "Unsupported key",
    )
    return [
        r[0]
        for r in connection.execute(
            text(f"SELECT to_jsonb(x) FROM {table} x WHERE {column}=ANY(:ids) ORDER BY id"),
            {"ids": list(ids)},
        )
    ]


def capture(connection, targets):
    nids = [t["normalized_id"] for t in targets]
    pids = [t["parsed_listing_id"] for t in targets]
    rawids = sorted({t["raw_id"] for t in targets})
    result = {
        "normalized_listings": rows(connection, "normalized_listings", "id", nids),
        "parsed_listings": rows(connection, "parsed_listings", "id", pids),
        "raw_listings": rows(connection, "raw_listings", "id", rawids),
    }
    for table in ["invalid_listings", "data_lineage", "listing_sources"]:
        # Include dependents linked through either normalized or parsed identity.
        linked = rows(connection, table, "parsed_listing_id", pids)
        linked += rows(connection, table, "normalized_listing_id", nids)
        if table != "listing_sources":
            linked += rows(connection, table, "raw_listing_id", rawids)
        result[table] = sorted({r["id"]: r for r in linked}.values(), key=lambda r: r["id"])
    result["listing_observations"] = rows(
        connection, "listing_observations", "normalized_listing_id", nids
    )
    return result


def schema(row):
    values = dict(row)
    for key in ["property_type", "listing_type", "building_age_category", "heating_type"]:
        if values.get(key):
            values[key] = values[key].lower()
    return NormalizedListingSchema.model_validate(values)


def price_values(target):
    total = target["new_sale_price"]
    area = target["stored_area"]
    psm = round(float(total) / area, 2) if total and area else None
    require(equal(psm, target["new_price_per_sqm"]), "Manifest dependent arithmetic differs")
    return {
        "sale_price": None if total is None else str(Decimal(str(total))),
        "price_per_sqm": None if psm is None else str(Decimal(str(psm))),
    }


def equal(left, right):
    if left is None or right is None:
        return left is right
    return Decimal(str(left)) == Decimal(str(right))


def inspect_targets(connection, targets, snapshot):
    """Exact frozen fingerprints plus independent replay from original DB source."""
    projected = {
        r["normalized_id"]: r
        for r in projection(connection, snapshot, [t["normalized_id"] for t in targets])
    }
    state = capture(connection, targets)
    ns = {r["id"]: r for r in state["normalized_listings"]}
    ps = {r["id"]: r for r in state["parsed_listings"]}
    raws = {r["id"]: r for r in state["raw_listings"]}
    frozen_raw = {r["id"]: r for r in snapshot["candidate_raw_versions"]}
    parser, validator = ParsingService(), ListingValidator()
    replacements = {}
    for target in targets:
        nid, pid, rid = target["normalized_id"], target["parsed_listing_id"], target["raw_id"]
        require(
            nid in projected and fingerprint(projected[nid]) == target["current_row_fingerprint"],
            f"Frozen fingerprint mismatch: normalized {nid}",
        )
        n, p, raw = ns[nid], ps[pid], raws[rid]
        require(n["parsed_listing_id"] == pid and p["raw_listing_id"] == rid, "ID lineage mismatch")
        require(
            all(
                r["source_website"] == "gjirafa"
                and r["source_listing_id"] == target["source_listing_id"]
                for r in [n, p, raw]
            ),
            "Source identity mismatch",
        )
        require(n["parser_version"] == p["parser_version"], "Parser lineage mismatch")
        require(raw["content_hash"] == frozen_raw[rid]["content_hash"], "Raw content hash changed")
        require(
            all(
                raw["raw_payload"].get(key) == value
                for key, value in frozen_raw[rid]["raw_payload"].items()
                if key != "description"
            ),
            "Frozen source extraction fields changed",
        )
        require(
            hashlib.sha256(str(raw["raw_payload"].get("description") or "").encode()).hexdigest()
            == frozen_raw[rid]["description_sha256"],
            "Original source description changed",
        )
        require(
            equal(n["sale_price"], target["old_sale_price"])
            and equal(n["price_per_sqm"], target["old_price_per_sqm"]),
            "Old prices changed",
        )
        require(equal(p["sale_price"], projected[nid]["parsed_sale_price"]), "Parsed price changed")
        require(MARKER not in (p["extra_fields"] or {}), "Existing remediation marker")
        for lineage in state["data_lineage"]:
            if lineage["normalized_listing_id"] == nid:
                require(
                    lineage["raw_listing_id"] == rid
                    and lineage["parsed_listing_id"] == pid
                    and lineage["parser_version"] == n["parser_version"]
                    and lineage["normalization_version"] == n["normalization_version"]
                    and lineage["gazetteer_version"] == n["gazetteer_version"],
                    "Dependent lineage differs",
                )
        parsed = parser.parse_raw(SimpleNamespace(**raw))
        require(equal(parsed.sale_price, target["new_sale_price"]), f"Source replay differs: {nid}")
        replacement = price_values(target)
        normalized = schema(n)
        before = sorted(i.code for i in validator.validate(normalized).issues)
        after_schema = normalized.model_copy(
            update={k: Decimal(v) if v is not None else None for k, v in replacement.items()}
        )
        after = sorted(i.code for i in validator.validate(after_schema).issues)
        require(
            before == target["before_validator_codes"] and after == target["after_validator_codes"],
            f"Validator replay differs: {nid}",
        )
        require(
            sorted(set(after) - set(before)) == target["introduced_validation_codes"],
            "Validation additions differ",
        )
        replacement["provenance"] = parsed.extra_fields["provenance"]["sale_price"]
        replacement["snapshot"] = after_schema.model_dump(mode="json")
        replacements[nid] = replacement
    return state, replacements


def lock_tables(connection):
    connection.execute(text("SET LOCAL lock_timeout='5s'"))
    connection.execute(text("SET LOCAL statement_timeout='120s'"))
    # The brief writer lock also prevents new child/quarantine/ETL rows between
    # precondition checks and commit, including writers outside this command.
    connection.execute(
        text(
            "LOCK TABLE raw_listings, parsed_listings, normalized_listings, "
            "invalid_listings, data_lineage, listing_sources, listing_observations "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    check_structure(connection)


def check_structure(connection):
    affected = ["raw_listings", "parsed_listings", "normalized_listings", "invalid_listings"]
    require(
        not connection.execute(
            text(
                "SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
                "AND c.relname=ANY(:tables) AND NOT t.tgisinternal LIMIT 1"
            ),
            {"tables": affected},
        ).first(),
        "Unexpected user trigger on affected table",
    )
    expected = {
        "raw_listings": {"parsed_listings", "invalid_listings", "data_lineage"},
        "parsed_listings": {
            "normalized_listings",
            "invalid_listings",
            "data_lineage",
            "listing_sources",
        },
        "normalized_listings": {
            "invalid_listings",
            "data_lineage",
            "listing_sources",
            "listing_observations",
        },
        "invalid_listings": set(),
    }
    references = connection.execute(
        text(
            "SELECT src.relname dependent,dst.relname target FROM pg_constraint k "
            "JOIN pg_class src ON src.oid=k.conrelid JOIN pg_class dst ON dst.oid=k.confrelid "
            "WHERE k.contype='f' AND k.confrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace "
            "AND relname=ANY(:tables))"
        ),
        {"tables": affected},
    ).mappings()
    for reference in references:
        require(
            reference["dependent"] in expected[reference["target"]], "Unexpected dependent table"
        )
    require(
        not connection.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated LIMIT 1"
            )
        ).first(),
        "Unvalidated database constraint",
    )


def check_applied(connection, journal):
    for change in journal["changes"]:
        n = rows(connection, "normalized_listings", "id", [change["normalized_id"]])[0]
        p = rows(connection, "parsed_listings", "id", [change["parsed_listing_id"]])[0]
        require(
            all(equal(n[k], v) for k, v in change["new_prices"].items()),
            "Applied normalized prices drifted",
        )
        require(
            equal(p["sale_price"], change["new_prices"]["sale_price"]),
            "Applied parsed price drifted",
        )
        require(
            (p["extra_fields"] or {}).get(MARKER) == change["marker"],
            "Applied audit marker differs",
        )
        require(
            p["extra_fields"]["provenance"]["sale_price"] == change["new_provenance"],
            "Applied provenance differs",
        )
        if change.get("invalid_row"):
            found = rows(connection, "invalid_listings", "id", [change["invalid_row"]["id"]])
            require(found == [change["invalid_row"]], "Owned quarantine row changed")


def database_fingerprints(connection, targets, added_invalid_ids=()):
    """All public base-table contents outside the exact owned rows, including raw HTML."""
    tables = (
        connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        )
        .scalars()
        .all()
    )
    result = {}
    for table in tables:
        # Catalog-derived identifiers are quoted; no caller-provided SQL identifier.
        quoted = connection.dialect.identifier_preparer.quote(table)
        omitted = []
        if table == "normalized_listings":
            omitted = [t["normalized_id"] for t in targets if t["approval_batch"] in BATCHES]
        elif table == "parsed_listings":
            omitted = [t["parsed_listing_id"] for t in targets if t["approval_batch"] in BATCHES]
        elif table == "invalid_listings":
            omitted = list(added_invalid_ids)
        where = "WHERE NOT (id=ANY(:ids))" if omitted else ""
        row_digest = "md5(to_jsonb(x)::text)"
        if table == "raw_listings":
            # Cover all columns and HTML bytes without allocating escaped HTML.
            columns = (
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
                        "AND table_name='raw_listings' ORDER BY ordinal_position"
                    )
                )
                .scalars()
                .all()
            )
            terms = []
            for column in columns:
                term = "x." + connection.dialect.identifier_preparer.quote(column)
                terms.append(
                    f"md5({term}::text)" if column in {"raw_html", "raw_payload"} else term
                )
            row_digest = "md5(jsonb_build_array(" + ",".join(terms) + ")::text)"
        result[table] = dict(
            connection.execute(
                text(
                    f"SELECT count(*) total,md5(string_agg(digest,'' ORDER BY digest)) content_digest "
                    f"FROM (SELECT {row_digest} digest FROM {quoted} x {where}) hashed"
                ),
                {"ids": omitted},
            )
            .mappings()
            .one()
        )
    return result


def verify_owned_changes(connection, journals):
    """Full target rows and dependent history must differ only in approved fields."""
    for journal in journals:
        check_applied(connection, journal)
        changes = {r["normalized_id"]: r for r in journal["changes"]}
        by_parsed = {r["parsed_listing_id"]: r for r in journal["changes"]}
        before = journal["before_images"]
        for old in before["normalized_listings"]:
            change = changes[old["id"]]
            current = rows(connection, "normalized_listings", "id", [old["id"]])[0]
            require(
                all(equal(current[k], v) for k, v in change["new_prices"].items()),
                "Wrong replacement",
            )
            require(
                {k: v for k, v in current.items() if k not in change["new_prices"]}
                == {k: v for k, v in old.items() if k not in change["new_prices"]},
                "Unrelated normalized field changed",
            )
        for old in before["parsed_listings"]:
            change = by_parsed[old["id"]]
            expected = copy.deepcopy(old)
            expected["sale_price"] = change["new_prices"]["sale_price"]
            expected["extra_fields"] = copy.deepcopy(old["extra_fields"] or {})
            expected["extra_fields"].setdefault("provenance", {})["sale_price"] = change[
                "new_provenance"
            ]
            expected["extra_fields"][MARKER] = change["marker"]
            current = rows(connection, "parsed_listings", "id", [old["id"]])[0]
            require(
                equal(current.pop("sale_price"), expected.pop("sale_price"))
                and current == expected,
                "Unrelated parsed field changed",
            )
        for table in [
            "invalid_listings",
            "data_lineage",
            "listing_sources",
            "listing_observations",
        ]:
            old_rows = before[table]
            if old_rows:
                require(
                    rows(connection, table, "id", [r["id"] for r in old_rows]) == old_rows,
                    "Pre-existing dependent history changed",
                )
        for change in journal["changes"]:
            if change.get("invalid_row"):
                require(
                    change["invalid_row"]["error_codes"] == ["missing_price"],
                    "Unexpected exclusion added",
                )


def integrity_checks(connection):
    foreign_keys = (
        connection.execute(
            text(
                "SELECT k.conname,k.conrelid child_oid,k.confrelid parent_oid,k.conkey,k.confkey,"
                "cn.nspname child_schema,c.relname child_table,pn.nspname parent_schema,p.relname parent_table "
                "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace cn ON cn.oid=c.relnamespace "
                "JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace "
                "WHERE k.contype='f' AND cn.nspname='public' ORDER BY k.conname"
            )
        )
        .mappings()
        .all()
    )
    quote = connection.dialect.identifier_preparer.quote
    orphans = {}
    for fk in foreign_keys:
        attributes = {
            (r["attrelid"], r["attnum"]): r["attname"]
            for r in connection.execute(
                text(
                    "SELECT attrelid,attnum,attname FROM pg_attribute WHERE attrelid=ANY(:oids) AND attnum>0"
                ),
                {"oids": [fk["child_oid"], fk["parent_oid"]]},
            ).mappings()
        }
        child_cols = [quote(attributes[(fk["child_oid"], n)]) for n in fk["conkey"]]
        parent_cols = [quote(attributes[(fk["parent_oid"], n)]) for n in fk["confkey"]]
        child = quote(fk["child_schema"]) + "." + quote(fk["child_table"])
        parent = quote(fk["parent_schema"]) + "." + quote(fk["parent_table"])
        joins = " AND ".join(f"p.{p}=c.{c}" for c, p in zip(child_cols, parent_cols, strict=True))
        present = " AND ".join(f"c.{c} IS NOT NULL" for c in child_cols)
        count = connection.execute(
            text(
                f"SELECT count(*) FROM {child} c WHERE {present} "
                f"AND NOT EXISTS(SELECT 1 FROM {parent} p WHERE {joins})"
            )
        ).scalar_one()
        orphans[fk["conname"]] = count
    require(not any(orphans.values()), "Foreign-key orphan detected")
    invalid_indexes = connection.execute(
        text(
            "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
            "WHERE c.relnamespace='public'::regnamespace AND NOT i.indisvalid"
        )
    ).scalar_one()
    require(invalid_indexes == 0, "Invalid public index detected")
    return {
        "foreign_keys_checked": len(foreign_keys),
        "orphans": orphans,
        "invalid_indexes": invalid_indexes,
    }


def apply_batch(engine, targets, snapshot, journal_path, execution_id, revision, fail_after=None):
    """One atomic batch; fail_after is an isolated-test fault injection only."""
    journal_path = Path(journal_path)
    if journal_path.exists():
        existing = json.loads(journal_path.read_text(encoding="utf-8"))
        require(
            existing["execution_id"] == execution_id
            and existing["manifest_sha256"] == MANIFEST_SHA,
            "Journal identity differs",
        )
        require(
            existing["targets"] == [t["normalized_id"] for t in targets], "Journal targets differ"
        )
        if existing["status"] in {"APPLIED", "PREPARED"}:
            with engine.begin() as connection:
                lock_tables(connection)
                check_applied(connection, existing)
            existing["status"] = "APPLIED"
            save_journal(journal_path, existing)
            return {"applied": 0, "skipped": len(targets), "failed": 0}
        require(existing["status"] != "ROLLED_BACK", "Use a new execution after rollback")
        raise PreconditionError("Incomplete/failed intent: inspect its transaction before retrying")
    with engine.begin() as connection:
        lock_tables(connection)
        connection.execute(
            text("SELECT id FROM normalized_listings WHERE id=ANY(:ids) ORDER BY id FOR UPDATE"),
            {"ids": [t["normalized_id"] for t in targets]},
        )
        before, replacements = inspect_targets(connection, targets, snapshot)
        p_before = {r["id"]: r for r in before["parsed_listings"]}
        n_before = {r["id"]: r for r in before["normalized_listings"]}
        txid = str(connection.execute(text("SELECT txid_current()")).scalar_one())
        journal = {
            "execution_id": execution_id,
            "manifest_sha256": MANIFEST_SHA,
            "code_revision": revision,
            "batch": targets[0]["approval_batch"],
            "targets": [t["normalized_id"] for t in targets],
            "transaction_id": txid,
            "status": "INTENT",
            "before_images": before,
            "changes": [],
        }
        for target in targets:
            nid, pid = target["normalized_id"], target["parsed_listing_id"]
            replacement = replacements[nid]
            marker = {
                "execution_id": execution_id,
                "manifest_sha256": MANIFEST_SHA,
                "transaction_id": txid,
                "code_revision": revision,
                "normalized_id": nid,
            }
            extra = copy.deepcopy(p_before[pid]["extra_fields"] or {})
            extra.setdefault("provenance", {})["sale_price"] = replacement["provenance"]
            extra[MARKER] = marker
            journal["changes"].append(
                {
                    "normalized_id": nid,
                    "parsed_listing_id": pid,
                    "raw_id": target["raw_id"],
                    "old_prices": {k: n_before[nid][k] for k in ["sale_price", "price_per_sqm"]},
                    "old_parsed_price": p_before[pid]["sale_price"],
                    "old_extra_fields": p_before[pid]["extra_fields"],
                    "new_prices": {k: replacement[k] for k in ["sale_price", "price_per_sqm"]},
                    "new_provenance": replacement["provenance"],
                    "marker": marker,
                    "validation_additions": target["introduced_validation_codes"],
                }
            )
        save_journal(journal_path, journal)
        for index, change in enumerate(journal["changes"]):
            replacement = replacements[change["normalized_id"]]
            extra = copy.deepcopy(change["old_extra_fields"] or {})
            extra.setdefault("provenance", {})["sale_price"] = change["new_provenance"]
            extra[MARKER] = change["marker"]
            connection.execute(
                text(
                    "UPDATE parsed_listings SET sale_price=:price, extra_fields=CAST(:extra AS jsonb) WHERE id=:id"
                ),
                {
                    "id": change["parsed_listing_id"],
                    "price": change["new_prices"]["sale_price"],
                    "extra": json.dumps(extra),
                },
            )
            connection.execute(
                text(
                    "UPDATE normalized_listings SET sale_price=:sale_price,price_per_sqm=:price_per_sqm WHERE id=:id"
                ),
                {"id": change["normalized_id"], **change["new_prices"]},
            )
            if "missing_price" in change["validation_additions"]:
                # Existing exclusions are immutable. Add exactly the new issue.
                issue = next(
                    i
                    for i in ListingValidator().validate(schema(replacement["snapshot"])).issues
                    if i.code == "missing_price"
                )
                snapshot_value = {**replacement["snapshot"], MARKER: change["marker"]}
                invalid_id = connection.execute(
                    text(
                        "INSERT INTO invalid_listings (scrape_run_id,raw_listing_id,parsed_listing_id,normalized_listing_id,"
                        "stage,error_codes,field_errors,message,snapshot) VALUES (:run,:raw,:parsed,:normalized,"
                        "'VALIDATE',CAST(:codes AS jsonb),CAST(:errors AS jsonb),:message,CAST(:snapshot AS jsonb)) RETURNING id"
                    ),
                    {
                        "run": n_before[change["normalized_id"]]["scrape_run_id"],
                        "raw": change["raw_id"],
                        "parsed": change["parsed_listing_id"],
                        "normalized": change["normalized_id"],
                        "codes": json.dumps([issue.code]),
                        "errors": json.dumps({issue.field: issue.message}),
                        "message": issue.message,
                        "snapshot": json.dumps(snapshot_value),
                    },
                ).scalar_one()
                change["invalid_row"] = rows(connection, "invalid_listings", "id", [invalid_id])[0]
            if fail_after is not None and index + 1 == fail_after:
                raise RuntimeError("Isolated transaction failure injection")
        check_applied(connection, journal)
        journal["status"] = "PREPARED"
        save_journal(journal_path, journal)
    journal["status"] = "APPLIED"
    save_journal(journal_path, journal)
    return {"applied": len(targets), "skipped": 0, "failed": 0}


def rollback_batch(engine, journal_path):
    """Restore only owned columns/JSON keys, retaining later unrelated writes."""
    journal_path = Path(journal_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    require(journal["manifest_sha256"] == MANIFEST_SHA, "Rollback manifest differs")
    if journal["status"] == "ROLLED_BACK":
        return {"restored": 0, "skipped": len(journal["changes"])}
    require(journal["status"] in {"APPLIED", "PREPARED"}, "No committed batch to roll back")
    with engine.begin() as connection:
        lock_tables(connection)
        check_applied(connection, journal)
        for change in journal["changes"]:
            p = rows(connection, "parsed_listings", "id", [change["parsed_listing_id"]])[0]
            extra = copy.deepcopy(p["extra_fields"])
            del extra[MARKER]
            old = change["old_extra_fields"]
            prior_provenance = (old or {}).get("provenance", {})
            if "sale_price" in prior_provenance:
                extra["provenance"]["sale_price"] = prior_provenance["sale_price"]
            else:
                extra["provenance"].pop("sale_price", None)
            if "provenance" not in (old or {}) and not extra["provenance"]:
                del extra["provenance"]
            if old is None and not extra:
                extra = None
            connection.execute(
                text(
                    "UPDATE parsed_listings SET sale_price=:price,extra_fields=CAST(:extra AS jsonb) WHERE id=:id"
                ),
                {
                    "id": change["parsed_listing_id"],
                    "price": change["old_parsed_price"],
                    "extra": json.dumps(extra),
                },
            )
            connection.execute(
                text(
                    "UPDATE normalized_listings SET sale_price=:sale_price,price_per_sqm=:price_per_sqm WHERE id=:id"
                ),
                {"id": change["normalized_id"], **change["old_prices"]},
            )
            if change.get("invalid_row"):
                connection.execute(
                    text("DELETE FROM invalid_listings WHERE id=:id"),
                    {"id": change["invalid_row"]["id"]},
                )
        journal["rollback_transaction_id"] = str(
            connection.execute(text("SELECT txid_current()")).scalar_one()
        )
        # A recovery intent is durable before the inverse transaction commits.
        journal["rollback_prepared"] = True
        save_journal(journal_path, journal)
    journal["status"] = "ROLLED_BACK"
    save_journal(journal_path, journal)
    return {"restored": len(journal["changes"]), "skipped": 0}
