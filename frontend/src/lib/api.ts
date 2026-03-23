import axios, { type AxiosRequestConfig } from "axios";
import { safeGetItem, safeSetItem, safeRemoveItem } from "./utils/storage";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
  timeout: 30000,
});

// Logout function
export function logout(): void {
  safeRemoveItem("access_token");
  safeRemoveItem("refresh_token");
  try {
    window.location.href = "/login";
  } catch (navError) {
    console.error("Failed to redirect to login:", navError);
  }
}

// Request interceptor for adding auth token
api.interceptors.request.use(
  (config) => {
    const token = safeGetItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

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

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
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

      const refreshTokenValue = safeGetItem("refresh_token");

      if (!refreshTokenValue) {
        // No refresh token, logout
        console.error("No refresh token available - redirecting to login");
        logout();
        return Promise.reject(error);
      }

      try {
        // Attempt to refresh the token
        const response = await api.post("/api/v1/auth/refresh", {
          refresh_token: refreshTokenValue,
        });

        const { access_token, refresh_token } = response.data;

        // Store new tokens
        safeSetItem("access_token", access_token);
        safeSetItem("refresh_token", refresh_token);

        // Update authorization header
        originalRequest.headers.Authorization = `Bearer ${access_token}`;

        // Process queued requests
        processQueue(null);
        isRefreshing = false;

        // Retry original request
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
