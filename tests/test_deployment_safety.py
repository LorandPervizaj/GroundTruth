"""Behavioral deployment regressions; all Azure/HTTP writes are simulated."""

import copy
import json
from pathlib import Path

import pytest

from groundtruth.automation.deployment import (
    Approval,
    Deployment,
    cache_guard,
    fingerprint,
    stable_state,
)
from groundtruth.automation.deployment_smoke import PAGES, READS, validate

ROOT = Path(__file__).resolve().parents[1]
OLD = "ca-metrik-api--old"
NEW = "ca-metrik-api--new"
OLD_IMAGE = "registry.example/metrik@sha256:" + "1" * 64
NEW_IMAGE = "registry.example/metrik@sha256:" + "2" * 64


class FakeAzure:
    def __init__(self, policy):
        self.value = {
            "id": policy["app_id"],
            "identity": {"type": "UserAssigned"},
            "properties": {
                "environmentId": "environment",
                "configuration": {
                    "activeRevisionsMode": "Multiple",
                    "ingress": {
                        "fqdn": "ca-metrik-api.example.com",
                        "traffic": [{"revisionName": OLD, "weight": 100}],
                    },
                },
            },
        }
        template = {
            "containers": [
                {
                    "name": "metrik-api",
                    "image": OLD_IMAGE,
                    "command": ["reviewed-old-guard"],
                    "env": [
                        {"name": "PRODUCT_WRITE_BACKEND", "value": "azure_table"},
                        {"name": "RUN_MIGRATIONS_ON_START", "value": "false"},
                        {"name": "API_REQUIRE_LOOKUP_CACHE", "value": "true"},
                        {"name": "TRUSTED_HOSTS", "value": "ca-metrik-api.example.com,localhost"},
                    ],
                }
            ],
            "volumes": policy["volumes"],
        }
        self.rows = {
            OLD: {
                "name": OLD,
                "properties": {
                    "active": True,
                    "healthState": "Healthy",
                    "template": template,
                    "fqdn": OLD + ".example.com",
                },
            }
        }
        self.labels = {}
        self.calls = []
        self.on_smoke = lambda url: None
        self.ignore_traffic = False
        self.break_reads = False

    def app(self):
        if self.break_reads:
            raise RuntimeError("Azure unavailable")
        return copy.deepcopy(self.value)

    def revisions(self):
        return copy.deepcopy(self.rows)

    def inspect_image(self, image):
        return self.labels

    def deploy(self, template):
        self.calls.append(("deploy", copy.deepcopy(template)))
        self.value["properties"]["template"] = copy.deepcopy(template)  # latest is NOT serving
        self.rows[NEW] = {
            "name": NEW,
            "properties": {
                "active": True,
                "healthState": "Healthy",
                "template": copy.deepcopy(template),
                "fqdn": NEW + ".example.com",
            },
        }

    def wait_ready(self, name):
        return copy.deepcopy(self.rows[name])

    def smoke(self, url, expected):
        self.calls.append(("smoke", url))
        self.on_smoke(url)

    def previous_smoke(self, url, release):
        self.calls.append(("old_smoke", url, release))

    def set_traffic(self, value):
        self.calls.append(("traffic", copy.deepcopy(value)))
        if not self.ignore_traffic:
            self.value["properties"]["configuration"]["ingress"]["traffic"] = copy.deepcopy(value)

    def deactivate(self, revision):
        self.calls.append(("deactivate", revision))
        self.rows[revision]["properties"]["active"] = False


@pytest.fixture
def setup():
    policy = json.loads((ROOT / "deploy/production-policy.json").read_text())
    policy["guard_source"] = (ROOT / "scripts/azure/cache_guard.template.py.txt").read_text()
    policy["previous_guard_hashes"] = [fingerprint(["reviewed-old-guard"])]
    policy["compatible_previous_images"] = [OLD_IMAGE]
    policy["previous_releases"] = {OLD: "old-data"}
    cloud = FakeAzure(policy)
    approval = Approval(
        "a" * 40,
        "b" * 40,
        "c" * 40,
        "d" * 40,
        "e" * 40,
        "new-data",
        "f" * 64,
        fingerprint(stable_state(cloud.app(), cloud.revisions())),
    )
    cloud.labels = {
        "org.opencontainers.image.revision": approval.serving_sha,
        "io.metrik.data-release-id": approval.release_id,
        "io.metrik.data-source-sha": approval.data_source_sha,
        "io.metrik.bundle-sha256": approval.bundle_sha256,
    }
    return cloud, policy, approval


