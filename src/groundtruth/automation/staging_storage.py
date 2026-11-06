"""Staging Table configuration and future live authorization-denial probes."""

import re

from groundtruth.automation.deployment import require
from groundtruth.automation.staging import PRODUCTION_CLIENT, PRODUCTION_PRINCIPAL


def data_scope(m):
    return m["table_id"] + "/tableServices/default/tables/StageSubmissions"


def janitor_role_name(m):
    return "Metrik staging janitor " + m["run_id"]


def validate_security(m, account, assignments, runtime_principal):
    require(account["id"].lower() == m["table_id"].lower(), "Wrong storage account")
    p = account.get("properties", account)
    require(
        p.get("allowSharedKeyAccess") is False and p.get("allowBlobPublicAccess") is False,
        "Shared Key and anonymous Blob access must be disabled",
    )
    require(
        p.get("supportsHttpsTrafficOnly", p.get("enableHttpsTrafficOnly")) is True
        and p.get("minimumTlsVersion") == "TLS1_2"
        and p.get("publicNetworkAccess") == "Enabled",
        "HTTPS/TLS/public endpoint configuration differs",
    )
    network = p.get("networkAcls", p.get("networkRuleSet", {}))
    require(
        network.get("defaultAction") == "Allow" and network.get("bypass") == "None",
        "Unexpected storage network configuration",
    )
    require(
        runtime_principal not in {PRODUCTION_PRINCIPAL, PRODUCTION_CLIENT},
        "Production identity forbidden",
    )
    writers = []
    for role in assignments:
        require(
            role["principalId"] not in {PRODUCTION_PRINCIPAL, PRODUCTION_CLIENT},
            "Production identity has staging access",
        )
        if role["roleDefinitionName"] in {"Owner", "User Access Administrator"}:
            require(
                role["principalId"] == m.get("bootstrap_principal")
                and role["scope"].lower()
                in {
                    m["resource_group_id"].lower(),
                    ("/subscriptions/" + m["subscription"]).lower(),
                },
                "Unreviewed inherited administrative principal",
            )
        elif role["roleDefinitionName"] in {
            "Storage Table Data Contributor",
            "Storage Table Data Reader",
        }:
            require(
                role["principalId"] == runtime_principal
                and role["scope"].lower() == data_scope(m).lower()
                and role["roleDefinitionName"] == "Storage Table Data Contributor",
                "Unexpected Table permission/principal/scope",
            )
            writers.append(role)
        else:
            require(
                role["roleDefinitionName"] in {"Contributor", "Reader", janitor_role_name(m)}
                and role["scope"].lower()
                in {m["resource_group_id"].lower(), m["table_id"].lower()},
                "Unknown or inherited broad authorization requires review",
            )
    require(len(writers) == 1, "One dedicated Table-scoped runtime writer required")
    return {
        "public_endpoint": True,
        "anonymous_data_access": False,
        "shared_key": False,
        "minimum_tls": "TLS1_2",
        "scope": data_scope(m),
    }


def authorization_probes(m, probe):
    """Probe callback performs GET only; a valid new-account Shared Key must be used."""
    require(probe("managed_identity")[0] == 200, "Authorized staging identity cannot read")
    for kind, code in (
        ("unauthorized_identity", "AuthorizationPermissionMismatch"),
        ("shared_key", "KeyBasedAuthenticationNotPermitted"),
        ("anonymous", "AuthenticationFailed"),
        ("http", "AccountRequiresHttps"),
    ):
        status, actual = probe(kind)
        require(
            status in {400, 401, 403} and actual == code,
            "Expected storage authorization denial missing: " + kind,
        )
    return {
        "managed_identity": "verified",
        "unauthorized_identity": "denied",
        "shared_key": "denied",
        "anonymous": "denied",
        "http": "denied",
    }


def authorization_plan(m, principals):
    require(
        len(set(principals.values())) == 3
        and set(principals) == {"runtime", "deploy", "janitor"}
        and all(bool(re.fullmatch(r"[0-9a-f-]{36}", p)) for p in principals.values())
        and all(p not in {PRODUCTION_CLIENT, PRODUCTION_PRINCIPAL} for p in principals.values()),
        "New distinct staging identities required",
    )
    return [
        {
            "principal": principals["runtime"],
            "role": "Storage Table Data Contributor",
            "scope": data_scope(m),
        },
        {"principal": principals["runtime"], "role": "AcrPull", "scope": m["registry_id"]},
        {"principal": principals["deploy"], "role": "AcrPush", "scope": m["registry_id"]},
        {
            "principal": principals["deploy"],
            "role": "Container Apps Contributor",
            "scope": m["app_id"],
        },
        {
            "principal": principals["janitor"],
            "role": janitor_role_name(m),
            "scope": m["resource_group_id"],
        },
    ]


JANITOR_ACTIONS = [
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Resources/subscriptions/resourceGroups/delete",
    "Microsoft.Resources/resources/read",
    "Microsoft.Authorization/roleAssignments/read",
    "Microsoft.Authorization/roleDefinitions/read",
]


def live_probes(m, authorized_read, unauthorized_credential, account_key):
    """Future approved Stage A: GET only, secrets in memory, no credential logging."""
    import json
    from xml.etree import ElementTree

    import httpx
    from azure.core.credentials import AzureNamedKeyCredential
    from azure.core.exceptions import HttpResponseError
    from azure.data.tables import TableClient

    require(bool(account_key), "Fresh staging test key required; never use a production key")
    endpoint = m["table_endpoint"]
    require(endpoint == f"https://{m['table']}.table.core.windows.net", "Wrong probe account")

    def get(kind):
        if kind == "managed_identity":
            authorized_read()  # Authenticated worker readback proves its actual managed identity/Table path.
            return 200, ""
        if kind in {"shared_key", "unauthorized_identity"}:
            credential = (
                AzureNamedKeyCredential(m["table"], account_key)
                if kind == "shared_key"
                else unauthorized_credential
            )
            with TableClient(
                endpoint,
                "StageSubmissions",
                credential=credential,
                retry_total=0,
                logging_enable=False,
            ) as client:
                try:
                    client.get_entity("_health", "schema-v1")
                    return 200, ""
                except HttpResponseError as error:
                    return error.status_code, getattr(error.error_code, "value", error.error_code)
        url = endpoint + "/StageSubmissions(PartitionKey='_health',RowKey='schema-v1')"
        if kind == "http":
            url = url.replace("https://", "http://", 1)
        response = httpx.get(
            url,
            headers={"x-ms-version": "2019-02-02", "Accept": "application/json"},
            follow_redirects=False,
            timeout=20,
        )
        code = response.headers.get("x-ms-error-code")
        if not code:
            try:
                code = json.loads(response.text)["odata.error"]["code"]
            except (ValueError, KeyError):
                code = ElementTree.fromstring(response.text).findtext("Code")
        return response.status_code, code

    return authorization_probes(m, get)
