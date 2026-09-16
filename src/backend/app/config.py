"""Application configuration, loaded from environment variables.

Everything the backend needs is injected as env vars by the Container App (see
`infra/`). No secrets or keys live here — the app authenticates to Azure with a
user-assigned managed identity via ``DefaultAzureCredential``.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .agent_policy import AGENT_INSTRUCTIONS, GATEWAY_INSTRUCTIONS


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

    gateway_model_endpoint: str = ""
    gateway_api_key: str = Field(default="", repr=False)
    gateway_model: str = "gpt-5-mini"
    gateway_instructions: str = GATEWAY_INSTRUCTIONS

    # Editing changes the shared deployment, so it requires an explicit opt-in.
    enable_router_control: bool = False
    model_deployment_resource_id: str = ""

    # Authenticated Azure AI Search Knowledge Base MCP endpoint (Foundry IQ).
    knowledge_mcp_endpoint: str = ""

    # APIM-hosted MCP endpoint for the gateway and direct Responses tools.
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

    # Runtime provider selected by deployment configuration. The demo supports
    # only the in-memory simulator; any other value is a platform fault.
    operations_source: str = "simulator"

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


settings = Settings()
