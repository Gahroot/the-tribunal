"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { workspacesApi, type WorkspaceWithMembership } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/query-keys";
import { STATIC } from "@/lib/query-options";

import { useAuth } from "./auth-provider";
import { BrandSwitchBoundary } from "./brand-switch-boundary";

const WORKSPACE_STORAGE_KEY = "current_workspace_id";

/**
 * Lifecycle of the workspace-membership list (finding RF-001). These states
 * are deliberately distinct so a failed request is never mistaken for an
 * account with no workspaces:
 * - `loading`: no response yet (or not authenticated yet).
 * - `empty`: the server successfully answered with zero workspaces.
 * - `unavailable`: the request failed and there is no previously loaded list.
 * - `ready`: a list with at least one workspace is loaded. A later refresh may
 *   have failed (`refreshFailed`); the last good list and selection are kept.
 */
export type WorkspaceListStatus = "loading" | "empty" | "unavailable" | "ready";

interface WorkspaceContextType {
  workspaces: WorkspaceWithMembership[];
  currentWorkspace: WorkspaceWithMembership | null;
  currentWorkspaceId: string | null;
  status: WorkspaceListStatus;
  /** True only while the first workspace-list response is outstanding. */
  isPending: boolean;
  /** True while any workspace-list request (including a retry) is in flight. */
  isFetching: boolean;
  /** A refresh failed after a list had already loaded; that list is still shown. */
  refreshFailed: boolean;
  /** Last workspace-list error, or null. */
  error: Error | null;
  /** Re-request the workspace list. */
  retry: () => void;
  setCurrentWorkspace: (workspaceId: string) => void;
  /** Confirm membership before entering a newly created brand's setup. */
  activateCreatedWorkspace: (workspaceId: string) => Promise<void>;
}

const NO_WORKSPACES: WorkspaceWithMembership[] = [];

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

function getStoredWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(WORKSPACE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredWorkspaceId(workspaceId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId);
  } catch (error) {
    if (process.env.NODE_ENV !== "production") {
      console.error("Failed to save workspace ID:", error);
    }
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(() =>
    getStoredWorkspaceId(),
  );

  const [switchDestination, setSwitchDestination] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.workspaces.all(),
    queryFn: workspacesApi.list,
    enabled: isAuthenticated,
    ...STATIC,
  });
  const { data, error, isFetching, isRefetchError, refetch } = listQuery;

  // Never surface a cached list while signed out.
  const workspaces = isAuthenticated && data ? data : NO_WORKSPACES;

  // Data wins over error: a failed refresh keeps the last good list (and thus
  // the selected workspace) instead of collapsing to "no workspaces".
  let status: WorkspaceListStatus;
  if (!isAuthenticated) status = "loading";
  else if (data !== undefined) status = data.length > 0 ? "ready" : "empty";
  else if (listQuery.isError) status = "unavailable";
  else status = "loading";

  const isPending = status === "loading";
  const refreshFailed = isAuthenticated && data !== undefined && isRefetchError;
  const listError = isAuthenticated ? error : null;

  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const currentWorkspace = useMemo(() => {
    if (!isAuthenticated || workspaces.length === 0) return null;

    const selectedWorkspace = selectedWorkspaceId
      ? workspaces.find((w) => w.workspace.id === selectedWorkspaceId)
      : null;

    // Default is only a fallback, not the current-brand selection (RF-033).
    // RF-032's API projects one effective default even for legacy duplicates.
    return selectedWorkspace ?? workspaces.find((w) => w.is_default) ?? workspaces[0] ?? null;
  }, [isAuthenticated, selectedWorkspaceId, workspaces]);

  const currentWorkspaceId = currentWorkspace?.workspace.id ?? null;

  // Persist the resolved selection so a missing or stale stored id (e.g. a
  // workspace the user was removed from, or a brand-new user who just landed in
  // their auto-provisioned personal workspace) converges to a real id instead
  // of leaving the dashboard wedged on `null` (finding RF-001).
  useEffect(() => {
    if (currentWorkspaceId && currentWorkspaceId !== getStoredWorkspaceId()) {
      setStoredWorkspaceId(currentWorkspaceId);
    }
  }, [currentWorkspaceId]);

  const switchWorkspace = useCallback(
    (workspaceId: string, destination: string | null = null, refresh = true) => {
      // Accept only a permitted brand, and do not reset a same-brand session.
      if (
        workspaceId === currentWorkspaceId ||
        !queryClient.getQueryData<WorkspaceWithMembership[]>(queryKeys.workspaces.all())
          ?.some((w) => w.workspace.id === workspaceId)
      )
        return;
      setSwitchDestination(destination);
      setSelectedWorkspaceId(workspaceId);
      setStoredWorkspaceId(workspaceId);
      // The membership list is user-scoped, so retain its last good response
      // through the refresh; an outage must not collapse the selected brand.
      const membershipList = queryClient.getQueryData<WorkspaceWithMembership[]>(
        queryKeys.workspaces.all(),
      );
      // Remove queries, not mutations: legitimate old-brand server operations
      // remain alive and keep their original workspace-aware cache keys.
      // Membership and other user-scoped query data are not brand-owned.
      const brandQueries = {
        predicate: (query: { queryKey: readonly unknown[] }) =>
          query.queryKey.length > 1 && query.queryKey[1] === currentWorkspaceId,
      };
      void queryClient.cancelQueries(brandQueries);
      queryClient.removeQueries(brandQueries);
      if (membershipList) {
        queryClient.setQueryData(queryKeys.workspaces.all(), membershipList);
        if (refresh) void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.all() });
      }
    },
    [queryClient, currentWorkspaceId],
  );

  const setCurrentWorkspace = useCallback(
    (workspaceId: string) => switchWorkspace(workspaceId),
    [switchWorkspace],
  );

  const activateCreatedWorkspace = useCallback(async (workspaceId: string) => {
    // Do not invent membership/default flags from a WorkspaceResponse. The
    // authenticated list confirms access and RF-032's effective login default.
    await queryClient.cancelQueries({ queryKey: queryKeys.workspaces.all() });
    const result = await refetch({ throwOnError: true });
    if (!result.data?.some((membership) => membership.workspace.id === workspaceId)) {
      throw new Error("Created workspace is not in the membership list yet");
    }
    // This list is already fresh; avoid a second refresh racing the handoff.
    switchWorkspace(workspaceId, "/onboarding", false);
  }, [queryClient, refetch, switchWorkspace]);

  const value = useMemo(
    () => ({
      workspaces,
      currentWorkspace,
      currentWorkspaceId,
      status,
      isPending,
      isFetching: isAuthenticated && isFetching,
      refreshFailed,
      error: listError,
      retry,
      setCurrentWorkspace,
      activateCreatedWorkspace,
    }),
    [
      workspaces,
      currentWorkspace,
      currentWorkspaceId,
      status,
      isPending,
      isAuthenticated,
      isFetching,
      refreshFailed,
      listError,
      retry,
      setCurrentWorkspace,
      activateCreatedWorkspace,
    ],
  );

  return (
    <WorkspaceContext value={value}>
      <Suspense fallback={null}>
        <BrandSwitchBoundary workspaceId={currentWorkspaceId} switchDestination={switchDestination}>
          {children}
        </BrandSwitchBoundary>
      </Suspense>
    </WorkspaceContext>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
