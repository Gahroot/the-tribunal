"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
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
    getStoredWorkspaceId()
  );

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

  const setCurrentWorkspace = useCallback(
    (workspaceId: string) => {
      setSelectedWorkspaceId(workspaceId);
      setStoredWorkspaceId(workspaceId);
      // The membership list is user-scoped (not workspace-scoped), so carry it
      // across the cache wipe below; otherwise a failed refetch right after a
      // switch would drop the selection and look like an empty account.
      const membershipList = queryClient.getQueryData<WorkspaceWithMembership[]>(
        queryKeys.workspaces.all()
      );
      // Clear all cached queries when switching workspaces to ensure fresh data
      // Using clear() instead of invalidateQueries() to remove stale workspace data
      queryClient.clear();
      if (membershipList) {
        queryClient.setQueryData(queryKeys.workspaces.all(), membershipList);
        void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.all() });
      }
    },
    [queryClient]
  );

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
    ]
  );

  return <WorkspaceContext value={value}>{children}</WorkspaceContext>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
