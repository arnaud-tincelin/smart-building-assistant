"""Post-provision setup for the BuildingAssist Foundry IQ knowledge.

Runs from the azd `postprovision` hook. Creates (idempotently, by name) a **vector
store** grounded on the sample building/energy docs. The backend resolves this store
by name at runtime and grounds answers on it via the Responses API's ``file_search``
tool — so nothing needs to be wired back into the running container.

Auth uses ``DefaultAzureCredential`` — locally this resolves to the azd/az login,
and the developer principal is granted ``Azure AI User`` on the Foundry account by
``infra/modules/rbac.bicep``.

Environment (provided by azd as infra outputs):
- ``AZURE_AI_PROJECT_ENDPOINT`` — the Foundry project endpoint.

Optional:
- ``BUILDINGASSIST_KNOWLEDGE_NAME`` — vector store name (default ``buildingassist-knowledge``).
- ``SAMPLE_DOCS_DIR`` — folder of *.md docs to ground on (default ``sample-docs``).
"""

from __future__ import annotations

import os
import pathlib
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

KNOWLEDGE_NAME = os.environ.get("BUILDINGASSIST_KNOWLEDGE_NAME", "buildingassist-knowledge")
DOCS_DIR = pathlib.Path(os.environ.get("SAMPLE_DOCS_DIR", "sample-docs"))


def _find_by_name(items, name: str):
    for item in items:
        if getattr(item, "name", None) == name:
            return item
    return None


def _ensure_vector_store(oai) -> str:
    """Create or reuse the knowledge vector store, uploading docs once."""
    store = _find_by_name(oai.vector_stores.list(), KNOWLEDGE_NAME)
    if store is None:
        store = oai.vector_stores.create(name=KNOWLEDGE_NAME)
        print(f"Created vector store {store.id} ({KNOWLEDGE_NAME})")
    else:
        print(f"Reusing vector store {store.id} ({KNOWLEDGE_NAME})")

    # Only upload if the store is empty, so re-runs don't duplicate files.
    total = getattr(getattr(store, "file_counts", None), "total", 0) or 0
    if total > 0:
        print(f"Vector store already has {total} file(s) — skipping upload.")
        return store.id

    docs = sorted(DOCS_DIR.glob("*.md"))
    if not docs:
        print(f"No docs found in {DOCS_DIR} — vector store left empty.")
        return store.id

    file_ids = []
    for path in docs:
        with path.open("rb") as fh:
            uploaded = oai.files.create(file=fh, purpose="assistants")
        file_ids.append(uploaded.id)
        print(f"Uploaded {path.name} -> {uploaded.id}")

    oai.vector_stores.file_batches.create_and_poll(
        vector_store_id=store.id, file_ids=file_ids
    )
    print(f"Attached {len(file_ids)} file(s) to vector store {store.id}")
    return store.id


def main() -> int:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        print("AZURE_AI_PROJECT_ENDPOINT is not set — skipping knowledge setup.", file=sys.stderr)
        return 0

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    oai = project.get_openai_client()

    store_id = _ensure_vector_store(oai)
    print(f"BUILDINGASSIST_KNOWLEDGE_ID={store_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
