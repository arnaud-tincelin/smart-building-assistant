metadata description = 'Azure AI Search service for the BuildingAssist Foundry IQ knowledge base.'

param location string
param tags object
param searchName string

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchName
  location: location
  tags: tags
  sku: {
    name: 'basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    semanticSearch: 'free'
    hostingMode: 'Default'
    partitionCount: 1
    replicaCount: 1
  }
}

output name string = search.name
output id string = search.id
output endpoint string = 'https://${search.name}.search.windows.net'
output principalId string = search.identity.principalId
