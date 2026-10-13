// Dynamic API base URL resolution.
// - Static export served by the FastMCP backend (any port, e.g. :8042) -> same origin ("").
// - `next dev` on :3000 -> backend at NEXT_PUBLIC_BACKEND_PORT (default 8042, matching MCP_PORT in .env).
const DEV_SERVER_PORT = "3000";
const DEFAULT_BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT || "8042";

export const getApiBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined" && window.location.port === DEV_SERVER_PORT) {
    return `http://${window.location.hostname}:${DEFAULT_BACKEND_PORT}`;
  }
  return "";
};
