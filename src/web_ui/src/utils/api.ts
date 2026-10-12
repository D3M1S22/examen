// Dynamic API base URL resolution (supports localhost:3000 / other dev ports -> localhost:8000 backend)
export const getApiBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    if (window.location.port && window.location.port !== "8000") {
      return `http://${window.location.hostname}:8000`;
    }
  }
  return "";
};
