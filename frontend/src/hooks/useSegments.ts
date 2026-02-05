import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  segmentsApi,
  type CreateSegmentRequest,
  type UpdateSegmentRequest,
} from "@/lib/api/segments";

export function useSegments(workspaceId: string) {
  return useQuery({
    queryKey: ["segments", workspaceId],
    queryFn: () => segmentsApi.list(workspaceId),
    enabled: !!workspaceId,
  });
}

export function useSegment(workspaceId: string, segmentId: string) {
  return useQuery({
    queryKey: ["segment", workspaceId, segmentId],
    queryFn: () => segmentsApi.get(workspaceId, segmentId),
    enabled: !!workspaceId && !!segmentId,
  });
}

export function useCreateSegment(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateSegmentRequest) => segmentsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments", workspaceId] });
    },
  });
}

export function useUpdateSegment(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { segmentId: string; data: UpdateSegmentRequest }) =>
      segmentsApi.update(workspaceId, variables.segmentId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments", workspaceId] });
    },
  });
}

export function useDeleteSegment(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (segmentId: string) => segmentsApi.delete(workspaceId, segmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments", workspaceId] });
    },
  });
}

export function useSegmentContacts(workspaceId: string, segmentId: string) {
  return useQuery({
    queryKey: ["segment-contacts", workspaceId, segmentId],
    queryFn: () => segmentsApi.getContacts(workspaceId, segmentId),
    enabled: !!workspaceId && !!segmentId,
  });
}
