targetScope = 'subscription'

metadata description = '''
BuildingAssist demo infrastructure for "A Developer's Day on the Microsoft Agentic
Platform". Provisions: Log Analytics + App Insights, ACR (remote builds), a user-
assigned identity, a Container Apps environment with two apps (backend + frontend),
an Azure AI Foundry account/project/model, and one APIM AI Gateway for models and
OpenAPI-backed MCP tools. The Foundry agent + Foundry IQ knowledge and the SRE Agent
are created post-provision (see README and docs/sre-agent.md).
'''

@minLength(1)
@maxLength(64)
@description('Name of the azd environment — used to derive resource names.')
param environmentName string

@minLength(1)
@description('Primary region for all resources.')
param location string

@description('Region for Azure AI Search. Kept separate so capacity constraints do not move the app.')
param searchLocation string = 'centralus'

@description('Publisher email for APIM.')
param apimPublisherEmail string = 'demo@contoso-energy.example'

@description('Backend container image. Uses the starter image only before the first application deployment.')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Frontend container image. Uses the starter image only before the first application deployment.')
param frontendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var tags = {
  'azd-env-name': environmentName
  project: 'buildingassist'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var searchToken = toLower(uniqueString(subscription().id, environmentName, searchLocation))
var abbrs = {
  rg: 'rg'
  logAnalytics: 'log'
  appInsights: 'appi'
  registry: 'cr'
  identity: 'id'
  appsEnv: 'cae'
  foundry: 'aif'
  search: 'srch'
  apim: 'aigw'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${abbrs.rg}-${environmentName}'
  location: location
  tags: tags
}

module monitoring 'modules/monitoring.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.logAnalytics}-${resourceToken}'
    appInsightsName: '${abbrs.appInsights}-${resourceToken}'
  }
}

module registry 'modules/registry.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    registryName: '${abbrs.registry}${resourceToken}'
  }
}

module identity 'modules/identity.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    identityName: '${abbrs.identity}-${resourceToken}'
  }
}

module appsEnv 'modules/apps-env.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    environmentName: '${abbrs.appsEnv}-${resourceToken}'
    logAnalyticsName: monitoring.outputs.logAnalyticsName
  }
}

module search 'modules/search.bicep' = {
  scope: resourceGroup
  params: {
    location: searchLocation
    tags: tags
    searchName: '${abbrs.search}-${searchToken}'
  }
}

var knowledgeBaseName = 'buildingassist-knowledge'
var knowledgeMcpEndpoint = '${search.outputs.endpoint}/knowledgebases/${knowledgeBaseName}/mcp?api-version=2026-04-01'

module foundry 'modules/foundry.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    accountName: '${abbrs.foundry}-${resourceToken}'
    projectName: 'buildingassist'
    appInsightsResourceId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    knowledgeMcpEndpoint: knowledgeMcpEndpoint
    knowledgeConnectionName: knowledgeBaseName
    searchEndpoint: search.outputs.endpoint
    searchResourceId: search.outputs.id
  }
}

module apim 'modules/apim.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    apimName: '${abbrs.apim}-${resourceToken}'
    publisherEmail: apimPublisherEmail
    publisherName: 'Contoso Energy'
    foundryAccountName: foundry.outputs.accountName
    foundryEndpoint: foundry.outputs.accountEndpoint
    modelDeploymentId: foundry.outputs.modelDeploymentId
    modelDeploymentName: foundry.outputs.modelDeploymentName
    modelVersion: foundry.outputs.modelVersion
    tokenLimitPerMinute: foundry.outputs.modelCapacity * 1000
    backendUrl: backendUrl
  }
}

module operationsMcpConnection 'modules/foundry-mcp-connection.bicep' = {
  scope: resourceGroup
  params: {
    foundryAccountName: foundry.outputs.accountName
    foundryProjectName: foundry.outputs.projectName
    connectionName: 'buildingassist-operations'
    mcpServerUrl: apim.outputs.operationsMcpEndpoint
    apiKey: apim.outputs.runtimeApiKey
  }
}

var backendAppName = 'ca-backend-${resourceToken}'
var backendHost = '${backendAppName}.${appsEnv.outputs.defaultDomain}'
var backendUrl = 'https://${backendHost}'

