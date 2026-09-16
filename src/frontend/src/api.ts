// Thin API client for the BuildingAssist backend.

import { endpoint } from "./config";

export interface Citation {
  title: string;
  url: string;
  snippet: string;
}

export interface UsageInfo {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  cache_write_tokens: number;
}

export interface ExecutionInfo {
  selected_model?: string | null;
  routing_mode?: string | null;
  latency_ms?: number | null;
  response_id?: string | null;
  routing_explanation?: string | null;
  tools_used?: string[];
  usage?: UsageInfo | null;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  execution?: ExecutionInfo | null;
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

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(endpoint(path), {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

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

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, "POST", body);
}

export async function ask(question: string, scenario: string | null): Promise<AskResponse> {
  return post<AskResponse>("/ask", { question, scenario });
}

export async function requestAccess(
  accessRequest: AccessRequest,
): Promise<SecurityOperationResponse> {
  return post<SecurityOperationResponse>("/security/access-requests", accessRequest);
}

export async function checkInVisitor(
  visitorRequest: VisitorCheckInRequest,
): Promise<SecurityOperationResponse> {
  return post<SecurityOperationResponse>("/security/visitors/check-in", visitorRequest);
}

export async function getRoutingMode(): Promise<RoutingModeState> {
  return request<RoutingModeState>("/model-router/mode", "GET");
}

export async function setRoutingMode(mode: RoutingMode): Promise<RoutingModeState> {
  return request<RoutingModeState>("/model-router/mode", "PUT", { mode });
}
