"""Stage A scope, preflight and cleanup controls; preparation never calls Azure."""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from groundtruth.automation.deployment import DIGEST, SHA, cache_guard, fingerprint, require
from groundtruth.automation.staging_fixture import no_production

SUBSCRIPTION = "c73c2fd1-9b7f-4221-a868-757128f2e416"
STAGING_REGION = "northcentralus"
PRODUCTION_PRINCIPAL = "f469a82e-9324-4b6f-a92e-498eb4b5acf2"
PRODUCTION_CLIENT = "89d6c8e2-3de1-46b5-8ce3-df6212487ed6"
GUARD_SHA = "cb53f92225872378adb456a54e8c62ecda8ec86d84a3ed78116b935c475b66fb"
CACHE_SHA = "da1ed7beb75566fd9953a6b2faa271a67ed749c0ef14060cb1a658ea84b2c793"
STAGE_PREFIX = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-metrik-stage-"


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "UTC timestamp required")
    return parsed.astimezone(UTC)


def prepare(
    run_id: str,
    source_sha: str,
    image: str,
    sidecar_image: str,
    runner_cidr: str,
    *,
    now: datetime,
    guard_source: str,
    cache_expected: dict,
    source_tree: str,
    baseline_image: str,
) -> dict:
    require(bool(re.fullmatch(r"[0-9]{8}-[0-9a-f]{8}", run_id)), "Invalid staging run ID")
    require(bool(SHA.fullmatch(source_sha)), "Full source SHA required")
    group = "rg-metrik-stage-" + run_id
    stem = run_id.replace("-", "")
    registry, table = "acrstg" + stem, "ststg" + stem
    root = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{group}"
    app = "ca-stage-" + run_id
    value = {
        "schema": 1,
        "run_id": run_id,
        "subscription": SUBSCRIPTION,
        "region": STAGING_REGION,
        "resource_group": group,
        "resource_group_id": root,
        "owner": "LorandPervizaj",
        "purpose": "metrik-stage-a",
        "created_at": now.astimezone(UTC).isoformat(),
        "expires_at": (now + timedelta(hours=2)).astimezone(UTC).isoformat(),
        "cleanup_deadline": (now + timedelta(hours=4)).astimezone(UTC).isoformat(),
        "source_sha": source_sha,
        "source_tree": source_tree,
        "release_id": "synthetic-stage-" + source_sha[:12],
        "image": image,
        "baseline_image": baseline_image,
        "sidecar_image": sidecar_image,
        "registry": registry,
        "table": table,
        "table_endpoint": f"https://{table}.table.core.windows.net",
        "storage_network_mode": "public-https-managed-identity-only",
        "app_name": app,
        "app_id": root + "/providers/Microsoft.App/containerApps/" + app,
        "environment_id": root + "/providers/Microsoft.App/managedEnvironments/cae-" + run_id,
        "registry_id": root + "/providers/Microsoft.ContainerRegistry/registries/" + registry,
        "table_id": root + "/providers/Microsoft.Storage/storageAccounts/" + table,
        "runtime_identity_id": root
        + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/runtime-"
        + run_id,
        "deploy_identity_id": root
        + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/deploy-"
        + run_id,
        "candidate_revision": app + "--candidate",
        "ingress_cidr": runner_cidr,
        "limits": {
            "cpu": 1,
            "memory_gib": 2,
            "replicas_per_revision": 1,
            "active_revisions": 3,
            "test_minutes": 90,
            "storage_gb": 0.1,
            "transactions": 100000,
            "requests": 10000,
            "egress_gb": 0.1,
            "budget_usd": 3,
        },
        "features": {
            "workload": "Consumption",
            "registry_sku": "Basic",
            "storage_sku": "Standard_LRS",
            "log_destination": "none",
            "private_endpoint": False,
            "nat": False,
            "dedicated": False,
            "planned_maintenance": False,
        },
        "backend": "azure_table",
        "volumes": [{"name": "pgdata", "storageType": "EmptyDir"}],
        "guard_source": guard_source,
        "guard_template_sha256": hashlib.sha256(guard_source.encode()).hexdigest(),
        "cache_expected": cache_expected,
        "approval": {"spending": False, "provisioning": False, "janitor_installation": False},
    }
    # The forbidden source-cluster identifier is a guard denylist, never a target.
    validate(value, now=now)
    return value


