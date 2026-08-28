targetScope = 'resourceGroup'

metadata description = 'User-assigned identity and GitHub branch federated credential for CI/CD.'

param location string
param tags object
param identityName string
param githubSubject string
param githubBranch string

resource deploymentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

resource githubCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  parent: deploymentIdentity
  name: 'github-${githubBranch}'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject
  }
}

output clientId string = deploymentIdentity.properties.clientId
output principalId string = deploymentIdentity.properties.principalId
