"""Render reviewed Stage A ARM resources without making cloud calls."""

import uuid

from groundtruth.automation.deployment import cache_guard
from groundtruth.automation.staging_storage import JANITOR_ACTIONS, janitor_role_name


def app_template(m, revision):
    values = {
        "APP_ENV": "production",
        "PRODUCT_WRITE_BACKEND": "azure_table",
        "PRODUCT_TABLE_ENDPOINT": m["table_endpoint"],
        "PRODUCT_TABLE_NAME": "StageSubmissions",
        "RUN_MIGRATIONS_ON_START": "false",
        "API_REQUIRE_LOOKUP_CACHE": "true",
        "API_DOCS_ENABLED": "false",
        "API_RATE_LIMIT_ENABLED": "true",
        "FORWARDED_ALLOW_IPS": "127.0.0.1",
        "REQUIRE_SENTRY_DSN": "false",
        "TRUSTED_HOSTS": ",".join(
            [
                "localhost",
                "127.0.0.1",
                m["app_name"] + "." + m["domain"],
                m["app_name"] + "--baseline-a." + m["domain"],
                m["app_name"] + "--baseline-b." + m["domain"],
            ]
        ),
        "AZURE_CLIENT_ID": m["runtime_client_id"],
        "PRODUCT_TABLE_IDENTITY_CLIENT_ID": m["runtime_client_id"],
        "METRIK_DEPLOY_SOURCE_SHA": m["source_sha"],
        "METRIK_DEPLOY_IMAGE": m["baseline_image"],
        "METRIK_DEPLOY_DATA_RELEASE_ID": m["release_id"],
    }
    return {
        "revisionSuffix": revision.split("--", 1)[1],
        "scale": {"minReplicas": 1, "maxReplicas": 1},
        "volumes": m["volumes"],
        "containers": [
            {
                "name": "metrik-api",
                "image": m["baseline_image"],
                "command": cache_guard(m, revision),
                "resources": {"cpu": 0.75, "memory": "1.5Gi"},
                "env": [{"name": k, "value": v} for k, v in values.items()]
                + [
                    {"name": "DATABASE_URL", "secretRef": "cache-url"},
                    {"name": "HEALTH_CHECK_TOKEN", "secretRef": "ops-token"},
                ],
                "probes": [
                    {
                        "type": "Readiness",
                        "httpGet": {"path": "/api/ready", "port": 8000},
                        "initialDelaySeconds": 5,
                        "periodSeconds": 5,
                    }
                ],
            },
            {
                "name": "postgres-cache",
                "image": m["sidecar_image"],
                "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                "env": [
                    {"name": "POSTGRES_USER", "value": "metrik"},
                    {"name": "POSTGRES_DB", "value": "metrik"},
                    {"name": "POSTGRES_PASSWORD", "secretRef": "cache-password"},
                ],
                "volumeMounts": [{"volumeName": "pgdata", "mountPath": "/var/lib/postgresql/data"}],
            },
        ],
    }