def validate(m: dict, *, now: datetime, allow_expired=False) -> None:
    require(
        m.get("schema") == 1 and m.get("subscription") == SUBSCRIPTION,
        "Wrong staging subscription/schema",
    )
    require(bool(re.fullmatch(r"[0-9]{8}-[0-9a-f]{8}", m["run_id"])), "Invalid run identity")
    root = STAGE_PREFIX + m["run_id"]
    require(
        m["resource_group_id"] == root and m["resource_group"] == root.rsplit("/", 1)[1],
        "Wrong resource group",
    )
    require(
        m["region"] == STAGING_REGION
        and m["purpose"] == "metrik-stage-a"
        and m["owner"] == "LorandPervizaj",
        "Wrong region/ownership",
    )
    require(
        m["app_name"] == "ca-stage-" + m["run_id"]
        and m["app_id"] == root + "/providers/Microsoft.App/containerApps/" + m["app_name"],
        "Wrong staging app",
    )
    for field in (
        "environment_id",
        "registry_id",
        "table_id",
        "runtime_identity_id",
        "deploy_identity_id",
    ):
        require(
            m[field].startswith(root + "/providers/") and "/../" not in m[field],
            "Resource outside staging scope",
        )
    stem = m["run_id"].replace("-", "")
    require(
        m["registry"] == "acrstg" + stem and m["table"] == "ststg" + stem,
        "Wrong registry/Table identity",
    )
    require(
        m["registry_id"]
        == root + "/providers/Microsoft.ContainerRegistry/registries/" + m["registry"]
        and m["table_id"] == root + "/providers/Microsoft.Storage/storageAccounts/" + m["table"],
        "Wrong registry/Table resource",
    )
    require(
        m["table_endpoint"] == f"https://{m['table']}.table.core.windows.net",
        "Wrong Table endpoint",
    )
    require(
        m.get("storage_network_mode") == "public-https-managed-identity-only",
        "Unapproved storage network mode",
    )
    require(
        bool(DIGEST.fullmatch(m["image"]))
        and m["image"].startswith(m["registry"] + ".azurecr.io/synthetic@sha256:"),
        "Synthetic registry digest required",
    )
    require(
        bool(DIGEST.fullmatch(m["baseline_image"]))
        and m["baseline_image"].startswith(m["registry"] + ".azurecr.io/synthetic@sha256:")
        and m["baseline_image"] != m["image"],
        "Distinct synthetic baseline digest required",
    )
    require(
        bool(DIGEST.fullmatch(m["sidecar_image"]))
        and m["sidecar_image"].startswith("docker.io/library/postgres@sha256:"),
        "Pinned PostgreSQL sidecar required",
    )
    require(
        bool(SHA.fullmatch(m["source_sha"]))
        and bool(SHA.fullmatch(m["source_tree"]))
        and m["release_id"] == "synthetic-stage-" + m["source_sha"][:12]
        and m["candidate_revision"] == m["app_name"] + "--candidate",
        "Wrong source/revision",
    )
    network = ipaddress.ip_network(m["ingress_cidr"], strict=True)
    require(
        network.version == 4 and network.prefixlen == 32 and network.network_address.is_global,
        "One public runner IPv4 /32 required",
    )
    require(
        m["backend"] == "azure_table"
        and m["volumes"] == [{"name": "pgdata", "storageType": "EmptyDir"}],
        "Wrong backend/cache volume",
    )
    require(
        m["features"]
        == {
            "workload": "Consumption",
            "registry_sku": "Basic",
            "storage_sku": "Standard_LRS",
            "log_destination": "none",
            "private_endpoint": False,
            "nat": False,
            "dedicated": False,
            "planned_maintenance": False,
        },
        "Unapproved paid feature",
    )
    ceilings = {
        "cpu": 1,
        "memory_gib": 2,
        "replicas_per_revision": 1,
        "active_revisions": 3,
        "test_minutes": 90,
        "storage_gb": 0.1,
        "transactions": 100000,
        "requests": 10000,
        "egress_gb": 0.1,
        "budget_usd": 3,
    }
    require(
        set(m["limits"]) == set(ceilings)
        and all(
            type(m["limits"][k]) in (int, float) and 0 < m["limits"][k] <= limit
            for k, limit in ceilings.items()
        ),
        "Unapproved budget/resource limit",
    )
    start, expires, deadline = (utc(m[k]) for k in ("created_at", "expires_at", "cleanup_deadline"))
    require(
        start <= now
        and expires - start == timedelta(hours=2)
        and deadline - start == timedelta(hours=4),
        "Invalid run lifetime",
    )
    require(allow_expired or now < expires, "Run expired")
    scrub = {k: v for k, v in m.items() if k not in ("guard_source", "cache_expected")}
    no_production(scrub)
    for key in ("runtime_client_id", "cleanup_client_id"):
        if key in m:
            require(
                bool(re.fullmatch(r"[0-9a-f-]{36}", m[key]))
                and m[key] not in {PRODUCTION_CLIENT, PRODUCTION_PRINCIPAL},
                "Production/invalid bound identity",
            )
    require(
        hashlib.sha256(m["guard_source"].encode()).hexdigest()
        == m["guard_template_sha256"]
        == GUARD_SHA
        and fingerprint(m["cache_expected"]) == CACHE_SHA,
        "Invalid cache guard",
    )
    cache_guard(m, m["candidate_revision"])
    if "domain" in m:
        bound_endpoints(m)


