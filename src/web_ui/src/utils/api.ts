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

/** Fired when the API answers 401: the session expired or the account was signed out elsewhere. */
export const UNAUTHORIZED_EVENT = "examen:unauthorized";

let installed = false;

/**
 * Sends the session cookie with every API request (needed when the dashboard runs on `next dev`,
 * a different origin than the API) and reports 401 answers so the dashboard can show the sign-in
 * screen. Installed once by the root page; components keep calling plain `fetch`.
 */
export const installCredentialedFetch = (): void => {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const base = getApiBaseUrl();
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    // Only our own API gets the cookie: never attach credentials to third-party URLs
    const isApi =
      url.startsWith("/api/") ||
      (base !== "" && url.startsWith(`${base}/api/`)) ||
      url.startsWith(`${window.location.origin}/api/`);
    const res = await original(input, isApi ? { credentials: "include", ...init } : init);
    if (isApi && res.status === 401 && !url.includes("/api/auth/")) {
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    return res;
  };
};
