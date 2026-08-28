metadata description = 'Log Analytics workspace + Application Insights for the BuildingAssist demo.'

param location string
param tags object
param logAnalyticsName string
param appInsightsName string

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: any({
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    AzureMonitorWorkspaceIngestionMode: 'Enabled'
  })
}

output logAnalyticsName string = logAnalytics.name
output appInsightsId string = appInsights.id
@secure()
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsName string = appInsights.name
output appInsightsAppId string = appInsights.properties.AppId
