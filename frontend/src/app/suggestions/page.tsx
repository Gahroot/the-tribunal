"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wand2, Lightbulb, Check, X, Clock } from "lucide-react";

import { improvementSuggestionsApi } from "@/lib/api/improvement-suggestions";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SuggestionsQueue } from "@/components/suggestions/suggestions-queue";

export default function SuggestionsPage() {
  const workspaceId = useWorkspaceId();
  const [statusFilter, setStatusFilter] = useState("pending");

  const { data: pendingCount } = useQuery({
    queryKey: ["suggestionsPendingCount", workspaceId],
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return improvementSuggestionsApi.getPendingCount(workspaceId);
    },
    enabled: !!workspaceId,
  });

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI Suggestions</h1>
          <p className="text-sm text-muted-foreground">
            Review and approve AI-generated prompt improvements
          </p>
        </div>
        {pendingCount && pendingCount.pending_count > 0 && (
          <div className="flex items-center gap-2 rounded-lg border bg-amber-50 px-4 py-2 dark:bg-amber-950/20">
            <Lightbulb className="h-5 w-5 text-amber-600" />
            <span className="text-sm font-medium">
              {pendingCount.pending_count} pending suggestion
              {pendingCount.pending_count !== 1 && "s"}
            </span>
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Pending</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{pendingCount?.pending_count ?? 0}</div>
            <p className="text-xs text-muted-foreground">Awaiting review</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Approved</CardTitle>
            <Check className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">All time</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Rejected</CardTitle>
            <X className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">All time</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Auto-Generated</CardTitle>
            <Wand2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">This month</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Suggestion Queue</CardTitle>
          <CardDescription>
            AI-generated prompt improvements based on call performance analysis
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={statusFilter} onValueChange={setStatusFilter}>
            <TabsList>
              <TabsTrigger value="pending">
                Pending
                {pendingCount && pendingCount.pending_count > 0 && (
                  <span className="ml-1.5 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs text-white">
                    {pendingCount.pending_count}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="approved">Approved</TabsTrigger>
              <TabsTrigger value="rejected">Rejected</TabsTrigger>
            </TabsList>

            <TabsContent value="pending" className="mt-4">
              <SuggestionsQueue statusFilter="pending" />
            </TabsContent>
            <TabsContent value="approved" className="mt-4">
              <SuggestionsQueue statusFilter="approved" />
            </TabsContent>
            <TabsContent value="rejected" className="mt-4">
              <SuggestionsQueue statusFilter="rejected" />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
