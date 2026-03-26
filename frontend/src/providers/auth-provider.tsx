"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { getCurrentUser, login as loginApi, type User, type LoginCredentials } from "@/lib/api/auth";
import { getToken, setToken, removeToken } from "@/lib/utils/storage";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  workspaceId: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
}

const AuthContext = React.createContext<AuthContextType | undefined>(undefined);

const PUBLIC_PATHS = ["/login", "/register"];
const PUBLIC_PATH_PREFIXES = ["/invite/", "/p/"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const isAuthenticated = user !== null;

  const fetchUser = React.useCallback(async () => {
    const token = getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      const userData = await getCurrentUser();
      setUser(userData);
    } catch {
      removeToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  React.useEffect(() => {
    if (isLoading) return;

    const isPublicPath =
      PUBLIC_PATHS.includes(pathname) ||
      PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix));

    if (!isAuthenticated && !isPublicPath) {
      router.replace("/login");
    } else if (isAuthenticated && PUBLIC_PATHS.includes(pathname)) {
      // Only redirect away from explicit public paths (login/register), not invite pages
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  const login = React.useCallback(async (credentials: LoginCredentials) => {
    const response = await loginApi(credentials);
    // Only access_token is in the response body; refresh_token is set as httpOnly cookie by backend
    setToken(response.access_token);
    const userData = await getCurrentUser();
    setUser(userData);
    router.replace("/");
  }, [router]);

  const logout = React.useCallback(() => {
    removeToken();
    // Clear the httpOnly refresh cookie on the backend
    api.post("/api/v1/auth/logout").catch(() => {});
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value = React.useMemo(
    () => ({
      user,
      isLoading,
      isAuthenticated,
      workspaceId: user?.default_workspace_id ?? null,
      login,
      logout,
    }),
    [user, isLoading, isAuthenticated, login, logout]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
