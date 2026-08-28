metadata description = 'A key-authenticated Foundry project connection to an APIM-hosted MCP server.'

param foundryAccountName string
param foundryProjectName string
param connectionName string
param mcpServerUrl string

@secure()
param apiKey string

resource account 'Microsoft.CognitiveServices/accounts@2026-05-01' existing = {
  name: foundryAccountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2026-05-01' existing = {
  parent: account
  name: foundryProjectName
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = {
  parent: project
  name: connectionName
  properties: {
    authType: 'CustomKeys'
    category: 'RemoteTool'
    target: mcpServerUrl
    isSharedToAll: true
    credentials: {
      keys: {
        'Api-Key': apiKey
      }
    }
  }
}

output connectionName string = connection.name