targetScope = 'subscription'

metadata description = '''
BuildingAssist demo infrastructure for "A Developer's Day on the Microsoft Agentic
Platform". Provisions: Log Analytics + App Insights, ACR (remote builds), a user-
assigned identity, a Container Apps environment with two apps (backend + frontend),
an Azure AI Foundry account/project/model, and an APIM AI Gateway in front of the
model. The Foundry agent + Foundry IQ knowledge and the SRE Agent are created
post-provision (see README and docs/sre-agent.md).
'''

@minLength(1)
@maxLength(64)
@description('Name of the azd environment — used to derive resource names.')
param environmentName string

@minLength(1)
@description('Primary region for all resources.')
param location string

@description('Publisher email for APIM.')
param apimPublisherEmail string = 'demo@contoso-energy.example'

var tags = {
  'azd-env-name': environmentName
  project: 'buildingassist'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var abbrs = {
  rg: 'rg'
  logAnalytics: 'log'
  appInsights: 'appi'
  registry: 'cr'
  identity: 'id'
  appsEnv: 'cae'
  foundry: 'aif'
  apim: 'apim'
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

module foundry 'modules/foundry.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    accountName: '${abbrs.foundry}-${resourceToken}'
    projectName: 'buildingassist'
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
    openAiEndpoint: foundry.outputs.openAiEndpoint
  }
}

var modelEndpoint = '${apim.outputs.gatewayUrl}/openai'

module backend 'modules/container-app.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    appName: 'ca-backend-${resourceToken}'
    serviceName: 'backend'
    environmentId: appsEnv.outputs.environmentId
    identityId: identity.outputs.identityId
    registryLoginServer: registry.outputs.loginServer
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
        name: 'BUILDINGASSIST_KNOWLEDGE_NAME'
        value: 'buildingassist-knowledge'
      }
      {
        name: 'BUILDINGASSIST_AZURE_CLIENT_ID'
        value: identity.outputs.clientId
      }
      {
        name: 'BUILDINGASSIST_MODEL_ENDPOINT'
        value: modelEndpoint
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.appInsightsConnectionString
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
    targetPort: 80
    external: true
    // The backend URL is rendered into config.js at container start from this
    // runtime env var (see src/frontend/docker-entrypoint.sh).
    env: [
      {
        name: 'BACKEND_URL'
        value: backend.outputs.appUrl
      }
    ]
  }
}

module rbac 'modules/rbac.bicep' = {
  scope: resourceGroup
  params: {
    registryName: registry.outputs.registryName
    foundryAccountName: foundry.outputs.accountName
    appPrincipalId: identity.outputs.principalId
    apimPrincipalId: apim.outputs.apimPrincipalId
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
    appInsightsAppId: monitoring.outputs.appInsightsAppId
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
output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.accountName
output AZURE_AI_MODEL_DEPLOYMENT string = foundry.outputs.modelDeploymentName
output SERVICE_BACKEND_URL string = backend.outputs.appUrl
output SERVICE_FRONTEND_URL string = frontend.outputs.appUrl
output APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output SRE_AGENT_NAME string = sreAgent.outputs.agentName
