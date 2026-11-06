"""Offline staging preparation plus separately approved, staging-scoped operations.

No resource creation command is implemented here. ARM output is for owner review.
Candidate/promotion/recovery/cleanup require explicit approved execution and preflight.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from safe_deploy import Azure, run

from groundtruth.automation.deployment import (
    Approval,
    Deployment,
    cache_guard,
    fingerprint,
    require,
    stable_state,
)
from groundtruth.automation.deployment_source import verify_source
from groundtruth.automation.staging import (
    checkpoint,
    cleanup,
    controller_policy,
    preflight,
    prepare,
    validate,
)
from groundtruth.automation.staging_fixture import build_context, generate, write_json
from groundtruth.automation.staging_image import build_and_verify
from groundtruth.automation.staging_resources import (
    application,
    federation_plan,
    infrastructure,
)
from groundtruth.automation.staging_storage import (
    JANITOR_ACTIONS,
    authorization_plan,
    data_scope,
    janitor_role_name,
    live_probes,
    validate_security,
)

ROOT = Path(__file__).resolve().parents[2]


class StageAzure(Azure):
    def __init__(self, manifest, policy):
        super().__init__(policy)
        self.manifest = manifest

    def check(self):
        m = self.manifest
        validate(m, now=datetime.now(UTC))
        require(
            json.loads(run("az", "account", "show", "-o", "json"))["id"] == m["subscription"],
            "Wrong active subscription",
        )
        app = self.app()
        require(app["id"].lower() == m["app_id"].lower(), "Wrong staging app")
        props = app["properties"]
        require(
            (props.get("managedEnvironmentId") or props.get("environmentId")).lower()
            == m["environment_id"].lower(),
            "Wrong staging environment",
        )
        require(
            set(app["identity"]["userAssignedIdentities"]) == {m["runtime_identity_id"]},
            "Wrong runtime identity",
        )
        ingress = props["configuration"]["ingress"]
        require(
            not any(s.get("value") for s in props["configuration"].get("secrets", [])),
            "Plaintext secret readback cannot enter a checkpoint",
        )
        require(
            ingress.get("ipSecurityRestrictions")
            == [
                {"name": "approved-runner", "action": "Allow", "ipAddressRange": m["ingress_cidr"]}
            ],
            "Ingress restriction changed",
        )
        active = [r for r in self.revisions().values() if r["properties"].get("active")]
        require(len(active) <= 3, "Too many active revisions")
        for row in active:
            template = row["properties"]["template"]
            require(
                template["scale"]["maxReplicas"] == 1 and template["volumes"] == m["volumes"],
                "Replica/cache limits changed",
            )
            containers = template["containers"]
            require(
                sum(c["resources"]["cpu"] for c in containers) <= 1
                and sum(float(c["resources"]["memory"].removesuffix("Gi")) for c in containers)
                <= 2,
                "Compute limit changed",
            )
            api = next(c for c in containers if c["name"] == "metrik-api")
            require(
                api["image"] in {m["image"], m["baseline_image"]}
                and api.get("command") == cache_guard(m, row["name"]),
                "Unreviewed staging image/guard",
            )
            values = {v["name"]: v for v in api["env"]}
            require(
                values["DATABASE_URL"].get("secretRef") == "cache-url"
                and values["HEALTH_CHECK_TOKEN"].get("secretRef") == "ops-token",
                "Secret references required",
            )
            require(
                values["PRODUCT_TABLE_ENDPOINT"].get("value") == m["table_endpoint"]
                and values["PRODUCT_WRITE_BACKEND"].get("value") == "azure_table"
                and values["AZURE_CLIENT_ID"].get("value") == m["runtime_client_id"],
                "Backend/identity changed",
            )
            require(
                values["PRODUCT_TABLE_IDENTITY_CLIENT_ID"].get("value") == m["runtime_client_id"],
                "Backend/identity changed",
            )

    def deploy(self, template):
        self.check()
        require(
            len([r for r in self.revisions().values() if r["properties"].get("active")]) < 3,
            "No active revision capacity for candidate",
        )
        return super().deploy(template)

    def set_traffic(self, traffic):
        self.check()
        require(
            all(x["revisionName"].startswith(self.manifest["app_name"] + "--") for x in traffic),
            "Wrong traffic target",
        )
        return super().set_traffic(traffic)

    def deactivate(self, revision):
        self.check()
        require(
            revision == self.manifest["candidate_revision"], "Only owned candidate cleanup allowed"
        )
        return super().deactivate(revision)


class CleanupAzure:
    def __init__(self, m):
        self.m = m

    def subscription(self):
        account = json.loads(run("az", "account", "show", "-o", "json"))
        require(
            account["user"]["type"] == "servicePrincipal"
            and account["user"]["name"] == self.m["cleanup_client_id"],
            "Dedicated janitor identity required",
        )
        return account["id"]

    def scope(self):
        # Scope the ARM reads and avoid Microsoft Graph directory permissions.
        assignments = json.loads(
            run(
                "az",
                "role",
                "assignment",
                "list",
                "--scope",
                self.m["resource_group_id"],
                "--include-inherited",
                "--fill-principal-name",
                "false",
                "--fill-role-definition-name",
                "false",
                "-o",
                "json",
            )
        )
        roles = json.loads(
            run(
                "az",
                "role",
                "definition",
                "list",
                "--scope",
                self.m["resource_group_id"],
                "--name",
                janitor_role_name(self.m),
                "-o",
                "json",
            )
        )
        require(len(roles) == 1 and len(roles[0]["permissions"]) == 1, "Unreviewed janitor role")
        permissions = roles[0]["permissions"][0]
        require(
            set(permissions["actions"]) == set(JANITOR_ACTIONS)
            and not permissions.get("dataActions")
            and not permissions.get("notActions"),
            "Janitor role is broader than deletion/readback",
        )
        own = [x for x in assignments if x["principalId"] == self.m["principals"]["janitor"]]
        require(
            bool(own)
            and all(
                x["scope"].lower() == self.m["resource_group_id"].lower()
                and x["roleDefinitionId"].lower() == roles[0]["id"].lower()
                for x in own
            ),
            "Janitor lacks exact group permission or has inherited broader access",
        )
        return self.m["resource_group_id"]

    def group(self, target):
        exists = json.loads(
            run(
                "az",
                "group",
                "exists",
                "--name",
                self.m["resource_group"],
                "--subscription",
                self.m["subscription"],
                "-o",
                "json",
            )
        )
        return (
            json.loads(
                run(
                    "az",
                    "group",
                    "show",
                    "--name",
                    self.m["resource_group"],
                    "--subscription",
                    self.m["subscription"],
                    "-o",
                    "json",
                )
            )
            if exists
            else None
        )

    def delete(self, target):
        require(target == self.m["resource_group_id"], "Wrong deletion target")
        run(
            "az",
            "group",
            "delete",
            "--name",
            self.m["resource_group"],
            "--subscription",
            self.m["subscription"],
            "--yes",
            "--no-wait",
        )
        for _ in range(120):
            if self.group(target) is None:
                return
            time.sleep(5)
        raise ValueError("Cleanup deadline exceeded; operator escalation required")

    def remaining(self, target):
        # An exact group 404 is required; auth/transport failures are never absence.
        if self.group(target) is not None:
            return json.loads(
                run("az", "resource", "list", "-g", self.m["resource_group"], "-o", "json")
            )
        return []


def execution_gate(args, manifest, *, cleanup_only=False):
    require(
        args.approved_execution and os.environ.get("METRIK_STAGING_EXECUTION_ENABLED") == "true",
        "Staging execution not authorized",
    )
    require(args.manifest_sha256 == fingerprint(manifest), "Exact approved manifest hash required")
    if not cleanup_only:
        require(args.evidence is not None, "Live preflight evidence required")
        preflight(manifest, json.loads(args.evidence.read_text()), now=datetime.now(UTC))
        protected = json.loads((ROOT / "deploy/production-policy.json").read_text())
        verify_source(ROOT, protected, manifest["source_sha"], manifest["source_tree"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "prepare",
            "fixture",
            "build-image",
            "render",
            "render-infrastructure",
            "preflight",
            "inspect",
            "storage-security",
            "initialize-table",
            "baseline-b",
            "candidate",
            "promote",
            "recover",
            "cleanup",
        ],
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--run-id")
    parser.add_argument("--image")
    parser.add_argument("--baseline-image")
    parser.add_argument("--sidecar-image")
    parser.add_argument("--runner-cidr")
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--approved-execution", action="store_true")
    parser.add_argument("--primary-cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.mode == "prepare":
        actual = run("git", "-C", str(ROOT), "rev-parse", "HEAD")
        require(args.source_sha == actual, "Approved source must match exact checkout")
        base = json.loads((ROOT / "deploy/production-policy.json").read_text())
        value = prepare(
            args.run_id,
            actual,
            args.image,
            args.sidecar_image,
            args.runner_cidr,
            now=now,
            source_tree=run("git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"),
            baseline_image=args.baseline_image,
            guard_source=(ROOT / "scripts/azure/cache_guard.template.py.txt").read_text(),
            cache_expected=base["cache_expected"],
        )
        checkpoint(args.output, value)
        return
    if args.mode == "build-image":
        build_and_verify(args.output)
        return
    if args.mode == "fixture":
        actual = run("git", "-C", str(ROOT), "rev-parse", "HEAD")
        require(args.source_sha == actual, "Fixture source must match exact checkout")
        generate(args.output / "fixture", args.source_sha)
        build_context(ROOT, args.output / "fixture", args.output / "context")
        return
    require(args.manifest is not None, "Manifest required")
    m = json.loads(args.manifest.read_text())
    if args.bindings:
        bindings = json.loads(args.bindings.read_text())
        require(
            set(bindings)
            <= {
                "runtime_client_id",
                "cleanup_client_id",
                "domain",
                "principals",
                "bootstrap_principal",
            },
            "Unexpected binding",
        )
        m.update(bindings)
    validate(m, now=now, allow_expired=args.mode == "cleanup")
    if args.mode == "render-infrastructure":
        write_json(args.output, infrastructure(m))
        return
    if args.mode == "render":
        require(
            bool(re.fullmatch(r"[0-9a-f-]{36}", m.get("runtime_client_id", ""))),
            "Bound staging identity required",
        )
        require(
            m.get("domain", "").endswith(".eastus2.azurecontainerapps.io"),
            "Bound staging domain required",
        )
        write_json(args.output / "infrastructure.json", infrastructure(m))
        write_json(args.output / "application.json", application(m))
        write_json(args.output / "bound-manifest.json", m)
        write_json(args.output / "federation-plan.json", federation_plan(m))
        write_json(args.output / "authorization-plan.json", authorization_plan(m, m["principals"]))
        write_json(
            args.output / "janitor-role.json",
            {
                "Name": janitor_role_name(m),
                "IsCustom": True,
                "Description": "Delete only the approved temporary Stage A group",
                "Actions": JANITOR_ACTIONS,
                "NotActions": [],
                "DataActions": [],
                "AssignableScopes": [m["resource_group_id"]],
            },
        )
        return
    if args.mode == "preflight":
        result = preflight(m, json.loads(args.evidence.read_text()), now=now)
    elif args.mode == "initialize-table":
        execution_gate(args, m)
        adapter = StageAzure(m, m)
        adapter.check()
        code = """from groundtruth.config import get_settings
