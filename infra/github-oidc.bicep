targetScope = 'subscription'

metadata description = '''
One-time bootstrap for GitHub Actions. Creates a user-assigned managed identity,
trusts OIDC tokens issued for this repository's main branch, and grants the
subscription permissions required by the subscription-scoped azd deployment.
'''

@description('Azure region for the managed identity resource group.')
param location string

@minLength(1)
@description('GitHub organization or user that owns the repository.')
param githubOwner string

@minLength(1)
@description('GitHub repository name, without the owner.')
param githubRepository string

@description('Repository subject prefix reported by GitHub. Leave empty to use the legacy owner/repository format.')
param githubSubjectPrefix string = ''

@minLength(1)
@description('Branch allowed to request Azure tokens.')
param githubBranch string = 'main'

@description('Resource group that holds the CI/CD identity.')
param identityResourceGroupName string = 'rg-buildingassist-cicd'

@description('Name of the user-assigned managed identity used by GitHub Actions.')
param identityName string = 'id-buildingassist-github'

@description('Existing tags on the CI/CD identity resource group to retain during reconfiguration.')
param identityResourceGroupTags object = {}

@description('Existing tags on the CI/CD identity to retain during reconfiguration.')
param identityTags object = {}

var tags = {
  project: 'buildingassist'
  purpose: 'github-cicd'
}
var contributorRoleId = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
var rbacAdministratorRoleId = 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
var resolvedGithubSubjectPrefix = empty(githubSubjectPrefix)
  ? 'repo:${githubOwner}/${githubRepository}'
  : githubSubjectPrefix
var deploymentIdentityId = resourceId(
  subscription().subscriptionId,
  identityResourceGroupName,
  'Microsoft.ManagedIdentity/userAssignedIdentities',
  identityName
)

resource identityResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: identityResourceGroupName
  location: location
  tags: union(identityResourceGroupTags, tags)
}

module deploymentIdentity 'modules/github-oidc-identity.bicep' = {
  scope: identityResourceGroup
  params: {
    githubBranch: githubBranch
    githubSubject: '${resolvedGithubSubjectPrefix}:ref:refs/heads/${githubBranch}'
    identityName: identityName
    location: location
    tags: union(identityTags, tags)
  }
}

// The application template creates a resource group and role assignments, so
// deployment requires resource writes and RBAC management at subscription scope.
resource contributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, deploymentIdentityId, contributorRoleId)
  properties: {
    principalId: deploymentIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRoleId)
  }
}

resource rbacAdministratorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, deploymentIdentityId, rbacAdministratorRoleId)
  properties: {
    principalId: deploymentIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rbacAdministratorRoleId)
  }
}

output AZURE_CLIENT_ID string = deploymentIdentity.outputs.clientId
output AZURE_PRINCIPAL_ID string = deploymentIdentity.outputs.principalId
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_TENANT_ID string = tenant().tenantId
