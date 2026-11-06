"""Offline Stage A contracts. All cloud operations below are simulated."""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from groundtruth.automation import staging
from groundtruth.automation.deployment import (
    Approval,
    Deployment,
    cache_guard,
    fingerprint,
    stable_state,
)
from groundtruth.automation.staging_fixture import build_context, generate, verify, write_json
from tests.test_deployment_safety import FakeAzure

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 6, tzinfo=UTC)


def test_synthetic_json_is_platform_independent(tmp_path):
    write_json(tmp_path / "fixture.json", {"synthetic": True})
    assert (tmp_path / "fixture.json").read_bytes() == b'{\n  "synthetic": true\n}\n'


def test_janitor_reads_only_its_group_without_directory_permissions(manifest, monkeypatch):
    import importlib.util

    monkeypatch.syspath_prepend(str(ROOT / "scripts/azure"))
    spec = importlib.util.spec_from_file_location(
        "stage_cli_scope_test", ROOT / "scripts/azure/staging.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    principal = "33333333-3333-3333-3333-333333333333"
    manifest["principals"] = {"janitor": principal}
    role_id = (
        manifest["resource_group_id"] + "/providers/Microsoft.Authorization/roleDefinitions/role"
    )
    calls = []

    def run(*args):
        calls.append(args)
        if "definition" in args:
            return json.dumps(
                [
                    {
                        "id": role_id,
                        "permissions": [
                            {"actions": module.JANITOR_ACTIONS, "dataActions": [], "notActions": []}
                        ],
                    }
                ]
            )
        return json.dumps(
            [
                {
                    "principalId": principal,
                    "scope": manifest["resource_group_id"],
                    "roleDefinitionId": role_id,
                }
            ]
        )

    monkeypatch.setattr(module, "run", run)
    assert module.CleanupAzure(manifest).scope() == manifest["resource_group_id"]
    assert all(args[args.index("--scope") + 1] == manifest["resource_group_id"] for args in calls)
    assert "--assignee" not in calls[0] and "--all" not in calls[0]


@pytest.fixture
def manifest():
    cache = json.loads((ROOT / "deploy/production-policy.json").read_text())["cache_expected"]
    return staging.prepare(
        "20261106-1234abcd",
        "a" * 40,
        "acrstg202611061234abcd.azurecr.io/synthetic@sha256:" + "1" * 64,
        "docker.io/library/postgres@sha256:" + "2" * 64,
        "8.8.8.8/32",
        now=NOW,
        guard_source=(ROOT / "scripts/azure/cache_guard.template.py.txt").read_text(),
        cache_expected=cache,
        source_tree="b" * 40,
        baseline_image="acrstg202611061234abcd.azurecr.io/synthetic@sha256:" + "3" * 64,
    )


def evidence(m):
    return {
        "subscription": staging.SUBSCRIPTION,
        "providers_registered": True,
        "quota_vcpu_available": 3,
        "janitor": {
            "default_branch_installed": True,
            "workflow_active": True,
            "test_run_conclusion": "success",
            "interval_minutes": 15,
            "manifest_sha256": fingerprint(m),
        },
        "cleanup_scope": m["resource_group_id"],
        "cleanup_permissions_verified": True,
        "runtime_table_scope": m["table_id"] + "/tableServices/default/tables/StageSubmissions",
        "deploy_scope": m["app_id"],
        "production_access": False,
        "runtime_principal": "11111111-1111-1111-1111-111111111111",
        "deploy_principal": "22222222-2222-2222-2222-222222222222",
        "cleanup_principal": "33333333-3333-3333-3333-333333333333",
        "pricing": {
            "checked_at": NOW.isoformat(),
            "currency": "USD",
            "cpu_second": 0.000024,
            "gib_second": 0.000003,
            "registry_day": 0.1666,
            "table_gb_month": 0.045,
            "table_10k": 0.00036,
            "requests_million": 0.4,
            "egress_gb": 0.1,
        },
    }


def test_fixture_is_deterministic_and_passes_real_release_verifier(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    assert generate(a, "a" * 40) == generate(b, "a" * 40)
    assert (a / "synthetic-inventory.json").read_bytes() == (
        b / "synthetic-inventory.json"
    ).read_bytes()
    from groundtruth import release

    monkeypatch.setattr(release, "lookup_cache_dir", lambda: a / "reports/generated/lookup_cache")
    monkeypatch.setattr(release, "DEFAULT_ANNUAL_REPORT_PATH", a / "data/api/annual_report.json")
    monkeypatch.setattr(release, "RENT_YIELD_CACHE", a / "data/api/rent_yield.json")
    assert len(release.verify_release_artifacts()) == 3
    expected = json.loads((a / "synthetic/expected.json").read_text())
    assert expected["gross_yield_pct"] == 6 and expected["active_listings"] == 24


@pytest.mark.parametrize("kind", ["checksum", "manifest", "production", "extra"])
def test_fixture_rejects_tampering(tmp_path, kind):
    generate(tmp_path, "a" * 40)
    if kind == "extra":
        write_json(tmp_path / "private.json", {"private": True})
    else:
        path = tmp_path / "reports/generated/lookup_cache/manifest.json"
        value = json.loads(path.read_text())
        if kind == "checksum":
            value["entry_count"] = 10
        if kind == "manifest":
            value["synthetic"] = False
        if kind == "production":
            value["production"] = "stmetrikbetalgy2mu"
        write_json(path, value)
        if kind != "checksum":
            from groundtruth.automation.staging_fixture import digest

            inventory = json.loads((tmp_path / "synthetic-inventory.json").read_text())
            inventory[path.relative_to(tmp_path).as_posix()] = digest(path)
            write_json(tmp_path / "synthetic-inventory.json", inventory)
    with pytest.raises(ValueError):
        verify(tmp_path)


def test_context_does_not_copy_live_data(tmp_path):
    import subprocess

    fixture, context = tmp_path / "fixture", tmp_path / "context"
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    generate(fixture, sha)
    inventory = build_context(ROOT, fixture, context)
    assert "data/api/annual_report.json" in inventory
    assert json.loads((context / "data/api/annual_report.json").read_text())["synthetic"]
    assert not (context / ".git").exists() and not (context / ".env").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("subscription", "foreign"),
        ("resource_group", "rg-metrik-beta-eus2"),
        ("table_endpoint", "https://stmetrikbetalgy2mu.table.core.windows.net"),
        ("image", "registry.example/synthetic:latest"),
        ("source_sha", "short"),
        ("guard_source", "print('unsafe')"),
        ("region", "westus"),
        ("ingress_cidr", "0.0.0.0/0"),
        ("backend", "database"),
    ],
)
def test_scope_and_identity_fail_closed(manifest, field, value):
    manifest[field] = value
    with pytest.raises(ValueError):
        staging.validate(manifest, now=NOW)


