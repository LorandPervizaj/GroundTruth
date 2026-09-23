@description('Region for private GroundTruth research resources')
param location string = resourceGroup().location

@description('Globally unique lowercase suffix')
@minLength(4)
@maxLength(12)
param nameSuffix string

@description('Existing ACR containing the private research worker image')
param acrName string

@description('Immutable GroundTruth research image')
param researchImage string

@description('Research PostgreSQL administrator login')
param postgresAdminLogin string = 'groundtruth_admin'

@secure()
@description('Research PostgreSQL administrator password')
param postgresAdminPassword string

@description('Research database name')
param postgresDatabaseName string = 'groundtruth'

@description('Flexible Server SKU; availability depends on subscription/region')
param postgresSkuName string = 'Standard_B1ms'

@description('Monday schedule in UTC. 03:00 UTC is 04:00/05:00 Europe/Belgrade.')
param cronExpression string = '0 3 * * 1'

@description('Statistical heuristics remain shadow-only during calibration')
param statisticalQaShadow bool = true

var prefix = 'groundtruth-research'
var postgresName = toLower('psql-${prefix}-${nameSuffix}')
var storageName = toLower(take('stgtresearch${nameSuffix}', 24))
var environmentName = 'cae-${prefix}'
var identityName = 'id-${prefix}-job'
var jobName = 'job-groundtruth-weekly'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: identity.properties.principalId
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
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 14
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'POSTGIS'
    source: 'user-override'
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [extensions]
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource stateShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: 'pipeline-state'
  properties: {
    enabledProtocols: 'SMB'
    shareQuota: 5
  }
}

resource releaseShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: 'verified-releases'
  properties: {
    enabledProtocols: 'SMB'
    shareQuota: 20
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${prefix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource stateStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'pipeline-state'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: stateShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource releaseStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'verified-releases'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: releaseShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource weeklyJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 43200
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          value: 'postgresql+psycopg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDatabaseName}?sslmode=require'
        }
      ]
    }
    template: {
      volumes: [
        {
          name: 'pipeline-state'
          storageType: 'AzureFile'
          storageName: stateStorage.name
        }
        {
          name: 'verified-releases'
          storageType: 'AzureFile'
          storageName: releaseStorage.name
        }
      ]
      containers: [
        {
          name: 'groundtruth'
          image: researchImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'APP_ENV', value: 'production' }
            { name: 'GROUNDTRUTH_PIPELINE_STATE_DIR', value: '/mnt/state' }
            { name: 'GROUNDTRUTH_RELEASE_OUTPUT_DIR', value: '/mnt/releases' }
            { name: 'GROUNDTRUTH_STATISTICAL_QA_SHADOW', value: statisticalQaShadow ? 'true' : 'false' }
          ]
          volumeMounts: [
            { volumeName: 'pipeline-state', mountPath: '/mnt/state' }
            { volumeName: 'verified-releases', mountPath: '/mnt/releases' }
          ]
        }
      ]
    }
  }
  dependsOn: [acrPull, database, allowAzure, stateStorage, releaseStorage]
}

output researchJobName string = weeklyJob.name
output researchDatabaseServer string = postgres.name
output researchDatabaseFqdn string = postgres.properties.fullyQualifiedDomainName
output stateStorageAccount string = storage.name
output stateFileShare string = stateShare.name
output releaseFileShare string = releaseShare.name
output scheduleUtc string = cronExpression
