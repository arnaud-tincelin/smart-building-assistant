metadata description = 'Opt-in SRE backend configuration repair; assignments are resource-scoped, not field-scoped.'

param backendAppName string
param identityId string
param identityPrincipalId string
param agentId string
param agentPrincipalId string

resource backendApp 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: backendAppName
}

resource configRepairRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'buildingassist-sre-config-repair')
  properties: {
    roleName: 'BuildingAssist configuration repair (${resourceGroup().name})'
    description: 'Backend configuration repair for the opt-in SRE chat demo. No delete or listSecrets action.'
    type: 'CustomRole'
    assignableScopes: [
      resourceGroup().id
    ]
    permissions: [
      {
        actions: [
          'Microsoft.App/containerApps/read'
          'Microsoft.App/containerApps/write'
          'Microsoft.App/containerApps/revisions/read'
        ]
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

resource configRepairAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(backendApp.id, identityId, 'sre-config-repair')
  scope: backendApp
  properties: {
    roleDefinitionId: configRepairRole.id
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource systemConfigRepairAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(backendApp.id, agentId, 'sre-config-repair-system')
  scope: backendApp
  properties: {
    roleDefinitionId: configRepairRole.id
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output roleDefinitionId string = configRepairRole.id