def infrastructure(m):
    """Bootstrap identities/env/storage/ACR only; app is rendered after readback."""
    tags = {
        "purpose": m["purpose"],
        "runId": m["run_id"],
        "owner": m["owner"],
        "expiresAt": m["expires_at"],
    }
    resources = []
    resources.append(
        {
            "type": "Microsoft.Authorization/roleDefinitions",
            "apiVersion": "2022-04-01",
            "name": str(uuid.uuid5(uuid.NAMESPACE_URL, m["resource_group_id"] + "/janitor-role")),
            "properties": {
                "roleName": janitor_role_name(m),
                "type": "CustomRole",
                "description": "Temporary staging group deletion and readback only",
                "assignableScopes": [m["resource_group_id"]],
                "permissions": [
                    {
                        "actions": JANITOR_ACTIONS,
                        "notActions": [],
                        "dataActions": [],
                        "notDataActions": [],
                    }
                ],
            },
        }
    )
    for role in ("runtime", "deploy", "janitor"):
        resources.append(
            {
                "type": "Microsoft.ManagedIdentity/userAssignedIdentities",
                "apiVersion": "2023-01-31",
                "name": role + "-" + m["run_id"],
                "location": m["region"],
                "tags": tags,
            }
        )
    resources += [
        {
            "type": "Microsoft.App/managedEnvironments",
            "apiVersion": "2024-03-01",
            "name": "cae-" + m["run_id"],
            "location": m["region"],
            "tags": tags,
            "properties": {
                "appLogsConfiguration": {"destination": "none"},
                "workloadProfiles": [{"name": "Consumption", "workloadProfileType": "Consumption"}],
            },
        },
        {
            "type": "Microsoft.ContainerRegistry/registries",
            "apiVersion": "2023-07-01",
            "name": m["registry"],
            "location": m["region"],
            "tags": tags,
            "sku": {"name": "Basic"},
            "properties": {"adminUserEnabled": False},
        },
        {
            "type": "Microsoft.Storage/storageAccounts",
            "apiVersion": "2023-05-01",
            "name": m["table"],
            "location": m["region"],
            "tags": tags,
            "kind": "StorageV2",
            "sku": {"name": "Standard_LRS"},
            "properties": {
                "supportsHttpsTrafficOnly": True,
                "allowBlobPublicAccess": False,
                "allowSharedKeyAccess": False,
                "minimumTlsVersion": "TLS1_2",
                "publicNetworkAccess": "Enabled",
                "networkAcls": {
                    "defaultAction": "Allow",
                    "bypass": "None",
                    "ipRules": [],
                },
            },
        },
        {
            "type": "Microsoft.Storage/storageAccounts/tableServices/tables",
            "apiVersion": "2023-05-01",
            "name": m["table"] + "/default/StageSubmissions",
            "dependsOn": [m["table_id"]],
            "properties": {},
        },
    ]
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "resources": resources,
    }


def application(m):
    """Fresh staging secrets arrive only as secure parameters at approved execution."""
    app = {
        "type": "Microsoft.App/containerApps",
        "apiVersion": "2024-03-01",
        "name": m["app_name"],
        "location": m["region"],
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {m["runtime_identity_id"]: {}},
        },
        "properties": {
            "managedEnvironmentId": m["environment_id"],
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Multiple",
                "maxInactiveRevisions": 3,
                "ingress": {
                    "external": True,
                    "targetPort": 8000,
                    "allowInsecure": False,
                    "ipSecurityRestrictions": [
                        {
                            "name": "approved-runner",
                            "action": "Allow",
                            "ipAddressRange": m["ingress_cidr"],
                        }
                    ],
                    "traffic": [{"revisionName": m["app_name"] + "--baseline-a", "weight": 100}],
                },
                "registries": [
                    {"server": m["registry"] + ".azurecr.io", "identity": m["runtime_identity_id"]}
                ],
                "secrets": [
                    {"name": "cache-password", "value": "[parameters('cachePassword')]"},
                    {"name": "ops-token", "value": "[parameters('opsToken')]"},
                    {
                        "name": "cache-url",
                        "value": "[concat('postgresql+psycopg://metrik:', uriComponent(parameters('cachePassword')), '@127.0.0.1:5432/metrik')]",
                    },
                ],
            },
            "template": app_template(m, m["app_name"] + "--baseline-a"),
        },
    }
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "cachePassword": {"type": "secureString", "minLength": 32},
            "opsToken": {"type": "secureString", "minLength": 32},
        },
        "resources": [app],
    }


def federation_plan(m):
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "audiences": ["api://AzureADTokenExchange"],
        "deploy": {
            "identity": m["deploy_identity_id"],
            "subjects": ["repo:LorandPervizaj/GroundTruth:environment:azure-staging"],
        },
        "janitor": {
            "identity": m["resource_group_id"]
            + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/janitor-"
            + m["run_id"],
            "subjects": [
                "repo:LorandPervizaj/GroundTruth:ref:refs/heads/master",
                "repo:LorandPervizaj/GroundTruth:ref:refs/heads/codex/publication-integration-20261104",
            ],
        },
    }