def execute(setup):
    cloud, policy, approval = setup
    deployment = Deployment(cloud, policy, approval)
    return deployment, lambda: deployment.apply(NEW_IMAGE, NEW, cache_guard(policy, NEW))


def test_candidate_validated_before_explicit_traffic_and_readback(setup):
    cloud, _, _ = setup
    d, apply = execute(setup)
    assert apply()["outcome"] == "verified"
    assert [x[0] for x in cloud.calls] == ["old_smoke", "deploy", "smoke", "traffic", "smoke"]
    assert cloud.calls[2][1] == "https://" + NEW + ".example.com"
    assert d.receipt["previous"][OLD]["image"] == OLD_IMAGE


def test_ready_new_release_without_routing_is_not_success(setup):
    cloud, _, _ = setup
    cloud.ignore_traffic = True
    d, apply = execute(setup)
    with pytest.raises(ValueError, match="state changed"):
        apply()
    assert d.receipt["outcome"] == "failed"
    assert d.receipt["rollback"] == "previous_traffic_unchanged"


def test_candidate_failure_never_changes_previous_traffic(setup):
    cloud, _, _ = setup
    cloud.on_smoke = lambda _: (_ for _ in ()).throw(ValueError("HTTP 500"))
    d, apply = execute(setup)
    with pytest.raises(ValueError, match="HTTP 500"):
        apply()
    assert not any(c[0] == "traffic" for c in cloud.calls)
    assert d.receipt["rollback"] == "previous_traffic_unchanged"


def test_failure_after_promotion_restores_exact_weighted_map(setup):
    cloud, policy, approval = setup
    other = "ca-metrik-api--other"
    cloud.rows[other] = copy.deepcopy(cloud.rows[OLD])
    cloud.rows[other]["name"] = other
    cloud.rows[other]["properties"]["fqdn"] = other + ".example.com"
    original = [{"revisionName": OLD, "weight": 35}, {"revisionName": other, "weight": 65}]
    cloud.value["properties"]["configuration"]["ingress"]["traffic"] = original
    policy["previous_releases"][other] = "old-data"
    setup = (
        cloud,
        policy,
        Approval(
            **{
                **vars(approval),
                "expected_state": fingerprint(stable_state(cloud.app(), cloud.revisions())),
            }
        ),
    )

    def smoke(url):
        if url == "https://ca-metrik-api.example.com":
            raise ValueError("public validation failed")

    cloud.on_smoke = smoke
    d, apply = execute(setup)
    with pytest.raises(ValueError):
        apply()
    assert d.receipt["rollback"] == "verified_exact_previous_allocation"
    assert [call for call in cloud.calls if call[0] == "traffic"][-1] == (
        "traffic",
        sorted(original, key=lambda t: t["revisionName"]),
    )
    assert d.receipt["previous_traffic"] == sorted(original, key=lambda t: t["revisionName"])


@pytest.mark.parametrize("when", ["before", "after"])
def test_out_of_band_traffic_change_refuses_stale_promotion_or_rollback(setup, when):
    cloud, _, _ = setup
    original = copy.deepcopy(cloud.rows[OLD])

    def change(url):
        if ("--new" in url) == (when == "before"):
            cloud.rows["ca-metrik-api--foreign"] = original
            cloud.value["properties"]["configuration"]["ingress"]["traffic"] = [
                {"revisionName": "ca-metrik-api--foreign", "weight": 100}
            ]
            if when == "after":
                raise ValueError("public error after operator update")

    cloud.on_smoke = change
    d, apply = execute(setup)
    with pytest.raises(ValueError):
        apply()
    assert d.receipt["rollback"] == "refused_foreign_state"
    assert len([c for c in cloud.calls if c[0] == "traffic"]) == (0 if when == "before" else 1)


