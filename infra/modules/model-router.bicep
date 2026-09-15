metadata description = 'Model Router restricted to GPT-4o-mini and GPT-5.6-sol.'

param accountName string
param deploymentName string
param modelName string
param modelVersion string
param capacity int

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = {
  parent: account
  name: deploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    routing: {
      models: [
        {
          format: 'OpenAI'
          name: 'gpt-4o-mini'
          version: '2024-07-18'
        }
        {
          format: 'OpenAI'
          name: 'gpt-5.6-sol'
          version: '2026-07-09'
        }
      ]
    }
  }
}

output deploymentName string = deployment.name
output deploymentId string = deployment.id
