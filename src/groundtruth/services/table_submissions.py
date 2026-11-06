"""Durable Azure Table submissions with an atomic rolling duplicate guard.

Canonical records are insert-only. A two-entity partition transaction commits the
record and its dedupe guard together; ETags serialize concurrent processes.
Never creates a table or falls back to local/SQL storage on failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from azure.core import MatchConditions
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.data.tables import TableClient, UpdateMode
from azure.identity import ManagedIdentityCredential

from groundtruth.config import get_settings


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(kind: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical({"kind": kind, "payload": payload}).encode()).hexdigest()


@lru_cache
def get_table_client() -> TableClient:
    settings = get_settings()
    options = {
        "retry_total": 2,
        "connection_timeout": 3,
        "read_timeout": 5,
        "logging_enable": False,
    }
    # azure-core HTTP INFO logs otherwise duplicate every health check and can
    # expose request metadata. Keep failures observable through application errors.
    http_logger = logging.getLogger("groundtruth.table.http")
    http_logger.setLevel(logging.WARNING)
    options["logger"] = http_logger
    if settings.product_table_connection_string:
        if settings.app_env == "production":
            raise ValueError("Production requires managed identity, never emulator/account keys")
        # Explicit loopback emulator only; no accidental cloud use through test credentials.
        value = settings.product_table_connection_string
        endpoint = next(
            (x.split("=", 1)[1] for x in value.split(";") if x.startswith("TableEndpoint=")), ""
        )
        if urlparse(endpoint).hostname not in {"127.0.0.1", "localhost", "metrik-table-emulator"}:
            raise ValueError("Development connection strings must target the local emulator")
        return TableClient.from_connection_string(value, settings.product_table_name, **options)
    parsed = urlparse(settings.product_table_endpoint)
    if (
        parsed.scheme != "https"
        or not (parsed.hostname or "").endswith(
            (".table.core.windows.net", ".table.cosmos.azure.com", ".table.cosmosdb.azure.com")
        )
        or parsed.query
        or parsed.username
        or parsed.password
    ):
        raise ValueError("An HTTPS Azure Table endpoint without embedded credentials is required")
    credential = ManagedIdentityCredential(
        client_id=settings.product_table_identity_client_id or None
    )
    return TableClient(
        settings.product_table_endpoint,
        settings.product_table_name,
        credential=credential,
        **options,
    )


class SubmissionTable:
    def __init__(self, client: TableClient):
        self.client = client

    def healthy(self) -> bool:
        marker = self.client.get_entity("_health", "schema-v1")
        return marker.get("SchemaVersion") == 1

    def append(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        window_seconds: int,
        now: datetime | None = None,
    ) -> str:
        from groundtruth.services.product_submissions import DuplicateSubmission

        now = now or datetime.now(UTC)
        if not kind or any(c in kind for c in "/\\#?"):
            raise ValueError("Invalid submission kind")
        serialized = canonical({"ts": now.isoformat(), **payload})
        if len(serialized.encode("utf-16-le")) > 60_000:
            raise ValueError("Submission exceeds the storage property limit")
        key = "record-" + uuid.uuid4().hex
        record = {
            "PartitionKey": kind,
            "RowKey": key,
            "RecordType": "submission",
            "SchemaVersion": 1,
            "RecordId": "table:" + key[7:],
            "Kind": kind,
            "PayloadJson": serialized,
            "CreatedAt": now,
            "UpdatedAt": now,
        }
        if window_seconds <= 0:
            # Still deterministic within SDK retries of this invocation.
            self.client.create_entity(record)
            return record["RecordId"]
        guard_key = "dedupe-" + fingerprint(kind, payload)
        for _ in range(8):
            try:
                existing = self.client.get_entity(kind, guard_key)
            except ResourceNotFoundError:
                existing = None
            if existing is not None and existing["LastAcceptedAt"] >= now - timedelta(
                seconds=window_seconds
            ):
                raise DuplicateSubmission(guard_key)
            guard = {
                "PartitionKey": kind,
                "RowKey": guard_key,
                "RecordType": "dedupe",
                "SchemaVersion": 1,
                "LastAcceptedAt": now,
                "RecordId": record["RecordId"],
            }
            mutation = (
                ("create", guard)
                if existing is None
                else (
                    "update",
                    guard,
                    {
                        "mode": UpdateMode.REPLACE,
                        "etag": existing.metadata["etag"],
                        "match_condition": MatchConditions.IfNotModified,
                    },
                )
            )
            try:
                self.client.submit_transaction([mutation, ("create", record)])
                return record["RecordId"]
            except HttpResponseError as error:
                if error.status_code not in {409, 412}:
                    raise
                # A simultaneous commit, expired-guard ETag conflict or lost reply:
                # reread authoritative state rather than creating a second record.
        raise RuntimeError("Concurrent submission contention; retry safely")

    def records(self, *, kind: str | None = None, since: datetime | None = None) -> list[dict]:
        filters = ["RecordType eq 'submission'"]
        parameters = {}
        if kind is not None:
            filters.append("PartitionKey eq @kind")
            parameters["kind"] = kind
        if since is not None:
            filters.append("CreatedAt ge @since")
            parameters["since"] = since
        return list(self.client.query_entities(" and ".join(filters), parameters=parameters))

    def import_legacy(self, rows: list[dict]) -> None:
        """Offline/frozen-source import: never overwrites or collapses canonical records."""
        for row in rows:
            kind = row["kind"]
            legacy_id = int(row["id"])
            record = {
                "PartitionKey": kind,
                "RowKey": f"legacy-{legacy_id:020d}",
                "RecordType": "submission",
                "SchemaVersion": 1,
                "RecordId": f"pg:metrik:{legacy_id}",
                "LegacyId": legacy_id,
                "Kind": kind,
                "PayloadJson": canonical(row["payload"]),
                "CreatedAt": row["created_at"],
                "UpdatedAt": row["updated_at"],
            }
            try:
                self.client.create_entity(record)
            except HttpResponseError as error:
                if error.status_code != 409:
                    raise
                existing = self.client.get_entity(kind, record["RowKey"])
                if any(existing.get(k) != v for k, v in record.items()):
                    raise ValueError("Conflicting legacy record; refusing overwrite") from None
            payload = {k: v for k, v in row["payload"].items() if k != "ts"}
            guard_key = "dedupe-" + fingerprint(kind, payload)
            try:
                old = self.client.get_entity(kind, guard_key)
            except ResourceNotFoundError:
                old = None
            if old is not None and old["LastAcceptedAt"] >= row["created_at"]:
                continue
            guard = {
                "PartitionKey": kind,
                "RowKey": guard_key,
                "RecordType": "dedupe",
                "SchemaVersion": 1,
                "LastAcceptedAt": row["created_at"],
                "RecordId": record["RecordId"],
            }
            if old is None:
                self.client.create_entity(guard)
            else:
                self.client.update_entity(
                    guard,
                    mode=UpdateMode.REPLACE,
                    etag=old.metadata["etag"],
                    match_condition=MatchConditions.IfNotModified,
                )


def active_store() -> SubmissionTable:
    return SubmissionTable(get_table_client())
