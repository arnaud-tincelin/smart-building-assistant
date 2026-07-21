// Thin API client for the BuildingAssist backend.

import { endpoint } from "./config";

export interface Citation {
  title: string;
  url: string;
  snippet: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
}

export async function ask(question: string): Promise<AskResponse> {
  const resp = await fetch(endpoint("/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `Request failed with status ${resp.status}`);
  }

  return (await resp.json()) as AskResponse;
}
