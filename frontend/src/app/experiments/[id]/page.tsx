"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Play,
  Pause,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Settings2,
  FlaskConical,
  Users,
} from "lucide-react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TestAnalytics } from "@/components/experiments/test-analytics";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { messageTestsApi } from "@/lib/api/message-tests";
import type { MessageTestStatus } from "@/types";

const statusColors: Record<MessageTestStatus, string> = {
  draft: "bg-gray-500/10 text-gray-500 border-gray-500/20",
  running: "bg-green-500/10 text-green-500 border-green-500/20",
  paused: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  completed: "bg-purple-500/10 text-purple-500 border-purple-500/20",
};

export default function ExperimentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  const testId = params.id as string;

  const {
    data: test,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["message-test", workspaceId, testId],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.get(workspaceId, testId);
    },
    enabled: !!workspaceId && !!testId,
  });

  const startMutation = useMutation({
    mutationFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.start(workspaceId, testId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["message-test", workspaceId, testId],
      });
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test started");
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Failed to start test"),
  });

  const pauseMutation = useMutation({
    mutationFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.pause(workspaceId, testId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["message-test", workspaceId, testId],
      });
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test paused");
    },
    onError: () => toast.error("Failed to pause test"),
  });

  const completeMutation = useMutation({
    mutationFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.complete(workspaceId, testId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["message-test", workspaceId, testId],
      });
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test completed");
    },
    onError: () => toast.error("Failed to complete test"),
  });

  if (isLoading) {
    return (
      <AppSidebar>
        <div className="flex items-center justify-center h-screen">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
        </div>
      </AppSidebar>
    );
  }

  if (error || !test) {
    return (
      <AppSidebar>
        <div className="flex flex-col items-center justify-center h-screen gap-4">
          <AlertCircle className="size-12 text-destructive" />
          <h2 className="text-xl font-semibold">Experiment not found</h2>
          <Button variant="outline" onClick={() => router.push("/experiments")}>
            Back to Experiments
          </Button>
        </div>
      </AppSidebar>
    );
  }

  return (
    <AppSidebar>
      <div className="flex flex-col h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push("/experiments")}
          >
            <ArrowLeft className="size-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold">{test.name}</h1>
              <Badge variant="outline" className={statusColors[test.status]}>
                {test.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {test.description || "No description"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {test.status === "draft" && (
            <Button onClick={() => startMutation.mutate()}>
              <Play className="size-4 mr-2" />
              Start Test
            </Button>
          )}
          {test.status === "running" && (
            <>
              <Button variant="outline" onClick={() => pauseMutation.mutate()}>
                <Pause className="size-4 mr-2" />
                Pause
              </Button>
              <Button onClick={() => completeMutation.mutate()}>
                <CheckCircle2 className="size-4 mr-2" />
                Complete
              </Button>
            </>
          )}
          {test.status === "paused" && (
            <>
              <Button variant="outline" onClick={() => startMutation.mutate()}>
                <Play className="size-4 mr-2" />
                Resume
              </Button>
              <Button onClick={() => completeMutation.mutate()}>
                <CheckCircle2 className="size-4 mr-2" />
                Complete
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-6">
        <Tabs defaultValue="analytics" className="space-y-6">
          <TabsList>
            <TabsTrigger value="analytics" className="flex items-center gap-2">
              <FlaskConical className="size-4" />
              Analytics
            </TabsTrigger>
            <TabsTrigger value="variants" className="flex items-center gap-2">
              <Settings2 className="size-4" />
              Variants
            </TabsTrigger>
            <TabsTrigger value="contacts" className="flex items-center gap-2">
              <Users className="size-4" />
              Contacts
            </TabsTrigger>
          </TabsList>

          <TabsContent value="analytics">
            <TestAnalytics testId={testId} />
          </TabsContent>

          <TabsContent value="variants">
            <div className="space-y-4">
              {test.variants?.map((variant) => (
                <Card key={variant.id}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {variant.name}
                      {variant.is_control && (
                        <Badge variant="secondary">Control</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="whitespace-pre-wrap bg-muted p-4 rounded-lg">
                      {variant.message_template}
                    </p>
                    <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t">
                      <div>
                        <p className="text-sm text-muted-foreground">Assigned</p>
                        <p className="text-lg font-semibold">
                          {variant.contacts_assigned}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Sent</p>
                        <p className="text-lg font-semibold">
                          {variant.messages_sent}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Replies</p>
                        <p className="text-lg font-semibold">
                          {variant.replies_received}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">
                          Response Rate
                        </p>
                        <p className="text-lg font-semibold">
                          {variant.response_rate.toFixed(1)}%
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="contacts">
            <Card>
              <CardHeader>
                <CardTitle>Test Contacts</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold">{test.total_contacts}</p>
                    <p className="text-sm text-muted-foreground">Total</p>
                  </div>
                  <div className="p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold">{test.messages_sent}</p>
                    <p className="text-sm text-muted-foreground">Sent</p>
                  </div>
                  <div className="p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold">
                      {test.total_contacts - test.messages_sent}
                    </p>
                    <p className="text-sm text-muted-foreground">Pending</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
      </div>
    </AppSidebar>
  );
}
