import axios, { type AxiosRequestConfig } from "axios";

import { getBackendUrl } from "@/lib/utils/backend-url";

// Use relative URL so requests are proxied through Next.js rewrites (no CORS issues)
// Fallback to direct backend URL for non-browser environments (SSR, tests)
const API_URL =
  typeof window !== "undefined"
    ? "" // Browser: use Next.js proxy
    : getBackendUrl(); // Server: direct

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  // Both access_token and refresh_token are httpOnly cookies set by the
  // backend. ``withCredentials`` is required so the browser includes them on
  // every API call. JS never reads, stores, or forwards the tokens itself —
  // an XSS payload cannot exfiltrate them.
  withCredentials: true,
  timeout: 30000,
});

// Logout — backend clears the httpOnly access + refresh cookies.
export function logout(): void {
  // Fire-and-forget: ask backend to clear the auth cookies.
  api.post("/api/v1/auth/logout").catch(() => {});
  try {
    window.location.href = "/login";
  } catch (navError) {
    console.error("Failed to redirect to login:", navError);
  }
}

// Track if we're currently refreshing to prevent multiple refresh attempts
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

const processQueue = (error: Error | null = null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve();
    }
  });
  failedQueue = [];
};

// Response interceptor for handling errors and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Never try to refresh on the refresh endpoint itself — that would loop.
    const requestUrl: string = originalRequest?.url ?? "";
    const isRefreshCall = requestUrl.includes("/api/v1/auth/refresh");

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry && !isRefreshCall) {
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then(() => {
            return api(originalRequest);
          })
          .catch((err) => {
            return Promise.reject(err);
          });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Attempt to refresh — refresh token is sent automatically via httpOnly cookie.
        // The new access cookie is set in the response; nothing for JS to store.
        await api.post("/api/v1/auth/refresh");

        // Process queued requests
        processQueue(null);
        isRefreshing = false;

        // Retry original request — the browser will attach the new access cookie.
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout
        processQueue(error);
        isRefreshing = false;
        console.error("Token refresh failed - redirecting to login");
        logout();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Typed wrapper helpers — return response.data directly, eliminating boilerplate
export const apiGet = <T>(url: string, config?: AxiosRequestConfig): Promise<T> =>
  api.get<T>(url, config).then((r) => r.data);

export const apiPost = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> =>
  api.post<T>(url, data, config).then((r) => r.data);

export const apiPut = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> =>
  api.put<T>(url, data, config).then((r) => r.data);

export const apiPatch = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> =>
  api.patch<T>(url, data, config).then((r) => r.data);

export const apiDelete = <T = void>(url: string, config?: AxiosRequestConfig): Promise<T> =>
  api.delete<T>(url, config).then((r) => r.data);

export default api;
