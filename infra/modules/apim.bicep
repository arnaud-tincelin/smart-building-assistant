metadata description = '''
Azure API Management AI Gateway tier (preview) with a managed-identity Foundry
provider, Model Router registration, structured token policy, and an OpenAPI ToolServer.
'''

@allowed([
  'eastus2'
  'swedencentral'
])
param location string
param tags object
param apimName string
param publisherEmail string
param publisherName string

@description('Name of the Foundry account that hosts the model deployment.')
param foundryAccountName string

@description('Foundry account endpoint used by the AI Gateway model provider.')
param foundryEndpoint string

@description('Resource ID of the Foundry model deployment exposed by the gateway.')
param modelDeploymentId string

@description('Model deployment name clients send in the model field.')
param modelDeploymentName string

@description('Version of the model behind the Foundry deployment.')
param modelVersion string

@minValue(1)
@description('Per-caller token allowance for the registered model during each minute.')
param tokenLimitPerMinute int = 30000

@description('Public base URL of the BuildingAssist backend API.')
param backendUrl string

var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var normalizedFoundryEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'
var operationsToolServerName = 'building-operations'
var operationsOpenApi = replace(
  loadTextContent('../api/building-operations.openapi.json'),
  '__BACKEND_URL__',
  backendUrl
)

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: 'AIGateway'
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource connectorNamespace 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: apimName
  location: location
  properties: {}
  dependsOn: [
    aiGateway
  ]
}

resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource gatewayFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, aiGateway.id, foundryUserRoleId)
  scope: foundry
  properties: {
    principalId: aiGateway.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource foundryProvider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: 'foundry'
  dependsOn: [
    gatewayFoundryUser
  ]
  properties: {
    kind: 'Foundry'
    displayName: 'Microsoft Foundry'
    description: 'Managed-identity provider for the BuildingAssist model deployment.'
    foundry: {
      endpoint: normalizedFoundryEndpoint
      resourceIds: [
        foundry.id
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
}

resource model 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: modelDeploymentName
  properties: {
    description: 'Model Router exposed through the BuildingAssist AI Gateway.'
    displayName: modelDeploymentName
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: modelDeploymentId
      modelName: modelDeploymentName
      modelVersion: modelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokenLimitPerMinute
        counterKey: 'Identity'
      }
    ]
  }
}

resource operationsToolServer 'Microsoft.ApiManagement/service/workspaces/toolServers@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: operationsToolServerName
  properties: {
    type: 'mcp'
    displayName: 'Contoso Building Operations'
    description: 'Fictional building information, telemetry, alerts, and bounded actions.'
    failureMode: 'failClosed'
    endpoints: [
      {
        namespace: 'operations'
        kind: 'openApi'
        openApi: {
          specSource: {
            type: 'inline'
            contentBase64: base64(operationsOpenApi)
          }
        }
        credentials: {
          type: 'none'
        }
        required: true
      }
    ]
  }
}

resource runtimeApiKey 'Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: 'buildingassist'
  properties: {
    displayName: 'BuildingAssist runtime key'
  }
}

output apimId string = aiGateway.id
output gatewayUrl string = aiGateway.properties.gatewayUrl
output modelEndpoint string = '${aiGateway.properties.gatewayUrl}/default/models/openai/v1'
output modelName string = model.name
output runtimeApiKeyId string = runtimeApiKey.id
output connectorNamespaceId string = connectorNamespace.id
output operationsMcpEndpoint string = '${aiGateway.properties.gatewayUrl}/default/toolservers/${operationsToolServerName}/mcp'
@secure()
#disable-next-line use-resource-symbol-reference
output runtimeApiKey string = listSecrets(runtimeApiKey.id, '2025-09-01-preview').primaryKey