def test_default_preflight_denies_and_approved_preflight_costs(manifest):
    with pytest.raises(ValueError, match="approvals"):
        staging.preflight(manifest, evidence(manifest), now=NOW)
    manifest["approval"] = dict.fromkeys(manifest["approval"], True)
    result = staging.preflight(manifest, evidence(manifest), now=NOW)
    assert result["four_hour_estimate_usd"] < 2
    assert result["maximum_hourly_compute_usd"] == pytest.approx(0.324)


@pytest.mark.parametrize(
    "fault", ["janitor", "permissions", "price", "quota", "principal", "budget", "cpu", "expiry"]
)
def test_incomplete_or_costly_preflight_denies(manifest, fault):
    manifest["approval"] = dict.fromkeys(manifest["approval"], True)
    e = evidence(manifest)
    if fault == "janitor":
        e["janitor"]["default_branch_installed"] = False
    if fault == "permissions":
        e["cleanup_permissions_verified"] = False
    if fault == "price":
        e["pricing"]["cpu_second"] *= 2
    if fault == "quota":
        e["quota_vcpu_available"] = 2
    if fault == "principal":
        e["runtime_principal"] = staging.PRODUCTION_PRINCIPAL
    if fault == "budget":
        manifest["limits"]["budget_usd"] = 4
    if fault == "cpu":
        manifest["limits"]["cpu"] = 2
    if fault == "expiry":
        manifest["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        staging.preflight(manifest, e, now=NOW)


class CleanupCloud:
    def __init__(self, m):
        self.m = m
        self.deleted = False
        self.stuck = False
        self.tags = {
            "purpose": m["purpose"],
            "runId": m["run_id"],
            "owner": m["owner"],
            "expiresAt": m["expires_at"],
        }

    def subscription(self):
        return self.m["subscription"]

    def scope(self):
        return self.m["resource_group_id"]

    def group(self, target):
        return None if self.deleted else {"id": target, "tags": self.tags}

    def delete(self, target):
        self.deleted = not self.stuck

    def remaining(self, target):
        return [] if self.deleted else ["survivor"]


def test_expired_cleanup_is_idempotent_and_verifies_absence(manifest):
    cloud = CleanupCloud(manifest)
    for _ in range(2):
        assert (
            staging.cleanup(manifest, cloud, now=NOW + timedelta(hours=3))["outcome"]
            == "verified_absent"
        )


def test_janitor_installation_can_verify_scope_without_deletion(manifest):
    cloud = CleanupCloud(manifest)
    assert (
        staging.cleanup(manifest, cloud, now=NOW, verify_only=True)["outcome"]
        == "scope_verified_no_mutation"
    )
    assert cloud.deleted is False


@pytest.mark.parametrize("fault", ["unexpired", "ownership", "partial", "wrong_id"])
def test_janitor_refuses_unsafe_or_incomplete_cleanup(manifest, fault):
    cloud = CleanupCloud(manifest)
    if fault == "ownership":
        cloud.tags["runId"] = "foreign"
    if fault == "partial":
        cloud.stuck = True
    if fault == "wrong_id":
        manifest["resource_group_id"] += "-other"
    with pytest.raises(ValueError):
        staging.cleanup(
            manifest, cloud, now=NOW if fault == "unexpired" else NOW + timedelta(hours=3)
        )


def staging_cloud(m):
    policy = copy.deepcopy(m)
    cloud = FakeAzure(policy)
    old_a, old_b = m["app_name"] + "--baseline-a", m["app_name"] + "--baseline-b"
    old = cloud.rows.pop("ca-metrik-api--old")
    old["name"] = old_a
    old["properties"]["fqdn"] = old_a + ".example.com"
    template = old["properties"]["template"]
    api = template["containers"][0]
    api["image"] = m["image"].replace("1" * 64, "3" * 64)
    api["command"] = cache_guard(m, old_a)
    api["env"].append({"name": "PRODUCT_TABLE_ENDPOINT", "value": m["table_endpoint"]})
    cloud.rows[old_a] = old
    cloud.rows[old_b] = copy.deepcopy(old)
    cloud.rows[old_b]["name"] = old_b
    cloud.rows[old_b]["properties"]["fqdn"] = old_b + ".example.com"
    cloud.rows[old_b]["properties"]["template"]["containers"][0]["command"] = cache_guard(m, old_b)
    cloud.value["properties"]["configuration"]["ingress"] = {
        "fqdn": m["app_name"] + ".example.com",
        "traffic": [{"revisionName": old_a, "weight": 70}, {"revisionName": old_b, "weight": 30}],
    }
    original_deploy = cloud.deploy

    def deploy(t):
        original_deploy(t)
        cloud.rows[m["candidate_revision"]] = cloud.rows.pop("ca-metrik-api--new")
        cloud.rows[m["candidate_revision"]]["properties"]["fqdn"] = (
            m["candidate_revision"] + ".example.com"
        )

    cloud.deploy = deploy
    before = stable_state(cloud.app(), cloud.revisions())
    policy = staging.controller_policy(m, before)
    approval = Approval(
        m["source_sha"],
        "b" * 40,
        "c" * 40,
        "d" * 40,
        "e" * 40,
        m["release_id"],
        "f" * 64,
        fingerprint(before),
    )
    cloud.labels = {
        "org.opencontainers.image.revision": approval.serving_sha,
        "io.metrik.data-release-id": approval.release_id,
        "io.metrik.data-source-sha": approval.data_source_sha,
        "io.metrik.bundle-sha256": approval.bundle_sha256,
    }
    return cloud, policy, approval, before


def test_real_controller_candidate_promotion_and_checkpoint_recovery(manifest, tmp_path):
    cloud, policy, approval, before = staging_cloud(manifest)
    path = tmp_path / "receipt.json"
    controller = Deployment(
        cloud, policy, approval, checkpoint=lambda r: staging.checkpoint(path, r)
    )
    receipt = controller.apply(
        manifest["image"],
        manifest["candidate_revision"],
        cache_guard(policy, manifest["candidate_revision"]),
        promote=False,
    )
    assert receipt["outcome"] == "candidate_verified_zero_traffic"
    assert stable_state(cloud.app(), cloud.revisions())["traffic"] == before["traffic"]
    resumed = Deployment(cloud, policy, approval)
    assert resumed.promote(json.loads(path.read_text()))["outcome"] == "verified"
    # Simulate process death after routing write, before a checkpoint can update.
    receipt = resumed.recover(json.loads(path.read_text()))
    assert receipt["rollback"] == "verified_exact_previous_allocation"
    assert stable_state(cloud.app(), cloud.revisions())["traffic"] == before["traffic"]


def test_recovery_refuses_foreign_changes_and_tampered_checkpoint(manifest):
    cloud, policy, approval, before = staging_cloud(manifest)
    d = Deployment(cloud, policy, approval, checkpoint=lambda receipt: None)
    r = d.apply(
        manifest["image"],
        manifest["candidate_revision"],
        cache_guard(policy, manifest["candidate_revision"]),
        promote=False,
    )
    cloud.value["identity"] = {"type": "foreign"}
    assert d.recover(r)["rollback"] == "refused_foreign_state"
    with pytest.raises(ValueError):
        Deployment(cloud, policy, replace(approval, expected_state="0" * 64)).recover(r)


def test_preparation_has_no_cloud_side_effects(manifest):
    with patch("subprocess.run", side_effect=AssertionError("Cloud calls forbidden")):
        staging.validate(manifest, now=NOW)


def test_synthetic_release_serves_real_read_api_contracts(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from groundtruth.analytics import annual_export, valuation
    from groundtruth.api import routes_markets
    from groundtruth.api.app import app
    from groundtruth.config import get_settings
    from groundtruth.database import session
    from groundtruth.gazetteers import canonical
    from groundtruth.services import lookup_cache, rent_yield, search

    generate(tmp_path, "a" * 40)
    settings = get_settings()
    monkeypatch.setattr(settings, "reports_generated_dir", tmp_path / "reports/generated")
    monkeypatch.setattr(settings, "gazetteer_dir", tmp_path / "data/gazetteers")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_require_lookup_cache", True)
    for key, empty in (
        ("_memory", {}),
        ("_manifest", None),
        ("_listing_counts", {}),
        ("_markets", []),
        ("_neighborhood_options", []),
    ):
        monkeypatch.setattr(lookup_cache, key, empty)
    monkeypatch.setattr(valuation, "_comparables_cache", None)
    monkeypatch.setattr(
        annual_export, "DEFAULT_ANNUAL_REPORT_PATH", tmp_path / "data/api/annual_report.json"
    )
    monkeypatch.setattr(rent_yield, "RENT_YIELD_CACHE", tmp_path / "data/api/rent_yield.json")
    monkeypatch.setattr(routes_markets, "log_product_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(session, "get_session_factory", lambda: MagicMock)
    canonical._neighborhood_rows.cache_clear()
    search._load_aliases.cache_clear()
    app.dependency_overrides[session.get_session] = lambda: MagicMock()
    try:
        assert lookup_cache.load_lookup_cache_from_disk() == 2
        client = TestClient(app)
        from groundtruth.automation.deployment_smoke import validate

        for path in (
            "/api/health",
            "/api/meta",
            "/api/search?q=ulpiana",
            "/api/markets",
            "/api/compare?neighborhoods=ulpiana,arberia",
            "/api/lookup/neighborhood/ulpiana",
            "/api/rent-yield",
            "/api/reports/annual_data",
        ):
            response = client.get(path)
            validate(
                path,
                response.status_code,
                response.json(),
                {"data_release_id": "synthetic-stage-" + "a" * 12},
            )
        assert client.get("/api/search?q=ulpiana").json()["results"][0]["slug"] == "ulpiana"
        assert client.get("/api/meta").json()["active_listings"] == 24
        assert client.get("/api/rent-yield").json()["rows"][0]["gross_yield_pct"] == 6
    finally:
        app.dependency_overrides.pop(session.get_session, None)
        canonical._neighborhood_rows.cache_clear()
        search._load_aliases.cache_clear()


@pytest.mark.parametrize("fault", ["key", "anonymous", "tls", "https", "principal", "scope"])
def test_storage_security_configuration_rejects_insecure_access(manifest, fault):
    from groundtruth.automation.staging_storage import data_scope, validate_security

    account = {
        "id": manifest["table_id"],
        "allowSharedKeyAccess": False,
        "allowBlobPublicAccess": False,
        "supportsHttpsTrafficOnly": True,
        "minimumTlsVersion": "TLS1_2",
        "publicNetworkAccess": "Enabled",
        "networkAcls": {"defaultAction": "Allow", "bypass": "None"},
    }
    runtime = "11111111-1111-1111-1111-111111111111"
    roles = [
        {
            "principalId": runtime,
            "scope": data_scope(manifest),
            "roleDefinitionName": "Storage Table Data Contributor",
        }
    ]
    assert validate_security(manifest, account, roles, runtime)["shared_key"] is False
    if fault == "key":
        account["allowSharedKeyAccess"] = True
    if fault == "anonymous":
        account["allowBlobPublicAccess"] = True
    if fault == "tls":
        account["minimumTlsVersion"] = "TLS1_0"
    if fault == "https":
        account["supportsHttpsTrafficOnly"] = False
    if fault == "principal":
        roles[0]["principalId"] = staging.PRODUCTION_PRINCIPAL
    if fault == "scope":
        roles[0]["scope"] = manifest["resource_group_id"]
    with pytest.raises(ValueError):
        validate_security(manifest, account, roles, runtime)


@pytest.mark.parametrize("bypass", ["unauthorized_identity", "shared_key", "anonymous", "http"])
def test_storage_authorization_negative_probe_requires_real_denial(manifest, bypass):
    from groundtruth.automation.staging_storage import authorization_probes

    expected = {
        "managed_identity": (200, ""),
        "unauthorized_identity": (403, "AuthorizationPermissionMismatch"),
        "shared_key": (403, "KeyBasedAuthenticationNotPermitted"),
        "anonymous": (403, "AuthenticationFailed"),
        "http": (400, "AccountRequiresHttps"),
    }
    assert authorization_probes(manifest, expected.__getitem__)["shared_key"] == "denied"
    expected[bypass] = (200, "")
    with pytest.raises(ValueError):
        authorization_probes(manifest, expected.__getitem__)


def test_cleanup_templates_are_inactive_and_default_off():
    import yaml

    for name in ("janitor", "primary-cleanup"):
        path = ROOT / f"deploy/staging/workflows/{name}.yml"
        assert not (ROOT / f".github/workflows/{name}.yml").exists()
        value = yaml.safe_load(path.read_text())
        job = value["jobs"]["cleanup"]
        assert "== 'true'" in job["if"]
        assert value["concurrency"]["cancel-in-progress"] is False
        assert "METRIK_AZURE" not in path.read_text()


def test_rendered_resources_enforce_storage_rbac_and_compute(manifest):
    from groundtruth.automation.staging_resources import (
        application,
        federation_plan,
        infrastructure,
    )
    from groundtruth.automation.staging_storage import authorization_plan, data_scope

    manifest.update(
        runtime_client_id="11111111-1111-1111-1111-111111111111",
        domain="synthetic.eastus2.azurecontainerapps.io",
    )
    resources = infrastructure(manifest)["resources"]
    storage = next(r for r in resources if r["type"] == "Microsoft.Storage/storageAccounts")
    assert storage["properties"]["allowSharedKeyAccess"] is False
    assert storage["properties"]["allowBlobPublicAccess"] is False
    assert storage["properties"]["minimumTlsVersion"] == "TLS1_2"
    assert storage["properties"]["supportsHttpsTrafficOnly"] is True
    assert storage["properties"]["networkAcls"]["defaultAction"] == "Allow"
    app = application(manifest)
    assert app["parameters"]["opsToken"]["type"] == "secureString"
    template = app["resources"][0]["properties"]["template"]
    assert sum(c["resources"]["cpu"] for c in template["containers"]) == 1
    assert template["scale"]["maxReplicas"] == 1
    assert template["containers"][0]["image"] == manifest["baseline_image"]
    principals = {
        "runtime": "11111111-1111-1111-1111-111111111111",
        "deploy": "22222222-2222-2222-2222-222222222222",
        "janitor": "33333333-3333-3333-3333-333333333333",
    }
    roles = authorization_plan(manifest, principals)
    assert roles[0]["scope"] == data_scope(manifest)
    assert all("azure-beta" not in s for s in federation_plan(manifest)["deploy"]["subjects"])


def test_recovery_rejects_tampered_clone_even_if_staged_state_is_altered(manifest):
    cloud, policy, approval, _ = staging_cloud(manifest)
    d = Deployment(cloud, policy, approval, checkpoint=lambda receipt: None)
    r = json.loads(
        json.dumps(
            d.apply(
                manifest["image"],
                manifest["candidate_revision"],
                cache_guard(policy, manifest["candidate_revision"]),
                promote=False,
            )
        )
    )
    r["recovery"]["template"]["containers"][0]["env"].append(
        {"name": "FOREIGN", "value": "injected"}
    )
    r["recovery"]["staged"]["app_template"] = r["recovery"]["template"]
    with pytest.raises(ValueError, match="clone contract"):
        d.recover(r)
