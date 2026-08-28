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

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(endpoint(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

export async function ask(question: string): Promise<AskResponse> {
  return post<AskResponse>("/ask", { question });
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
