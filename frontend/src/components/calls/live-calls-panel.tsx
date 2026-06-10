"use client";

import { useQuery } from "@tanstack/react-query";
import { Headphones, PhoneCall, Radio } from "lucide-react";
import { useState } from "react";

import { LiveCallSupervisor } from "@/components/calls/live-call-supervisor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { callsApi, type LiveCall } from "@/lib/api/calls";
import { queryKeys } from "@/lib/query-keys";

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/**
 * Live-call roster + supervision entry point.
 *
 * Polls the workspace's in-progress calls and, for each, exposes a "Supervise"
 * action that opens the listen / whisper / barge panel.
 */
export function LiveCallsPanel() {
  const workspaceId = useWorkspaceId();
  const [activeCall, setActiveCall] = useState<LiveCall | null>(null);

  const { data } = useQuery({
    queryKey: queryKeys.calls.live(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return callsApi.listLive(workspaceId);
    },
    enabled: Boolean(workspaceId),
    // Live roster: poll frequently so calls appear/disappear promptly.
    refetchInterval: 5000,
  });

  const liveCalls = data?.items ?? [];

  if (liveCalls.length === 0) {
    return null;
  }

  return (
    <Card className="border-success/40">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Radio className="h-4 w-4 text-success animate-pulse" />
          Live calls
          <Badge variant="secondary">{liveCalls.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {liveCalls.map((call) => (
          <div
            key={call.call_id}
            className="flex items-center justify-between gap-3 rounded-md border p-3"
          >
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex-shrink-0 size-9 rounded-full bg-primary/10 flex items-center justify-center">
                <PhoneCall className="size-4 text-primary" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {call.contact_name || call.contact_phone || "Unknown contact"}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {call.direction}
                  {call.agent_name ? ` · ${call.agent_name}` : ""} ·{" "}
                  {formatDuration(call.duration_seconds)}
                  {call.barged ? " · operator on call" : ""}
                  {call.supervisor_count > 0 ? ` · ${call.supervisor_count} watching` : ""}
                </div>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="gap-2 flex-shrink-0"
              onClick={() => setActiveCall(call)}
            >
              <Headphones className="h-4 w-4" />
              Supervise
            </Button>
          </div>
        ))}
      </CardContent>

      <LiveCallSupervisor
        open={activeCall !== null}
        onOpenChange={(open) => {
          if (!open) setActiveCall(null);
        }}
        workspaceId={workspaceId ?? ""}
        call={activeCall}
      />
    </Card>
  );
}
