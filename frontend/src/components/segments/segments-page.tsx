"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Layers, RefreshCw, Trash2, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import { useDeleteSegment, useSegments } from "@/hooks/useSegments";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { segmentsApi } from "@/lib/api/segments";
import { queryKeys } from "@/lib/query-keys";
import { formatRelative } from "@/lib/utils/date";
import { formatNumber } from "@/lib/utils/number";

export function SegmentsPage() {
  const workspaceId = useWorkspaceId();
  const router = useRouter();
  const queryClient = useQueryClient();

  const {
    data: segmentsData,
    isPending,
    error,
    refetch,
  } = useSegments(workspaceId ?? "");

  const deleteSegment = useDeleteSegment(workspaceId ?? "");

  const refreshSegment = useMutation({
    mutationFn: (segmentId: string) =>
      segmentsApi.refresh(workspaceId ?? "", segmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.segments.all(workspaceId ?? ""),
      });
      toast.success("Segment refreshed");
    },
    onError: () => toast.error("Failed to refresh segment"),
  });

  const handleDelete = async (segmentId: string, name: string) => {
    if (!window.confirm(`Delete segment "${name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteSegment.mutateAsync(segmentId);
      toast.success("Segment deleted");
    } catch {
      toast.error("Failed to delete segment");
    }
  };

  const segments = segmentsData?.items ?? [];

  return (
    <AppSidebar>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Layers className="size-6" />
              Segments
            </h1>
            <p className="text-muted-foreground">
              Saved contact filters you can reuse across campaigns and lists.
            </p>
          </div>
        </div>

        {!workspaceId || isPending ? (
          <PageLoadingState message="Loading segments…" />
        ) : error ? (
          <PageErrorState
            message="Failed to load segments."
            onRetry={() => refetch()}
          />
        ) : segments.length === 0 ? (
          <PageEmptyState
            icon={<Layers className="size-8" />}
            title="No segments yet"
            description="Build a filter on the Contacts page and choose “Save as Segment” to create one."
            action={
              <Button variant="outline" onClick={() => router.push("/contacts")}>
                Go to Contacts
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {segments.map((segment) => (
              <Card key={segment.id} className="flex flex-col">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{segment.name}</CardTitle>
                    {segment.is_dynamic && (
                      <Badge variant="secondary">Dynamic</Badge>
                    )}
                  </div>
                  {segment.description && (
                    <CardDescription>{segment.description}</CardDescription>
                  )}
                </CardHeader>
                <CardContent className="flex-1 space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Users className="size-4" />
                    <span>{formatNumber(segment.contact_count)} contacts</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {segment.definition.rules.length} rule
                    {segment.definition.rules.length !== 1 ? "s" : ""} ·{" "}
                    {segment.definition.logic === "or"
                      ? "Match any"
                      : "Match all"}
                  </p>
                  {segment.last_computed_at && (
                    <p className="text-xs text-muted-foreground">
                      Updated {formatRelative(segment.last_computed_at)}
                    </p>
                  )}
                </CardContent>
                <CardFooter className="gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => refreshSegment.mutate(segment.id)}
                    disabled={
                      refreshSegment.isPending &&
                      refreshSegment.variables === segment.id
                    }
                  >
                    <RefreshCw
                      className={
                        refreshSegment.isPending &&
                        refreshSegment.variables === segment.id
                          ? "size-4 animate-spin"
                          : "size-4"
                      }
                    />
                    Refresh
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleDelete(segment.id, segment.name)}
                    disabled={deleteSegment.isPending}
                  >
                    <Trash2 className="size-4" />
                    Delete
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppSidebar>
  );
}
