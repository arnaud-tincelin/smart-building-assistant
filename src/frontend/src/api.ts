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
  execution?: ModelExecution | null;
}

export type AskMode = "agents" | "gateway";

export interface TokenUsage {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens: number | null;
  cached_tokens: number | null;
  cache_write_tokens: number | null;
}

export interface ModelExecution {
  mode: AskMode;
  requested_model: string;
  reported_model: string | null;
  selected_model: string | null;
  routing_mode: RoutingMode | null;
  latency_ms: number;
  response_id: string | null;
  usage: TokenUsage | null;
  tools_used: string[];
  routing_explanation: string;
}

export interface AccessRequest {
  building_id: string;
  access_point_id: string;
  credential_id: string;
  method: "badge" | "mobile";
}

export interface VisitorCheckInRequest {
  building_id: string;
  access_point_id: string;
  visitor_name: string;
  visitor_email: string;
  host_name: string;
  purpose: string;
}

export interface SecurityOperationResponse {
  id: string;
}

export type RoutingMode = "balanced" | "cost" | "quality";

export interface RoutingModeState {
  mode: RoutingMode;
  editable: boolean;
  explicitly_set?: boolean;
  model_name?: string;
  model_version?: string;
  model_subset?: string[];
  propagation_seconds?: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly incidentId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), options);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let incidentId: string | undefined;
    try {
      const payload = (await response.json()) as {
        detail?: string | { message?: string; incident_id?: string };
      };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail) {
        message = payload.detail.message || message;
        incidentId = payload.detail.incident_id;
      }
    } catch {
      // Keep the status-based fallback for non-JSON responses.
    }
    throw new ApiError(message, response.status, incidentId);
  }

  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export async function ask(
  question: string,
  mode: AskMode = "agents",
  signal?: AbortSignal,
): Promise<AskResponse> {
  return post<AskResponse>("/ask", { question, mode }, signal);
}

export async function getRoutingMode(signal?: AbortSignal): Promise<RoutingModeState> {
  return request<RoutingModeState>("/model-router/mode", { method: "GET", signal });
}

export async function setRoutingMode(mode: RoutingMode): Promise<RoutingModeState> {
  return request<RoutingModeState>("/model-router/mode", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
}

export async function requestAccess(
  request: AccessRequest,
): Promise<SecurityOperationResponse> {
  return post<SecurityOperationResponse>("/security/access-requests", request);
}

export async function checkInVisitor(
  request: VisitorCheckInRequest,
): Promise<SecurityOperationResponse> {
  return post<SecurityOperationResponse>("/security/visitors/check-in", request);
}