def bound_endpoints(m: dict) -> dict:
    """Expected hosts are bound only to the approved new staging region."""
    require(m["region"] == STAGING_REGION, "Wrong staging endpoint region")
    domain = m.get("domain", "")
    require(
        bool(
            re.fullmatch(
                r"[a-z0-9][a-z0-9-]*\." + STAGING_REGION + r"\.azurecontainerapps\.io", domain
            )
        ),
        "Bound North Central US staging domain required",
    )
    return {
        "public": "https://" + m["app_name"] + "." + domain,
        "baseline_a": "https://" + m["app_name"] + "--baseline-a." + domain,
        "baseline_b": "https://" + m["app_name"] + "--baseline-b." + domain,
        "candidate": "https://" + m["candidate_revision"] + "." + domain,
        "table": m["table_endpoint"],
    }


def validate_image_region(m: dict, labels: dict) -> None:
    require(
        m["region"] == STAGING_REGION and labels.get("io.metrik.staging-region") == STAGING_REGION,
        "Synthetic image staging region differs",
    )


def preflight(m: dict, evidence: dict, *, now: datetime) -> dict:
    validate(m, now=now)
    cores = evidence.get("quota_vcpu_available")
    require(
        all(
            m["approval"].get(k) is True
            for k in ("spending", "provisioning", "janitor_installation")
        ),
        "External approvals missing",
    )
    require(
        evidence.get("subscription") == SUBSCRIPTION
        and evidence.get("region") == STAGING_REGION
        and evidence.get("quota_environment_id") == m["environment_id"]
        and evidence.get("providers_registered")
        and type(cores) in (int, float)
        and cores >= 3,
        "Subscription/provider/quota preflight failed",
    )
    janitor = evidence.get("janitor", {})
    require(
        janitor.get("default_branch_installed") is True
        and janitor.get("workflow_active") is True
        and janitor.get("test_run_conclusion") == "success"
        and janitor.get("interval_minutes") == 15
        and janitor.get("manifest_sha256") == fingerprint(m),
        "Working independent janitor required",
    )
    require(
        evidence.get("cleanup_scope") == m["resource_group_id"]
        and evidence.get("cleanup_permissions_verified") is True,
        "Cleanup permission missing",
    )
    require(
        evidence.get("runtime_table_scope")
        == m["table_id"] + "/tableServices/default/tables/StageSubmissions"
        and evidence.get("deploy_scope") == m["app_id"]
        and evidence.get("production_access") is False,
        "Staging-only RBAC required",
    )
    for key in ("runtime_principal", "deploy_principal", "cleanup_principal"):
        require(
            bool(re.fullmatch(r"[0-9a-f-]{36}", evidence.get(key, "")))
            and evidence[key] not in {PRODUCTION_PRINCIPAL, PRODUCTION_CLIENT},
            "New staging-only principal required",
        )
    require(
        len({evidence[k] for k in ("runtime_principal", "deploy_principal", "cleanup_principal")})
        == 3,
        "Distinct runtime/deploy/cleanup principals required",
    )
    price = evidence.get("pricing", {})
    age = now - utc(price.get("checked_at", "1900-01-01T00:00:00Z"))
    require(
        timedelta(0) <= age <= timedelta(hours=24) and price.get("currency") == "USD",
        "Fresh USD retail quote required",
    )
    bounds = {
        "cpu_second": 0.000024,
        "gib_second": 0.000003,
        "registry_day": 0.1666,
        "table_gb_month": 0.045,
        "table_10k": 0.00036,
        "requests_million": 0.4,
        "egress_gb": 0.1,
    }
    require(
        all(
            type(price.get(k)) in (int, float) and base <= price[k] <= base * 1.01
            for k, base in bounds.items()
        ),
        "Retail price changed; approval required",
    )
    hourly = (price["cpu_second"] + 2 * price["gib_second"]) * 3600 * 3
    maximum = hourly * 4 + price["registry_day"] + 0.01 + 0.004 + 0.004
    require(maximum <= 2 and maximum < m["limits"]["budget_usd"], "Cost exceeds approved plan")
    return {
        "preflight": "passed",
        "maximum_hourly_compute_usd": hourly,
        "four_hour_estimate_usd": maximum,
        "manifest_sha256": fingerprint(m),
    }


