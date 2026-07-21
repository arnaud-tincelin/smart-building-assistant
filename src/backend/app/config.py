"""Application configuration, loaded from environment variables.

Everything the backend needs is injected as env vars by the Container App (see
`infra/`). No secrets or keys live here — the app authenticates to Azure with a
user-assigned managed identity via ``DefaultAzureCredential``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INSTRUCTIONS = (
    "You are BuildingAssist, an assistant for Contoso Energy's smart buildings. "
    "Answer questions about building energy use concisely and factually. When a "
    "knowledge source is available, ground your answer in it and cite the source. "
    "If you don't have the data, say so plainly."
)


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
    model_deployment: str = "gpt-4.1-mini"

    # Name of the Foundry IQ knowledge (vector store) to ground answers on. The
    # backend resolves it to an id at runtime, so no id needs to be wired in.
    knowledge_name: str = "buildingassist-knowledge"

    # System instructions for the agent.
    instructions: str = DEFAULT_INSTRUCTIONS

    # Managed identity client id (user-assigned). Empty => system-assigned / default.
    azure_client_id: str = ""

    # CORS: comma-separated list of allowed frontend origins. "*" allows all.
    allowed_origins: str = "*"

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
