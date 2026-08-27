"""Application configuration, loaded from environment variables.

Everything the backend needs is injected as env vars by the Container App (see
`infra/`). No secrets or keys live here — the app authenticates to Azure with a
user-assigned managed identity via ``DefaultAzureCredential``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from .agent_policy import AGENT_INSTRUCTIONS


class Settings(BaseSettings):
    """Runtime settings for the BuildingAssist backend."""

    model_config = SettingsConfigDict(
        env_prefix="BUILDINGASSIST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure AI Foundry project endpoint, e.g.
    # https://<account>.services.ai.azure.com/api/projects/<project>
    project_endpoint: str = ""

    # The model deployment the agent reasons with.
    model_deployment: str = "model-router"

    # Prompt agent created by the postprovision hook. Empty uses direct Responses tools.
    agent_name: str = "buildingassist-agent"

    # Authenticated Azure AI Search Knowledge Base MCP endpoint (Foundry IQ).
    knowledge_mcp_endpoint: str = ""

    # Public Streamable HTTP endpoint for the simulated building-operations MCP server.
    mcp_server_url: str = ""

    # System instructions for the agent.
    instructions: str = AGENT_INSTRUCTIONS

    # Client-side OpenTelemetry; server-side agent tracing is controlled by the
    # Foundry project's Application Insights connection.
    enable_tracing: bool = False

    # Managed identity client id (user-assigned). Empty => system-assigned / default.
    azure_client_id: str = ""

    # CORS: comma-separated list of allowed frontend origins. "*" allows all.
    allowed_origins: str = "*"

    # Hosts and browser origins accepted by the public MCP Streamable HTTP endpoint.
    mcp_allowed_hosts: str = "localhost,localhost:*,127.0.0.1,127.0.0.1:*,testserver"
    mcp_allowed_origins: str = "http://localhost:*,http://127.0.0.1:*"

    # When true, skip the real Foundry call and return a canned answer. Handy for
    # local development and tests without Azure credentials.
    use_mock_agent: bool = False

    @property
    def origins_list(self) -> list[str]:
        """Parse ``allowed_origins`` into a list for the CORS middleware."""
        raw = self.allowed_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]

    @property
    def mcp_allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.mcp_allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
