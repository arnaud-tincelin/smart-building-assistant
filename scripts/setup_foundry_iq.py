"""Create the BuildingAssist Foundry IQ Knowledge Base in Azure AI Search."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
    SearchableField,
    SearchFieldDataType,
    SearchIndex,
    SearchIndexFieldReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
)

SEARCH_API_VERSION = "2026-04-01"
KNOWLEDGE_BASE_API_VERSION = "2026-08-01-preview"
KNOWLEDGE_MCP_API_VERSION = KNOWLEDGE_BASE_API_VERSION
INDEX_NAME = os.environ.get(
    "BUILDINGASSIST_SEARCH_INDEX_NAME", "buildingassist-docs")
KNOWLEDGE_SOURCE_NAME = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_SOURCE_NAME", "buildingassist-docs-source"
)
KNOWLEDGE_BASE_NAME = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_NAME", "buildingassist-knowledge"
)
KNOWLEDGE_MODEL_DEPLOYMENT = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_MODEL_DEPLOYMENT", "gpt-5-mini"
)
KNOWLEDGE_MODEL_NAME = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_MODEL_NAME", "gpt-5-mini"
)
KNOWLEDGE_MODEL_RESOURCE_URI = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_MODEL_RESOURCE_URI", ""
)
SEMANTIC_CONFIGURATION_NAME = "buildingassist-semantic"
DOCS_DIR = pathlib.Path(os.environ.get("SAMPLE_DOCS_DIR", "sample-docs"))


def _document_chunks(docs_dir: pathlib.Path = DOCS_DIR) -> list[dict[str, str]]:
    documents = []
    for path in sorted(docs_dir.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        document_title = next(
            (line.removeprefix("# ").strip()
             for line in lines if line.startswith("# ")),
            path.stem,
        )
        sections: list[tuple[str, list[str]]] = []
        section_title = document_title
        section_lines: list[str] = []
        for line in lines:
            if line.startswith("## "):
                if any(part.strip() for part in section_lines):
                    sections.append((section_title, section_lines))
                section_title = line.removeprefix("## ").strip()
                section_lines = []
            elif not line.startswith("# "):
                section_lines.append(line)
        if any(part.strip() for part in section_lines):
            sections.append((section_title, section_lines))

        for index, (section_title, section_lines) in enumerate(sections, start=1):
            key_base = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
            documents.append(
                {
                    "id": f"{key_base}-{index:02d}",
                    "title": f"{document_title} - {section_title}",
                    "content": "\n".join(section_lines).strip(),
                    "source": f"sample-docs/{path.name}",
                }
            )
    return documents


def _search_index() -> SearchIndex:
    return SearchIndex(
        name=INDEX_NAME,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String,
                        key=True, filterable=True),
            SearchableField(name="title", analyzer_name="en.microsoft"),
            SearchableField(name="content", analyzer_name="en.microsoft"),
            SearchableField(name="source", filterable=True),
        ],
        semantic_search=SemanticSearch(
            default_configuration_name=SEMANTIC_CONFIGURATION_NAME,
            configurations=[
                SemanticConfiguration(
                    name=SEMANTIC_CONFIGURATION_NAME,
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ],
        ),
    )


def _knowledge_source() -> SearchIndexKnowledgeSource:
    return SearchIndexKnowledgeSource(
        name=KNOWLEDGE_SOURCE_NAME,
        description="Stable Contoso building facts and simulated operating policies.",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=INDEX_NAME,
            semantic_configuration_name=SEMANTIC_CONFIGURATION_NAME,
            search_fields=[
                SearchIndexFieldReference(name="title"),
                SearchIndexFieldReference(name="content"),
            ],
            source_data_fields=[
                SearchIndexFieldReference(name="id"),
                SearchIndexFieldReference(name="title"),
                SearchIndexFieldReference(name="content"),
                SearchIndexFieldReference(name="source"),
            ],
        ),
    )


def _knowledge_base() -> KnowledgeBase:
    return KnowledgeBase(
        name=KNOWLEDGE_BASE_NAME,
        description="BuildingAssist portfolio knowledge for grounded agent answers.",
        knowledge_sources=[KnowledgeSourceReference(
            name=KNOWLEDGE_SOURCE_NAME)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=KNOWLEDGE_MODEL_RESOURCE_URI,
                    deployment_name=KNOWLEDGE_MODEL_DEPLOYMENT,
                    model_name=KNOWLEDGE_MODEL_NAME,
                )
            )
        ],
    )


def _knowledge_base_preview_payload(document: dict) -> dict:
    document["retrievalReasoningEffort"] = {"kind": "low"}
    document["outputMode"] = "extractiveData"
    return document


def _knowledge_mcp_endpoint(endpoint: str) -> str:
    knowledge_base_name = urllib.parse.quote(KNOWLEDGE_BASE_NAME, safe="")
    return (
        f"{endpoint.rstrip('/')}/knowledgebases/{knowledge_base_name}/mcp"
        f"?api-version={KNOWLEDGE_MCP_API_VERSION}"
    )


def _apply_knowledge_base_preview_settings(
    endpoint: str, credential: DefaultAzureCredential
) -> None:
    knowledge_base_name = urllib.parse.quote(KNOWLEDGE_BASE_NAME, safe="")
    url = (
        f"{endpoint.rstrip('/')}/knowledgebases/{knowledge_base_name}"
        f"?api-version={KNOWLEDGE_BASE_API_VERSION}"
    )
    token = credential.get_token("https://search.azure.com/.default").token
    headers = {"Authorization": f"Bearer {token}"}
    get_request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(get_request, timeout=60) as response:
        payload = _knowledge_base_preview_payload(json.load(response))

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=60):
        pass


def main() -> int:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    if not endpoint:
        print(
            "AZURE_SEARCH_ENDPOINT is not set - skipping Foundry IQ setup.", file=sys.stderr)
        return 0
    if not KNOWLEDGE_MODEL_RESOURCE_URI:
        print(
            "BUILDINGASSIST_KNOWLEDGE_MODEL_RESOURCE_URI is not set - "
            "skipping Foundry IQ setup.",
            file=sys.stderr,
        )
        return 0

    documents = _document_chunks()
    if not documents:
        print(
            f"No docs found in {DOCS_DIR} - skipping Foundry IQ setup.", file=sys.stderr)
        return 0

    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=endpoint,
        credential=credential,
        api_version=SEARCH_API_VERSION,
    )
    index_client.create_or_update_index(_search_index())
    print(f"Created or updated search index {INDEX_NAME!r}.")

    search_client = SearchClient(
        endpoint=endpoint, index_name=INDEX_NAME, credential=credential)
    results = search_client.merge_or_upload_documents(documents)
    failures = [result for result in results if not result.succeeded]
    if failures:
        failed_keys = ", ".join(result.key for result in failures)
        raise RuntimeError(f"Failed to index knowledge chunks: {failed_keys}")
    print(f"Indexed {len(documents)} knowledge chunks.")

    index_client.create_or_update_knowledge_source(_knowledge_source())
    index_client.create_or_update_knowledge_base(_knowledge_base())
    _apply_knowledge_base_preview_settings(endpoint, credential)
    print(
        f"Created or updated Foundry IQ knowledge base {KNOWLEDGE_BASE_NAME!r}.")
    print(
        "BUILDINGASSIST_KNOWLEDGE_MCP_ENDPOINT="
        f"{_knowledge_mcp_endpoint(endpoint)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
