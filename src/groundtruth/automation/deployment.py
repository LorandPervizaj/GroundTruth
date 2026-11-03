"""Fail-closed deployment protocol. Azure writes exist only behind an explicit apply call.

State fingerprints detect cooperative and out-of-band changes; they are optimistic
checks, not an Azure compare-and-swap. Operators must also hold the shared Actions
deployment lock and prohibit direct CLI writers during the maintenance window.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import zlib
from dataclasses import dataclass
from typing import Any, Protocol

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[a-z0-9.-]+/[a-z0-9/._-]+@sha256:[0-9a-f]{64}")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def cache_guard(policy: dict, revision: str) -> list[str]:
    source = policy["guard_source"]
    require(
        hashlib.sha256(source.encode()).hexdigest() == policy["guard_template_sha256"],
        "Cache guard source differs",
    )
    source = source.replace(
        "__EXPECTED__", repr({**policy["cache_expected"], "revision": revision})
    )
    compile(source, "cache_guard", "exec")
    data = base64.b64encode(zlib.compress(source.encode())).decode()
    return [
        "/app/.venv/bin/python",
        "-c",
        f"import base64,zlib;exec(zlib.decompress(base64.b64decode('{data}')))",
    ]


@dataclass(frozen=True)
class Approval:
    serving_sha: str
    serving_tree: str
    tooling_sha: str
    tooling_tree: str
    data_source_sha: str
    release_id: str
    bundle_sha256: str
    expected_state: str
    tooling_ref: str = ""

    def validate(self) -> None:
        if self.tooling_ref:
            require(
                bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}", self.tooling_ref))
                and ".." not in self.tooling_ref
                and not self.tooling_ref.endswith("/")
                and not SHA.fullmatch(self.tooling_ref),
                "Explicit branch/tag tooling ref required",
            )
        for name in (
            "serving_sha",
            "serving_tree",
            "tooling_sha",
            "tooling_tree",
            "data_source_sha",
        ):
            require(
                bool(SHA.fullmatch(getattr(self, name))),
                f"Invalid {name}; full immutable SHA required",
            )
        for name in ("bundle_sha256", "expected_state"):
            require(bool(re.fullmatch(r"[0-9a-f]{64}", getattr(self, name))), f"Invalid {name}")
        require(
            bool(re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}", self.release_id)),
            "Invalid data release ID",
        )


def env(container: dict) -> dict:
    return {
        e["name"]: {k: v for k, v in e.items() if k != "name"} for e in container.get("env", [])
    }


def api_container(template: dict) -> dict:
    matches = [c for c in template["containers"] if c["name"] == "metrik-api"]
    require(len(matches) == 1, "Missing or ambiguous API container")
    return matches[0]


def allocation(app: dict) -> list[dict]:
    ingress = app["properties"]["configuration"]["ingress"]
    traffic = ingress.get("traffic", [])
    require(bool(traffic), "Missing traffic allocation")
    result = []
    for t in traffic:
        require(
            not t.get("latestRevision") and bool(t.get("revisionName")),
            "Traffic must use explicit revision identities",
        )
        require(not t.get("label"), "Label routing requires a separately reviewed policy")
        require(type(t.get("weight")) is int and t["weight"] >= 0, "Invalid traffic weight")
        if t["weight"]:
            result.append({"revisionName": t["revisionName"], "weight": t["weight"]})
    require(sum(t["weight"] for t in result) == 100, "Traffic weights must total 100")
    require(len({t["revisionName"] for t in result}) == len(result), "Duplicate traffic revisions")
    return sorted(result, key=lambda t: t["revisionName"])


def global_state(app: dict) -> dict:
    p = app["properties"]
    config = copy.deepcopy(p["configuration"])
    config["ingress"].pop("traffic", None)
    return {
        "id": app["id"],
        "identity": app.get("identity"),
        "configuration": config,
        "environmentId": p.get("environmentId") or p.get("managedEnvironmentId"),
    }


def stable_state(app: dict, revisions: dict) -> dict:
    """Serving identity comes from traffic; the app template is watched only for drift."""
    traffic = allocation(app)
    serving = {}
    for t in traffic:
        name = t["revisionName"]
        require(name in revisions, "Serving revision readback missing")
        r = revisions[name]["properties"]
        serving[name] = r["template"]
    return {
        "global": global_state(app),
        "traffic": traffic,
        "serving": serving,
        "app_template": app["properties"].get("template"),
    }


def compatible(template: dict, policy: dict, *, candidate: bool = False) -> None:
    api = api_container(template)
    e = env(api)
    require(
        e.get("PRODUCT_WRITE_BACKEND") == {"value": "azure_table"}, "Azure Table backend required"
    )
    require(
        e.get("RUN_MIGRATIONS_ON_START") == {"value": "false"},
        "Unconditional startup migrations forbidden",
    )
    require(
        e.get("API_REQUIRE_LOOKUP_CACHE") == {"value": "true"}, "Verified cache startup required"
    )
    require(
        bool(DIGEST.fullmatch(api["image"])), "Immutable registry-qualified API digest required"
    )
    for c in template["containers"]:
        require(bool(DIGEST.fullmatch(c["image"])), "Every sidecar must use an immutable digest")
    require(template.get("volumes") == policy["volumes"], "Unreviewed volume configuration")
    if not candidate:
        require(
            fingerprint(api.get("command")) in policy["previous_guard_hashes"],
            "Previous cache startup guard not approved",
        )


class Cloud(Protocol):
    def app(self) -> dict: ...
    def revisions(self) -> dict: ...
    def deploy(self, template: dict) -> None: ...
    def wait_ready(self, revision: str) -> dict: ...
    def inspect_image(self, image: str) -> dict: ...
    def smoke(self, url: str, expected: dict) -> None: ...
    def previous_smoke(self, url: str, release: str) -> None: ...
    def set_traffic(self, traffic: list[dict]) -> None: ...
    def deactivate(self, revision: str) -> None: ...


class Deployment:
    def __init__(self, cloud: Cloud, policy: dict, approval: Approval):
        approval.validate()
        self.cloud, self.policy, self.approval = cloud, policy, approval
        self.receipt: dict = {"outcome": "not_started", "approval": vars(approval), "events": []}

    def read(self) -> tuple[dict, dict, dict]:
        app, revisions = self.cloud.app(), self.cloud.revisions()
        require(app["id"].lower() == self.policy["app_id"].lower(), "Wrong Azure target")
        require(
            app["properties"]["configuration"].get("activeRevisionsMode") == "Multiple",
            "Multiple revision mode required",
        )
        state = stable_state(app, revisions)
        for template in state["serving"].values():
            is_candidate = api_container(template)["image"] == self.receipt.get("candidate_image")
            compatible(template, self.policy, candidate=is_candidate)
            if is_candidate:
                require(
                    api_container(template).get("command") == self._guard,
                    "Candidate startup guard changed",
                )
        return app, revisions, state

    def unchanged(self, expected: dict) -> tuple[dict, dict]:
        app, revisions, state = self.read()
        require(state == expected, "Production state changed; refusing stale mutation")
        return app, revisions

    def apply(self, image: str, revision: str, guard_command: list[str]) -> dict:
        require(bool(DIGEST.fullmatch(image)), "Candidate must use immutable digest")
        require(
            revision.startswith(self.policy["app_name"] + "--")
            and bool(re.fullmatch(r"[a-z0-9-]+", revision)),
            "Invalid candidate revision",
        )
        require(
            guard_command == cache_guard(self.policy, revision),
            "Candidate cache startup guard differs",
        )
        self._guard = guard_command
        app, revisions, before = self.read()
        for name in before["serving"]:
            state = revisions[name]["properties"]
            require(
                state.get("active") is True and state.get("healthState") == "Healthy",
                "Serving baseline not healthy/active",
            )
        require(
            fingerprint(before) == self.approval.expected_state,
            "Approved production fingerprint differs",
        )
        require(revision not in revisions, "Candidate revision already exists")
        labels = self.cloud.inspect_image(image)
        expected_labels = {
            "org.opencontainers.image.revision": self.approval.serving_sha,
            "io.metrik.data-release-id": self.approval.release_id,
            "io.metrik.data-source-sha": self.approval.data_source_sha,
            "io.metrik.bundle-sha256": self.approval.bundle_sha256,
        }
        require(
            all(labels.get(k) == v for k, v in expected_labels.items()),
            "Candidate image provenance/digest mismatch",
        )
        # Weighted baselines are supported only when backend and runtime configuration
        # agree. Use an actual traffic-serving template, never properties.template.
        templates = list(before["serving"].values())
        baseline = templates[0]

        def contract(t: dict) -> dict:
            a = copy.deepcopy(api_container(t))
            a.pop("image", None)
            a.pop("command", None)
            a["env"] = [e for e in a.get("env", []) if not e["name"].startswith("METRIK_DEPLOY_")]
            return {
                "api": a,
                "other": [c for c in t["containers"] if c["name"] != "metrik-api"],
                "volumes": t.get("volumes"),
                "scale": t.get("scale"),
            }

        require(
            all(contract(t) == contract(baseline) for t in templates),
            "Weighted revisions have incompatible backend/configuration",
        )
        previous = {}
        for name, t in before["serving"].items():
            old = api_container(t)["image"]
            require(
                old in self.policy["compatible_previous_images"],
                "Previous serving digest not approved for rollback",
            )
            require(name in self.policy["previous_releases"], "Previous release identity missing")
            previous[name] = {"image": old, "release_id": self.policy["previous_releases"][name]}
        template = copy.deepcopy(baseline)
        template["revisionSuffix"] = revision.split("--", 1)[1]
        api = api_container(template)
        api["image"], api["command"] = image, guard_command
        api.pop("args", None)
        values = {
            "METRIK_DEPLOY_SOURCE_SHA": self.approval.serving_sha,
            "METRIK_DEPLOY_DATA_RELEASE_ID": self.approval.release_id,
            "METRIK_DEPLOY_IMAGE": image,
        }
        api["env"] = [e for e in api.get("env", []) if e["name"] not in values] + [
            {"name": k, "value": v} for k, v in values.items()
        ]
        domain = app["properties"]["configuration"]["ingress"]["fqdn"].split(".", 1)[1]
        candidate_host = revision + "." + domain
        hosts = env(api).get("TRUSTED_HOSTS", {}).get("value", "")
        require(bool(hosts) and "*" not in hosts, "Explicit trusted hosts required")
        api["env"] = [e for e in api["env"] if e["name"] != "TRUSTED_HOSTS"] + [
            {"name": "TRUSTED_HOSTS", "value": hosts + "," + candidate_host}
        ]
        compatible(template, self.policy, candidate=True)
        self.receipt.update(
            before_fingerprint=fingerprint(before),
            previous=previous,
            previous_traffic=before["traffic"],
            configuration_fingerprint=fingerprint(before["global"]),
            candidate_image=image,
            candidate_revision=revision,
        )
        promoted = [{"revisionName": revision, "weight": 100}]
        staged = {**before, "app_template": template}
        promoted_state = None
        try:
            self.unchanged(before)
            for name in before["serving"]:
                self.cloud.previous_smoke(
                    "https://" + revisions[name]["properties"]["fqdn"], previous[name]["release_id"]
                )
            self.unchanged(before)
            self.cloud.deploy(template)
            self.receipt["events"].append("candidate_created")
            self.unchanged(staged)
            candidate = self.cloud.wait_ready(revision)
            require(
                candidate["properties"]["template"] == template,
                "Candidate template differs from reviewed clone",
            )
            url = "https://" + candidate["properties"]["fqdn"]
            require(
                candidate["properties"]["fqdn"] == candidate_host, "Unsupported revision endpoint"
            )
            expected = {
                "revision": revision,
                "serving_source_sha": self.approval.serving_sha,
                "image": image,
                "data_release_id": self.approval.release_id,
            }
            self.cloud.smoke(url, expected)
            self.unchanged(staged)
            # Re-read candidate immediately before routing as well as the serving state.
            require(
                self.cloud.wait_ready(revision)["properties"]["template"] == template,
                "Candidate changed before promotion",
            )
            promoted_state = {
                "global": before["global"],
                "traffic": promoted,
                "serving": {revision: template},
                "app_template": template,
            }
            self.cloud.set_traffic(promoted)
            self.receipt["events"].append("promotion_requested")
            self.unchanged(promoted_state)
            public = "https://" + app["properties"]["configuration"]["ingress"]["fqdn"]
            self.cloud.smoke(public, expected)
            self.unchanged(promoted_state)
            self.receipt["outcome"] = "verified"
        except Exception as error:
            self.receipt["outcome"] = "failed"
            self.receipt["error_type"] = type(error).__name__
            self.receipt["error"] = str(error)
            # Only rollback a state that is provably ours. CLI transport failure may
            # have committed routing: read it back instead of trusting an exit code.
            try:
                _, _, current = self.read()
                if current in (before, staged):
                    self.receipt["rollback"] = "previous_traffic_unchanged"
                elif promoted_state is not None and current == promoted_state:
                    all_revisions = self.cloud.revisions()
                    for name, t in before["serving"].items():
                        r = all_revisions[name]["properties"]
                        require(
                            r.get("active") is True
                            and r.get("healthState") == "Healthy"
                            and r["template"] == t,
                            "Previous rollback revision changed/unhealthy",
                        )
                        self.cloud.previous_smoke(
                            "https://" + r["fqdn"], previous[name]["release_id"]
                        )
                    self.unchanged(promoted_state)
                    self.cloud.set_traffic(before["traffic"])
                    self.unchanged(staged)
                    for name in before["serving"]:
                        self.cloud.previous_smoke(
                            "https://" + all_revisions[name]["properties"]["fqdn"],
                            previous[name]["release_id"],
                        )
                    self.unchanged(staged)
                    self.receipt["rollback"] = "verified_exact_previous_allocation"
                else:
                    self.receipt["rollback"] = "refused_foreign_state"
            except Exception:
                self.receipt["rollback"] = "unverified_no_further_mutation"
            if self.receipt.get("rollback") in {
                "previous_traffic_unchanged",
                "verified_exact_previous_allocation",
            }:
                try:
                    expected_unchanged = before if self.read()[2] == before else staged
                    _, rows = self.unchanged(expected_unchanged)
                    owned = rows.get(revision)
                    if owned is not None:
                        require(
                            owned["properties"]["template"] == template,
                            "Owned candidate changed; cleanup refused",
                        )
                        self.cloud.deactivate(revision)
                        self.unchanged(expected_unchanged)
                        self.receipt["cleanup"] = "failed_owned_candidate_deactivated"
                except Exception:
                    self.receipt["cleanup"] = "unverified_operator_action_required"
            raise
        return self.receipt
