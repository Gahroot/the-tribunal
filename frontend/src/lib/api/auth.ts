import { apiGet, apiPost } from "@/lib/api";

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
  default_workspace_id: string | null;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export async function login(credentials: LoginCredentials): Promise<AuthResponse> {
  const formData = new URLSearchParams();
  formData.append("username", credentials.email);
  formData.append("password", credentials.password);

  return apiPost<AuthResponse>("/api/v1/auth/login", formData, {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });
}

export async function register(data: RegisterData): Promise<User> {
  return apiPost<User>("/api/v1/auth/register", data);
}

/**
 * Fetch the signed-in user. With `optional: true` a missing/expired session
 * rejects quietly instead of redirecting to /login (used on public pages that
 * merely want to recognize a signed-in visitor).
 */
export async function getCurrentUser(options?: { optional?: boolean }): Promise<User> {
  return apiGet<User>(
    "/api/v1/auth/me",
    options?.optional ? { skipAuthRedirect: true } : undefined
  );
}

export async function refreshToken(): Promise<AuthResponse> {
  // Refresh token is sent automatically via httpOnly cookie
  return apiPost<AuthResponse>("/api/v1/auth/refresh");
}
