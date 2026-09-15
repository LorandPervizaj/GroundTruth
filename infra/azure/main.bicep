@description('Azure region for all beta resources')
param location string = resourceGroup().location

@description('Environment name suffix (beta)')
param environmentName string = 'beta'

@description('Unique suffix for globally unique names (ACR, etc.)')
@minLength(4)
@maxLength(12)
param nameSuffix string

@description('PostgreSQL administrator login')
param postgresAdminLogin string = 'metrik_admin'

@description('PostgreSQL administrator password (pass via secure parameter / pipeline secret)')
@secure()
param postgresAdminPassword string

@description('Application database name')
param postgresDatabaseName string = 'metrik'

@description('Container image (ACR login server + repository:tag). Must already exist in ACR.')
@minLength(10)
param containerImage string

@description('Public base URL used by the app (TrustedHost + links). Use default hostname until custom domain is bound.')
param publicBaseUrl string = ''

@description('Optional comma-separated CIDRs/IPs allowed to reach the Container App (invite-only). Empty = public ingress.')
param ingressIpAllowList string = ''

@description('Health check token for ops endpoints (min 24 chars)')
@secure()
param healthCheckToken string

@description('Forwarded allow IPs for uvicorn proxy headers (ACA private ranges; never *)')
param forwardedAllowIps string = '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10'

@description('Require Sentry DSN (false for limited beta)')
param requireSentryDsn bool = false

@description('Optional Sentry DSN')
@secure()
param sentryDsn string = ''

@description('PostgreSQL SKU — Burstable B1ms is the cheapest sensible beta tier')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL storage size in GiB (minimum 32 on Flexible Server)')
@minValue(32)
param postgresStorageGb int = 32

@description('PostgreSQL backup retention days')
@minValue(7)
@maxValue(35)
param postgresBackupRetentionDays int = 7

var prefix = 'metrik-${environmentName}'
var acrName = toLower(replace('acrmetrik${environmentName}${nameSuffix}', '-', ''))
var logAnalyticsName = 'log-${prefix}'
var caeName = 'cae-${prefix}'
var caName = 'ca-metrik-api'
var postgresName = toLower('psql-${prefix}-${nameSuffix}')
var identityName = 'id-${prefix}-app'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  sku: {
    name: postgresSkuName
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageGb
    }
    backup: {
      backupRetentionDays: postgresBackupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    // Beta: public endpoint with Azure-services firewall (see AllowAzureServices rule).
    // Full launch should move to private access / VNet.
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource postgresFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var resolvedPublicBaseUrl = empty(publicBaseUrl) ? 'https://placeholder.local' : publicBaseUrl
var allowCidrs = empty(ingressIpAllowList) ? [] : split(ingressIpAllowList, ',')
var ipRestrictions = [
  for (cidr, i) in allowCidrs: {
    name: 'allow-${i}'
    ipAddressRange: trim(cidr)
    action: 'Allow'
  }
]

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: caName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: union({
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }, empty(ingressIpAllowList) ? {} : {
        ipSecurityRestrictions: ipRestrictions
      })
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: concat([
        {
          name: 'database-url'
          value: 'postgresql+psycopg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDatabaseName}?sslmode=require'
        }
        {
          name: 'health-check-token'
          value: healthCheckToken
        }
      ], empty(sentryDsn) ? [] : [
        {
          name: 'sentry-dsn'
          value: sentryDsn
        }
      ])
    }
    template: {
      containers: [
        {
          name: 'metrik-api'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            { name: 'APP_ENV', value: 'production' }
            { name: 'LOG_FORMAT', value: 'json' }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'API_DOCS_ENABLED', value: 'false' }
            { name: 'API_REQUIRE_LOOKUP_CACHE', value: 'true' }
            { name: 'PRODUCT_WRITE_BACKEND', value: 'database' }
            { name: 'API_RATE_LIMIT_ENABLED', value: 'true' }
            { name: 'ALERTS_SIGNUP_ENABLED', value: 'false' }
            { name: 'VALUATION_PUBLIC_ENABLED', value: 'true' }
            { name: 'RUN_MIGRATIONS_ON_START', value: 'true' }
            { name: 'REQUIRE_SENTRY_DSN', value: requireSentryDsn ? 'true' : 'false' }
            { name: 'REPORTS_GENERATED_DIR', value: '/app/reports/generated' }
            { name: 'PUBLIC_BASE_URL', value: resolvedPublicBaseUrl }
            { name: 'FORWARDED_ALLOW_IPS', value: forwardedAllowIps }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'HEALTH_CHECK_TOKEN', secretRef: 'health-check-token' }
          ], empty(sentryDsn) ? [] : [
            { name: 'SENTRY_DSN', secretRef: 'sentry-dsn' }
          ])
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/ready'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
    postgresDb
    postgresFirewallAzure
  ]
}

output resourceGroupName string = resourceGroup().name
output location string = location
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppDefaultUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output postgresServerName string = postgres.name
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output postgresDatabaseName string = postgresDatabaseName
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output logAnalyticsWorkspaceId string = logAnalytics.id