@pytest.mark.parametrize("kind", ["backend", "guard", "digest", "fingerprint", "cli"])
def test_incompatible_or_unreadable_baseline_fails_before_mutation(setup, kind):
    cloud, _, _ = setup
    if kind == "backend":
        cloud.rows[OLD]["properties"]["template"]["containers"][0]["env"][0]["value"] = "database"
    elif kind == "guard":
        cloud.rows[OLD]["properties"]["template"]["containers"][0]["command"] = [
            "unconditional-alembic"
        ]
    elif kind == "digest":
        cloud.labels["org.opencontainers.image.revision"] = "0" * 40
    elif kind == "fingerprint":
        cloud.value["identity"]["type"] = "Other"
    else:
        cloud.break_reads = True
    _, apply = execute(setup)
    with pytest.raises((ValueError, RuntimeError)):
        apply()
    assert cloud.calls == []


def test_rollback_readback_failure_is_not_claimed_success(setup):
    cloud, _, _ = setup

    def fail(url):
        if url == "https://ca-metrik-api.example.com":
            cloud.break_reads = True
            raise RuntimeError("transport lost")

    cloud.on_smoke = fail
    d, apply = execute(setup)
    with pytest.raises(RuntimeError):
        apply()
    assert d.receipt["rollback"] == "unverified_no_further_mutation"


def test_unhealthy_promoted_candidate_can_roll_back_to_healthy_previous(setup):
    cloud, _, _ = setup

    def fail(url):
        if url == "https://ca-metrik-api.example.com":
            cloud.rows[NEW]["properties"]["healthState"] = "Unhealthy"
            raise ValueError("candidate became unhealthy")

    cloud.on_smoke = fail
    d, apply = execute(setup)
    with pytest.raises(ValueError, match="unhealthy"):
        apply()
    assert d.receipt["rollback"] == "verified_exact_previous_allocation"


@pytest.mark.parametrize("path", READS + PAGES)
def test_every_critical_http_failure_fails_gate(path):
    with pytest.raises(ValueError, match="Critical read"):
        validate(path, 500, {}, {"data_release_id": "expected"})


def test_unrelated_metadata_match_cannot_pass():
    with pytest.raises(ValueError, match="exact release_id"):
        validate(
            "/api/meta", 200, {"release_id": "old", "unrelated": "new"}, {"data_release_id": "new"}
        )


@pytest.mark.parametrize(
    "field", ["revision", "serving_source_sha", "image", "backend", "cache_guard_verified", "ok"]
)
def test_same_release_from_wrong_worker_or_backend_rejected(field):
    expected = {
        "revision": NEW,
        "serving_source_sha": "a" * 40,
        "image": NEW_IMAGE,
        "data_release_id": "same-data",
    }
    body = {
        **expected,
        "backend": "azure_table",
        "ok": True,
        "cache_guard_verified": True,
        "artifacts_verified": True,
    }
    body[field] = False if isinstance(body[field], bool) else "wrong"
    with pytest.raises(ValueError):
        validate("/api/deployment", 200, body, expected)


def test_malformed_json_schema_rejected():
    with pytest.raises(ValueError, match="Malformed"):
        validate("/api/meta", 200, "not json", {"data_release_id": "new"})


def test_bad_probe_credential_stops_before_search_telemetry():
    from groundtruth.automation.deployment_smoke import smoke

    calls = []

    def fetch(path):
        calls.append(path)
        return 403, {"detail": "forbidden"}

    with pytest.raises(ValueError):
        smoke("https://candidate.example.com", {}, token="incorrect", fetch=fetch)
    assert calls == ["/api/deployment"]


def test_foreign_template_update_without_traffic_change_is_detected(setup):
    cloud, _, _ = setup

    def update(_):
        cloud.value["properties"]["template"]["containers"][0]["image"] = (
            "registry.example/foreign@sha256:" + "3" * 64
        )

    cloud.on_smoke = update
    d, apply = execute(setup)
    with pytest.raises(ValueError, match="state changed"):
        apply()
    assert d.receipt["rollback"] == "refused_foreign_state"
    assert not any(c[0] == "traffic" for c in cloud.calls)
