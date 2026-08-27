import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "https://aif-62wgl4jumru6y.services.ai.azure.com/api/projects/buildingassist")
print(f"Connecting to endpoint: {endpoint}")

try:
    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    print("Project client created.")
    # List agents or get agent buildingassist-agent
    agents = client.agents.list_agents()
    print("Agents in project:")
    for agent in agents.data:
        print(f"- {agent.name} (id: {agent.id})")
except Exception as e:
    print(f"Error: {e}")
