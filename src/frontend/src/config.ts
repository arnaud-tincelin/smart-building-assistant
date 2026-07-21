// Runtime configuration read from public/config.js (window global), which the
// container entrypoint renders from the BACKEND_URL env var. Falls back to the
// Vite dev proxy (/api) when no backend URL is provided.

interface BuildingAssistConfig {
  backendUrl?: string;
}

declare global {
  interface Window {
    BUILDINGASSIST_CONFIG?: BuildingAssistConfig;
  }
}

const backendUrl = (window.BUILDINGASSIST_CONFIG?.backendUrl ?? "").replace(/\/$/, "");

export function endpoint(path: string): string {
  return backendUrl ? `${backendUrl}${path}` : `/api${path}`;
}