module backend 'modules/container-app.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    appName: backendAppName
    serviceName: 'backend'
    environmentId: appsEnv.outputs.environmentId
    identityId: identity.outputs.identityId
    registryLoginServer: registry.outputs.loginServer
    image: backendImage
    targetPort: 8000
    external: true
    env: [
      {
        name: 'BUILDINGASSIST_PROJECT_ENDPOINT'
        value: foundry.outputs.projectEndpoint
      }
      {
        name: 'BUILDINGASSIST_MODEL_DEPLOYMENT'
        value: foundry.outputs.modelDeploymentName
      }
      {
        name: 'BUILDINGASSIST_AGENT_NAME'
        value: 'buildingassist-agent'
      }
      {
        name: 'BUILDINGASSIST_KNOWLEDGE_MCP_ENDPOINT'
        value: knowledgeMcpEndpoint
      }
      {
        name: 'BUILDINGASSIST_AZURE_CLIENT_ID'
        value: identity.outputs.clientId
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.appInsightsConnectionString
      }
      {
        name: 'BUILDINGASSIST_ENABLE_TRACING'
        value: 'true'
      }
      {
        name: 'AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING'
        value: 'true'
      }
      {
        name: 'OTEL_SERVICE_NAME'
        value: 'buildingassist-backend'
      }
      {
        name: 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'
        value: 'false'
      }
    ]
  }
}

module frontend 'modules/container-app.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    appName: 'ca-frontend-${resourceToken}'
    serviceName: 'frontend'
    environmentId: appsEnv.outputs.environmentId
    identityId: identity.outputs.identityId
    registryLoginServer: registry.outputs.loginServer
    image: frontendImage
    targetPort: 80
    external: true
    // The backend URL is rendered into config.js at container start from this
    // runtime env var (see src/frontend/docker-entrypoint.sh).
    env: [
      {
        name: 'BACKEND_URL'
        value: backendUrl
      }
    ]
  }
}

module rbac 'modules/rbac.bicep' = {
  scope: resourceGroup
  params: {
    registryName: registry.outputs.registryName
    foundryAccountName: foundry.outputs.accountName
    searchServiceName: search.outputs.name
    appInsightsName: monitoring.outputs.appInsightsName
    appPrincipalId: identity.outputs.principalId
    foundryProjectPrincipalId: foundry.outputs.projectPrincipalId
    searchPrincipalId: search.outputs.principalId
    developerPrincipalId: deployer().objectId
  }
}

module sreAgent 'modules/sre-agent.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    agentName: 'sre-${resourceToken}'
    identityName: '${abbrs.identity}-sre-${resourceToken}'
    actionGroupName: 'ag-sre-${resourceToken}'
    alertName: 'alert-backend-5xx-${resourceToken}'
    developerPrincipalId: deployer().objectId
    appInsightsAppId: monitoring.outputs.appInsightsAppId
    appInsightsResourceId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    logAnalyticsName: monitoring.outputs.logAnalyticsName
    backendAppId: backend.outputs.appId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.registryName
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_AI_PROJECT_ID string = foundry.outputs.projectId
output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.accountName
output AZURE_AI_MODEL_DEPLOYMENT string = foundry.outputs.modelDeploymentName
output BUILDINGASSIST_KNOWLEDGE_MODEL_DEPLOYMENT string = foundry.outputs.knowledgeModelDeploymentName
output BUILDINGASSIST_KNOWLEDGE_MODEL_NAME string = foundry.outputs.knowledgeModelName
output BUILDINGASSIST_KNOWLEDGE_MODEL_RESOURCE_URI string = foundry.outputs.knowledgeModelResourceUri
output APPLICATIONINSIGHTS_RESOURCE_ID string = monitoring.outputs.appInsightsId
output APPLICATIONINSIGHTS_NAME string = monitoring.outputs.appInsightsName
output APPLICATIONINSIGHTS_CONNECTION_NAME string = foundry.outputs.appInsightsConnectionName
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_SEARCH_CONNECTION string = foundry.outputs.searchConnectionName
output BUILDINGASSIST_KNOWLEDGE_MCP_ENDPOINT string = knowledgeMcpEndpoint
output BUILDINGASSIST_KNOWLEDGE_CONNECTION string = foundry.outputs.knowledgeConnectionName
output SERVICE_BACKEND_URL string = backendUrl
output SERVICE_FRONTEND_URL string = frontend.outputs.appUrl
output APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output AI_GATEWAY_RESOURCE_ID string = apim.outputs.apimId
output AI_GATEWAY_MODEL_ENDPOINT string = apim.outputs.modelEndpoint
output AI_GATEWAY_MODEL string = apim.outputs.modelName
output AI_GATEWAY_API_KEY_RESOURCE_ID string = apim.outputs.runtimeApiKeyId
output AI_GATEWAY_CONNECTOR_NAMESPACE_RESOURCE_ID string = apim.outputs.connectorNamespaceId
output AI_GATEWAY_TELEMETRY_EXPORTER_RESOURCE_ID string = '${apim.outputs.apimId}/workspaces/default/telemetryExporters/appinsights'
output BUILDINGASSIST_OPERATIONS_API_URL string = '${backendUrl}/operations'
output BUILDINGASSIST_MCP_SERVER_URL string = apim.outputs.operationsMcpEndpoint
output BUILDINGASSIST_MCP_CONNECTION string = operationsMcpConnection.outputs.connectionName
output SRE_AGENT_NAME string = sreAgent.outputs.agentName
