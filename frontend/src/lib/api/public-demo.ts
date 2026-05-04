import axios, { AxiosError } from "axios";

// Use relative URL in browser (proxied through Next.js), direct URL on server
const API_URL =
  typeof window !== "undefined"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL?.replace(/\\n$/, "").replace(/\n$/, "") ?? "http://localhost:8000");

// Create a separate axios instance without auth interceptors for public endpoints
const publicApi = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// Helper to extract error message from axios errors
function extractErrorMessage(error: unknown): string {
  if (error instanceof AxiosError && error.response?.data) {
    // FastAPI returns error details in the "detail" field
    const detail = error.response.data.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return "Something went wrong. Please try again.";
}

// Types
export interface DemoRequest {
  phone_number: string;
}

export interface DemoResponse {
  success: boolean;
  message: string;
}

// Public Demo API (no auth required)
export const publicDemoApi = {
  triggerCall: async (phoneNumber: string): Promise<DemoResponse> => {
    try {
      const response = await publicApi.post<DemoResponse>(
        "/api/v1/p/demo/call",
        {
          phone_number: phoneNumber,
        }
      );
      return response.data;
    } catch (error) {
      throw new Error(extractErrorMessage(error));
    }
  },

  triggerText: async (phoneNumber: string): Promise<DemoResponse> => {
    try {
      const response = await publicApi.post<DemoResponse>(
        "/api/v1/p/demo/text",
        {
          phone_number: phoneNumber,
        }
      );
      return response.data;
    } catch (error) {
      throw new Error(extractErrorMessage(error));
    }
  },
};
