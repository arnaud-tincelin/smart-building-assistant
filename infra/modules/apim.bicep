metadata description = '''
Azure API Management as an AI Gateway in front of the Azure OpenAI (Foundry) model
endpoint: token rate-limiting, token metrics, retries, and managed-identity auth.
'''

param location string
param tags object
param apimName string
param publisherEmail string
param publisherName string

@description('APIM SKU. BasicV2/StandardV2 provision faster than classic Developer.')
@allowed([
  'BasicV2'
  'StandardV2'
  'Developer'
])
param skuName string = 'BasicV2'

@description('Azure OpenAI endpoint to front, e.g. https://<account>.openai.azure.com/')
param openAiEndpoint string

resource apim 'Microsoft.ApiManagement/service@2023-05-01-preview' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: skuName
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

resource openAiBackend 'Microsoft.ApiManagement/service/backends@2023-05-01-preview' = {
  parent: apim
  name: 'azure-openai'
  properties: {
    protocol: 'http'
    url: '${openAiEndpoint}openai'
  }
}

resource openAiApi 'Microsoft.ApiManagement/service/apis@2023-05-01-preview' = {
  parent: apim
  name: 'azure-openai'
  properties: {
    displayName: 'Azure OpenAI (Foundry)'
    path: 'openai'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    serviceUrl: '${openAiEndpoint}openai'
    apiType: 'http'
  }
}

resource openAiApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-05-01-preview' = {
  parent: openAiApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('../policies/openai-policy.xml')
  }
  dependsOn: [
    openAiBackend
  ]
}

output apimName string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output apimPrincipalId string = apim.identity.principalId
