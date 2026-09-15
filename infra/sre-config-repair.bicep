targetScope = 'resourceGroup'

metadata description = 'Deploy only SRE repair RBAC for existing resources; leaves applications and agent configuration unchanged.'

param backendAppName string
param agentName string
param identityName string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

resource agent 'Microsoft.App/agents@2026-01-01' existing = {
  name: agentName
}

module configRepair 'modules/sre-config-repair-rbac.bicep' = {
  params: {
    backendAppName: backendAppName
    identityId: identity.id
    identityPrincipalId: identity.properties.principalId
    agentId: agent.id
    agentPrincipalId: agent.identity.principalId
  }
}

output roleDefinitionId string = configRepair.outputs.roleDefinitionId
