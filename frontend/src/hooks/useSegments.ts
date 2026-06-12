import { useQuery } from "@tanstack/react-query";

import { useDebounce } from "@/hooks/useDebounce";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { segmentsApi } from "@/lib/api/segments";
import { queryKeys } from "@/lib/query-keys";
import type { FilterDefinition } from "@/types";

const {
  queryKeys: segmentQueryKeys,
  useList: useSegments,
  useGet: useSegment,
  useCreate: useCreateSegment,
  useUpdate: useUpdateSegment,
  useDelete: useDeleteSegment,
} = createResourceHooks({
  resourceKey: "segments",
  apiClient: segmentsApi,
});

export { segmentQueryKeys, useSegments, useSegment, useCreateSegment, useUpdateSegment, useDeleteSegment };

export function useSegmentContacts(workspaceId: string, segmentId: string) {
  return useQuery({
    queryKey: queryKeys.segments.contacts(workspaceId, segmentId),
    queryFn: () => segmentsApi.getContacts(workspaceId, segmentId),
    enabled: !!workspaceId && !!segmentId,
  });
}

/**
 * Live count of contacts matching an unsaved filter definition.
 * Debounced so it doesn't fire on every keystroke while building rules.
 */
export function useSegmentPreview(
  workspaceId: string,
  definition: FilterDefinition | null,
) {
  const debounced = useDebounce(
    definition ? JSON.stringify(definition) : null,
    400,
  );
  const hasRules = !!definition && definition.rules.length > 0;

  return useQuery({
    queryKey: queryKeys.segments.preview(workspaceId, debounced),
    queryFn: () => segmentsApi.preview(workspaceId, definition as FilterDefinition),
    enabled: !!workspaceId && hasRules && debounced !== null,
  });
}
