metadata description = 'A single Azure Container App pulling from ACR with a user-assigned identity.'

param location string
param tags object
param appName string
param environmentId string
param identityId string
param registryLoginServer string

@description('Container image reference. Defaults to a placeholder for first provision; azd deploy swaps it.')
param image string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container listening port.')
param targetPort int

@description('Expose the app to the internet (frontend) or keep it internal (backend).')
param external bool

@description('Plain environment variables passed to the container.')
param env array = []

@secure()
@description('Optional AI Gateway runtime key for the backend, stored as a Container App secret.')
param gatewayApiKey string = ''

@description('The azd service name tag so azd can match and deploy to this app.')
param serviceName string

param cpu string = '0.5'
param memory string = '1.0Gi'

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, {
    'azd-service-name': serviceName
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: empty(gatewayApiKey) ? [] : [
        {
          name: 'ai-gateway-key'
          value: gatewayApiKey
        }
      ]
      ingress: {
        external: external
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: serviceName
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: env
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

output appId string = containerApp.id
output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
