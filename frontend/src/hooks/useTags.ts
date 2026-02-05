import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  tagsApi,
  type CreateTagRequest,
  type UpdateTagRequest,
  type BulkTagRequest,
} from "@/lib/api/tags";

export function useTags(workspaceId: string) {
  return useQuery({
    queryKey: ["tags", workspaceId],
    queryFn: () => tagsApi.list(workspaceId),
    enabled: !!workspaceId,
  });
}

export function useCreateTag(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateTagRequest) => tagsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags", workspaceId] });
    },
  });
}

export function useUpdateTag(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { tagId: string; data: UpdateTagRequest }) =>
      tagsApi.update(workspaceId, variables.tagId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags", workspaceId] });
    },
  });
}

export function useDeleteTag(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (tagId: string) => tagsApi.delete(workspaceId, tagId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
    },
  });
}

export function useBulkTagContacts(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BulkTagRequest) => tagsApi.bulkTag(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
    },
  });
}
