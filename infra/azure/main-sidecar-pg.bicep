@description('Fallback beta stack when Azure Database for PostgreSQL Flexible Server is subscription-blocked. Runs Postgres as a sidecar with Azure Files persistence.')
param location string = resourceGroup().location
param environmentName string = 'beta'
@minLength(4)
@maxLength(12)
param nameSuffix string
@secure()
param postgresPassword string
@secure()
param healthCheckToken string
@minLength(10)
param containerImage string
param publicBaseUrl string = ''
param forwardedAllowIps string = '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10'
param requireSentryDsn bool = false
@secure()
param sentryDsn string = ''
param postgresUser string = 'metrik'
param postgresDatabaseName string = 'metrik'

var prefix = 'metrik-${environmentName}'
var acrName = toLower(replace('acrmetrik${environmentName}${nameSuffix}', '-', ''))
var logAnalyticsName = 'log-${prefix}'
var caeName = 'cae-${prefix}'
var caName = 'ca-metrik-api'
var identityName = 'id-${prefix}-app'
var storageName = toLower(take('stmetrik${environmentName}${nameSuffix}', 24))
var resolvedPublicBaseUrl = empty(publicBaseUrl) ? 'https://placeholder.local' : publicBaseUrl

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
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

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

// NOTE: Official postgres:16 cannot chmod on Azure Files SMB shares.
// Beta uses EmptyDir for PGDATA (ephemeral). Prefer Flexible Server when the
// subscription allows it (main.bicep). EmptyDir data is lost on replica recycle.

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
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: concat([
        {
          name: 'database-url'
          value: 'postgresql+psycopg://${postgresUser}:${postgresPassword}@127.0.0.1:5432/${postgresDatabaseName}'
        }
        {
          name: 'health-check-token'
          value: healthCheckToken
        }
        {
          name: 'postgres-password'
          value: postgresPassword
        }
      ], empty(sentryDsn) ? [] : [
        {
          name: 'sentry-dsn'
          value: sentryDsn
        }
      ])
    }
    template: {
      volumes: [
        {
          name: 'pgdata'
          storageType: 'EmptyDir'
        }
      ]
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
            // ACA ingress/probes use platform Host headers; "*" is acceptable behind ACA TLS edge.
            { name: 'TRUSTED_HOSTS', value: '*' }
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
              initialDelaySeconds: 30
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/ready'
                port: 8000
              }
              initialDelaySeconds: 40
              periodSeconds: 10
            }
          ]
        }
        {
          name: 'postgres'
          image: 'docker.io/library/postgres:16-alpine'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'POSTGRES_USER', value: postgresUser }
            { name: 'POSTGRES_DB', value: postgresDatabaseName }
            { name: 'POSTGRES_PASSWORD', secretRef: 'postgres-password' }
            { name: 'PGDATA', value: '/var/lib/postgresql/data/pgdata' }
          ]
          volumeMounts: [
            {
              volumeName: 'pgdata'
              mountPath: '/var/lib/postgresql/data'
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
    storage
  ]
}

output resourceGroupName string = resourceGroup().name
output location string = location
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppDefaultUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output postgresMode string = 'sidecar-emptydir-ephemeral'
output postgresNote string = 'Flexible Server blocked on subscription; Postgres 16 sidecar uses EmptyDir (ephemeral). Upgrade to Flexible Server (main.bicep) when allowed. Do not treat EmptyDir as durable DR.'
output storageAccountName string = storage.name