from groundtruth.services.table_submissions import active_store
from azure.core.exceptions import ResourceNotFoundError
s=get_settings()
assert s.product_table_endpoint==__ENDPOINT__ and s.product_table_name=='StageSubmissions'
assert not s.product_table_connection_string
client=active_store().client
assert not list(client.query_entities("PartitionKey ne '_health'")), 'Nonempty synthetic submissions'
try:
 marker=client.get_entity('_health','schema-v1')
 assert marker['SchemaVersion']==1
except ResourceNotFoundError:
 client.create_entity({'PartitionKey':'_health','RowKey':'schema-v1','SchemaVersion':1})
print('STAGING_TABLE_INITIALIZED')
""".replace("__ENDPOINT__", repr(m["table_endpoint"]))
        encoded = base64.b64encode(code.encode()).decode()
        output = run(
            "az",
            "containerapp",
            "exec",
            "-g",
            m["resource_group"],
            "-n",
            m["app_name"],
            "--revision",
            m["app_name"] + "--baseline-a",
            "--container",
            "metrik-api",
            "--command",
            f"/app/.venv/bin/python -c \"import base64;exec(base64.b64decode('{encoded}'))\"",
        )
        require(
            "STAGING_TABLE_INITIALIZED" in output,
            "Synthetic health marker initialization unverified",
        )
        result = {"table_initialized": True, "synthetic_submissions": 0}
    elif args.mode == "baseline-b":
        execution_gate(args, m)
        adapter = StageAzure(m, m)
        adapter.check()
        before = stable_state(adapter.app(), adapter.revisions())
        a, b = m["app_name"] + "--baseline-a", m["app_name"] + "--baseline-b"
        require(
            before["traffic"] == [{"revisionName": a, "weight": 100}],
            "Baseline initialization needs A100",
        )
        rows = adapter.revisions()
        template = copy.deepcopy(rows[a]["properties"]["template"])
        template["revisionSuffix"] = "baseline-b"
        next(c for c in template["containers"] if c["name"] == "metrik-api")["command"] = (
            cache_guard(m, b)
        )
        checkpoint(
            args.output,
            {"before": before, "expected_template": template, "phase": "before_baseline_b"},
        )
        if b not in rows:
            adapter.deploy(template)
        else:
            require(rows[b]["properties"]["template"] == template, "Foreign baseline B")
        ready = adapter.wait_ready(b)
        require(ready["properties"]["template"] == template, "Baseline B configuration differs")
        expected = {**before, "app_template": template}
        require(
            stable_state(adapter.app(), adapter.revisions()) == expected, "Foreign bootstrap drift"
        )
        for name in (a, b):
            adapter.previous_smoke(
                "https://" + adapter.revisions()[name]["properties"]["fqdn"], m["release_id"]
            )
        require(
            stable_state(adapter.app(), adapter.revisions()) == expected,
            "Bootstrap drift before routing",
        )
        weights = [{"revisionName": a, "weight": 70}, {"revisionName": b, "weight": 30}]
        adapter.set_traffic(weights)
        actual = stable_state(adapter.app(), adapter.revisions())
        require(
            actual["traffic"] == weights and actual["global"] == before["global"],
            "Weighted bootstrap readback differs",
        )
        result = {"baseline_ready": True, "traffic": weights, "fingerprint": fingerprint(actual)}
    elif args.mode == "storage-security":
        from azure.identity import AzureCliCredential

        execution_gate(args, m)
        account = json.loads(
            run("az", "storage", "account", "show", "--ids", m["table_id"], "-o", "json")
        )
        roles = json.loads(
            run(
                "az",
                "role",
                "assignment",
                "list",
                "--scope",
                data_scope(m),
                "--include-inherited",
                "--fill-principal-name",
                "false",
                "-o",
                "json",
            )
        )
        result = validate_security(m, account, roles, m["principals"]["runtime"])
        adapter = StageAzure(m, m)
        adapter.check()
        row = adapter.wait_ready(m["candidate_revision"])
        expected = {
            "revision": m["candidate_revision"],
            "serving_source_sha": m["source_sha"],
            "image": m["image"],
            "data_release_id": m["release_id"],
        }
        require(
            row["properties"]["fqdn"] == m["candidate_revision"] + "." + m["domain"],
            "Wrong security probe endpoint",
        )
        result["probes"] = live_probes(
            m,
            lambda: adapter.smoke("https://" + row["properties"]["fqdn"], expected),
            AzureCliCredential(),
            os.environ.get("METRIK_STAGING_TEST_ACCOUNT_KEY", ""),
        )
    elif args.mode == "cleanup":
        execution_gate(args, m, cleanup_only=True)
        result = cleanup(
            m,
            CleanupAzure(m),
            now=now,
            expired_only=not args.primary_cleanup,
            verify_only=args.verify_only,
        )
    else:
        adapter = StageAzure(m, m)
        adapter.check()
        before = stable_state(adapter.app(), adapter.revisions())
        if args.mode == "inspect":
            result = {"fingerprint": fingerprint(before), "state": before}
        else:
            execution_gate(args, m)
            require(
                args.approval is not None and args.receipt is not None,
                "Approval and durable receipt required",
            )
            approval = Approval(**json.loads(args.approval.read_text()))
            require(
                approval.serving_sha == m["source_sha"]
                and approval.serving_tree == m["source_tree"]
                and approval.tooling_sha == m["source_sha"]
                and approval.tooling_tree == m["source_tree"]
                and approval.data_source_sha == m["source_sha"]
                and approval.release_id == m["release_id"],
                "Wrong synthetic approval",
            )
            protected = json.loads((ROOT / "deploy/production-policy.json").read_text())
            verify_source(ROOT, protected, m["source_sha"], m["source_tree"])
            old_receipt = json.loads(args.receipt.read_text()) if args.mode != "candidate" else None
            baseline = old_receipt["recovery"]["before"] if old_receipt else before
            policy = controller_policy(m, baseline)
            adapter.policy = policy
            d = Deployment(
                adapter, policy, approval, checkpoint=lambda r: checkpoint(args.receipt, r)
            )
            if args.mode == "candidate":
                result = d.apply(
                    m["image"],
                    m["candidate_revision"],
                    cache_guard(policy, m["candidate_revision"]),
                    promote=False,
                )
            else:
                result = getattr(d, args.mode)(old_receipt)
    checkpoint(args.output, result)


if __name__ == "__main__":
    main()
