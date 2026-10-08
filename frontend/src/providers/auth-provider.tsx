"use client";

import { useRouter, usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { PageErrorState, PageLoadingState } from "@/components/ui/page-state";
import { api, isUnauthorizedError } from "@/lib/api";
import { getCurrentUser, login as loginApi, type User, type LoginCredentials } from "@/lib/api/auth";
import { RETURN_TO_PARAM, buildLoginHref, getSafeReturnTo } from "@/lib/auth/return-to";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  workspaceId: string | null;
  /** Sign in, then go to `redirectTo` if it is a permitted local path, else "/". */
  login: (credentials: LoginCredentials, options?: { redirectTo?: string | null }) => Promise<void>;
  /** Sign out, then go to sign-in (carrying `redirectTo` back when permitted). */
  logout: (options?: { redirectTo?: string | null }) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const PUBLIC_PATHS = ["/login", "/register"];
const PUBLIC_PATH_PREFIXES = ["/invite/", "/p/"];
// Public pages that still want to recognize an existing session (finding
// RF-003): an invitation can be accepted in place by a signed-in teammate.
const OPTIONAL_AUTH_PATH_PREFIXES = ["/invite/"];

function isPublicPathname(pathname: string): boolean {
  return (
    PUBLIC_PATHS.includes(pathname) ||
    PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}

function isOptionalAuthPathname(pathname: string): boolean {
  return OPTIONAL_AUTH_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

/** Validated `?redirect=` destination of the current URL, if any. */
function currentReturnTo(): string | null {
  return getSafeReturnTo(new URLSearchParams(window.location.search).get(RETURN_TO_PARAM));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSessionUnavailable, setIsSessionUnavailable] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const isAuthenticated = user !== null;

  const fetchUser = useCallback(async () => {
    setIsLoading(true);
    setIsSessionUnavailable(false);
    setUser(null);
    // Invitation pages are public but must recognize a signed-in visitor so
    // they can offer "Accept" directly. Probe quietly: a signed-out visitor
    // just stays signed out instead of being bounced to /login.
    if (isOptionalAuthPathname(window.location.pathname)) {
      try {
        setUser(await getCurrentUser({ optional: true }));
      } catch {
        setUser(null);
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // Other public surfaces (login/register, /invite/, and all /p/ pages such as the
    // review rating-gate and offer landing pages) are visited by anonymous
    // users. Probing /auth/me there would 401 and trip the axios interceptor's
    // hard redirect to /login, breaking those public flows. Skip the probe and
    // resolve to signed-out so the public page renders.
    if (isPublicPathname(window.location.pathname)) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    // Auth tokens live in httpOnly cookies — JS can’t check for them. We just
    // probe /auth/me; if the cookie is missing or expired the response
    // interceptor will attempt a refresh, and a final 401 means signed-out.
    try {
      const userData = await getCurrentUser({ skipAuthRedirect: true });
      setUser(userData);
    } catch (error) {
      setUser(null);
      setIsSessionUnavailable(!isUnauthorizedError(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchUser();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [fetchUser]);

  useEffect(() => {
    if (isLoading || isSessionUnavailable) return;

    const isPublicPath = isPublicPathname(pathname);

    if (!isAuthenticated && !isPublicPath) {
      router.replace("/login");
    } else if (isAuthenticated && PUBLIC_PATHS.includes(pathname)) {
      // Only redirect away from explicit public paths (login/register), not
      // invite pages. Honour a permitted ?redirect= so signing in from an
      // invitation returns there instead of landing on the dashboard.
      router.replace(currentReturnTo() ?? "/");
    }
  }, [isAuthenticated, isLoading, isSessionUnavailable, pathname, router]);

  const login = useCallback(async (
    credentials: LoginCredentials,
    options?: { redirectTo?: string | null }
  ) => {
    // Backend sets both access_token and refresh_token as httpOnly cookies on
    // the response; the body is ignored here. Subsequent requests carry the
    // cookies automatically (axios is configured with withCredentials).
    await loginApi(credentials);
    const userData = await getCurrentUser();
    setUser(userData);
    setIsSessionUnavailable(false);
    router.replace(getSafeReturnTo(options?.redirectTo) ?? "/");
  }, [router]);

  const logout = useCallback((options?: { redirectTo?: string | null }) => {
    // Backend clears both auth cookies.
    api.post("/api/v1/auth/logout").catch(() => {});
    setUser(null);
    setIsSessionUnavailable(false);
    router.replace(buildLoginHref(options?.redirectTo));
  }, [router]);

  const value = useMemo(
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

  // Do not mount protected consumers (including query-cache readers) until
  // authorization succeeds. Public pages remain usable without a session.
  let content = children;
  if (!isPublicPathname(pathname)) {
    if (isLoading || !isAuthenticated) {
      content = isSessionUnavailable && !isLoading ? (
        <PageErrorState
          className="min-h-screen"
          role="alert"
          message="Service temporarily unavailable. We couldn't check your session. Check your connection and try again."
          onRetry={() => { void fetchUser(); }}
          retryLabel="Retry session check"
        />
      ) : (
        <PageLoadingState className="min-h-screen" role="status" message="Checking your session…" />
      );
    }
  }

  return <AuthContext value={value}>{content}</AuthContext>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
