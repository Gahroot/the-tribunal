import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { promptVersionsApi, type VersionComparisonResponse } from "@/lib/api/prompt-versions";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { toast } from "sonner";

export const promptVersionQueryKeys = {
  comparison: (workspaceId: string, agentId: string) =>
    ["promptVersionComparison", workspaceId, agentId] as const,
  allComparisons: (workspaceId: string) =>
    ["promptVersionComparison", workspaceId] as const,
};

export function usePromptComparison(agentId: string) {
  const workspaceId = useWorkspaceId();

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

export function useActivateVersion(agentId: string) {
  const workspaceId = useWorkspaceId();
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
    onError: () => toast.error("Failed to declare winner"),
  });
}

export function usePauseVersion(agentId: string) {
  const workspaceId = useWorkspaceId();
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
    onError: () => toast.error("Failed to pause version"),
  });
}

export function useResumeVersion(agentId: string) {
  const workspaceId = useWorkspaceId();
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
    onError: () => toast.error("Failed to resume version"),
  });
}

export function useEliminateVersion(agentId: string) {
  const workspaceId = useWorkspaceId();
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
    onError: () => toast.error("Failed to eliminate version"),
  });
}
