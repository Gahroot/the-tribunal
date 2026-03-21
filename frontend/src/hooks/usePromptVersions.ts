import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { promptVersionsApi, type VersionComparisonResponse } from "@/lib/api/prompt-versions";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/lib/utils/errors";

export const promptVersionQueryKeys = {
  comparison: (workspaceId: string, agentId: string) =>
    ["promptVersionComparison", workspaceId, agentId] as const,
  allComparisons: (workspaceId: string) =>
    ["promptVersionComparison", workspaceId] as const,
};

export function usePromptComparison(workspaceId: string, agentId: string) {
  return useQuery<VersionComparisonResponse>({
    queryKey: promptVersionQueryKeys.comparison(workspaceId ?? "", agentId),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return promptVersionsApi.compare(workspaceId, agentId);
    },
    enabled: !!workspaceId && !!agentId,
    refetchInterval: 60000,
  });
}

export function useActivateVersion(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (versionId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return promptVersionsApi.activate(workspaceId, agentId, versionId);
    },
    onSuccess: () => {
      toast.success("Winner declared! Other versions deactivated.");
      void queryClient.invalidateQueries({ queryKey: ["promptVersionComparison"] });
      void queryClient.invalidateQueries({ queryKey: ["promptVersions"] });
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to declare winner")),
  });
}

export function usePauseVersion(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (versionId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return promptVersionsApi.pause(workspaceId, agentId, versionId);
    },
    onSuccess: () => {
      toast.success("Version paused");
      void queryClient.invalidateQueries({ queryKey: ["promptVersionComparison"] });
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to pause version")),
  });
}

export function useResumeVersion(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (versionId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return promptVersionsApi.resume(workspaceId, agentId, versionId);
    },
    onSuccess: () => {
      toast.success("Version resumed");
      void queryClient.invalidateQueries({ queryKey: ["promptVersionComparison"] });
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to resume version")),
  });
}

export function useEliminateVersion(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (versionId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return promptVersionsApi.eliminate(workspaceId, agentId, versionId);
    },
    onSuccess: () => {
      toast.success("Version eliminated from testing");
      void queryClient.invalidateQueries({ queryKey: ["promptVersionComparison"] });
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to eliminate version")),
  });
}
