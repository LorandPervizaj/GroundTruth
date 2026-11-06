"""Exercise actual SDK token audiences with a local transport, never Azure."""

import json
import time

import pytest

pytest.importorskip("azure.data.tables")
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.data.tables import TableClient

from groundtruth.config import Settings
from groundtruth.services import table_submissions
from groundtruth.startup import validate_production_settings


class Reply(HttpResponse):
    def __init__(self, request):
        super().__init__(request, None)
        self.status_code = 200
        self.headers = {"Content-Type": "application/json"}
        self.content_type = "application/json"

    def body(self):
        return json.dumps(
            {"PartitionKey": "_health", "RowKey": "schema-v1", "SchemaVersion": 1}
        ).encode()


class Transport(HttpTransport):
    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        return Reply(request)


class Credential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        self.scopes.extend(scopes)
        return AccessToken("synthetic-token", int(time.time()) + 3600)


@pytest.mark.parametrize(
    ("endpoint", "scope"),
    [
        ("https://example.table.core.windows.net", "https://storage.azure.com/.default"),
        ("https://example.table.cosmos.azure.com", "https://cosmos.azure.com/.default"),
    ],
)
def test_managed_identity_sdk_uses_service_specific_audience(endpoint, scope, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        product_write_backend="azure_table",
        product_table_endpoint=endpoint,
        product_table_identity_client_id="synthetic-client",
        database_url="postgresql+psycopg://cache:synthetic@127.0.0.1/cache",
        health_check_token="synthetic-health-token-at-least-24-characters",
        api_require_lookup_cache=True,
        api_rate_limit_enabled=True,
        api_docs_enabled=False,
        product_table_connection_string=None,
    )
    validate_production_settings(settings)
    credential = Credential()
    seen = []

    def identity(*, client_id):
        seen.append(client_id)
        return credential

    def client(*args, **kwargs):
        return TableClient(*args, transport=Transport(), **kwargs)

    monkeypatch.setattr(table_submissions, "get_settings", lambda: settings)
    monkeypatch.setattr(table_submissions, "ManagedIdentityCredential", identity)
    monkeypatch.setattr(table_submissions, "TableClient", client)
    table_submissions.get_table_client.cache_clear()
    try:
        assert table_submissions.active_store().healthy()
        assert credential.scopes == [scope] and seen == ["synthetic-client"]
    finally:
        table_submissions.get_table_client.cache_clear()


def test_production_rejects_emulator_keys_before_network(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        product_write_backend="azure_table",
        product_table_endpoint="https://example.table.core.windows.net",
        product_table_connection_string="UseDevelopmentStorage=true",
    )
    monkeypatch.setattr(table_submissions, "get_settings", lambda: settings)
    table_submissions.get_table_client.cache_clear()
    with pytest.raises(ValueError):
        table_submissions.get_table_client()
    with pytest.raises(SystemExit):
        validate_production_settings(settings)


@pytest.mark.parametrize("backend", ["database", "jsonl"])
def test_production_never_accepts_ephemeral_authoritative_backend(backend):
    settings = Settings(
        _env_file=None,
        app_env="production",
        product_write_backend=backend,
        database_url="postgresql+psycopg://cache:synthetic@127.0.0.1/cache",
        health_check_token="synthetic-health-token-at-least-24-characters",
        api_require_lookup_cache=True,
        api_rate_limit_enabled=True,
        api_docs_enabled=False,
    )
    with pytest.raises(SystemExit, match="authoritative submissions require Azure Table"):
        validate_production_settings(settings)