def controller_policy(m: dict, before: dict) -> dict:
    """Bind existing deployment controller checks to the staging baseline, never production."""
    require(before["global"]["id"] == m["app_id"], "Wrong captured app")
    policy = copy.deepcopy(m)
    policy["previous_guard_hashes"] = []
    policy["compatible_previous_images"] = []
    policy["previous_releases"] = {}
    for revision, template in before["serving"].items():
        require(revision.startswith(m["app_name"] + "--"), "Wrong previous revision")
        api = next(c for c in template["containers"] if c["name"] == "metrik-api")
        require(
            api["image"].startswith(m["registry"] + ".azurecr.io/synthetic@sha256:"),
            "Wrong previous registry",
        )
        require(api["command"] == cache_guard(m, revision), "Unreviewed previous guard")
        values = {x["name"]: x for x in api["env"]}
        require(
            values["PRODUCT_WRITE_BACKEND"]["value"] == "azure_table"
            and values["PRODUCT_TABLE_ENDPOINT"]["value"] == m["table_endpoint"],
            "Wrong previous Table target",
        )
        policy["previous_guard_hashes"].append(fingerprint(api["command"]))
        policy["compatible_previous_images"].append(api["image"])
        policy["previous_releases"][revision] = m["release_id"]
    return policy


def checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.flush()
        import os

        os.fsync(handle.fileno())
    temporary.replace(path)


def cleanup(m: dict, cloud, *, now: datetime, expired_only=True, verify_only=False) -> dict:
    validate(m, now=now, allow_expired=True)
    require(
        verify_only or not expired_only or now >= utc(m["expires_at"]),
        "Janitor refuses unexpired run",
    )
    require(
        cloud.subscription() == SUBSCRIPTION and cloud.scope() == m["resource_group_id"],
        "Cleanup identity/subscription scope differs",
    )
    receipt = {"run_id": m["run_id"], "target": m["resource_group_id"], "outcome": "pending"}
    value = cloud.group(m["resource_group_id"])
    if value is not None:
        require(value["id"].lower() == m["resource_group_id"].lower(), "Wrong cleanup target")
        require(
            value.get("tags")
            == {
                "purpose": m["purpose"],
                "runId": m["run_id"],
                "owner": m["owner"],
                "expiresAt": m["expires_at"],
            },
            "Wrong cleanup ownership",
        )
        if verify_only:
            receipt["outcome"] = "scope_verified_no_mutation"
            return receipt
        cloud.delete(m["resource_group_id"])
    require(
        cloud.group(m["resource_group_id"]) is None
        and cloud.remaining(m["resource_group_id"]) == [],
        "Cleanup incomplete",
    )
    receipt["outcome"] = "verified_absent"
    return receipt
