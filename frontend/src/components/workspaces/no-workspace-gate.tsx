"use client";

import { AlertCircle, Building2, Plus, RefreshCw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CreateWorkspaceDialog } from "@/components/workspaces/create-workspace-dialog";
import { useWorkspace } from "@/providers/workspace-provider";

/**
 * Workspace-list gate for the authenticated shell (finding RF-001).
 *
 * Workspace-scoped pages gate their queries on `enabled: !!workspaceId`, so
 * without a workspace they would sit on their loading skeleton forever. This
 * gate keeps the workspace-list states apart:
 * - loading: render children so pages keep their own loading skeletons;
 * - unavailable: the request failed with nothing loaded — explain the outage
 *   and offer a retry (never a "create workspace" prompt);
 * - empty: the server confirmed zero workspaces — offer workspace creation;
 * - ready: render children; if a later refresh failed, keep the loaded
 *   workspace and show a non-blocking notice with retry.
 */
export function NoWorkspaceGate({ children }: { children: ReactNode }) {
  const { status, refreshFailed, isFetching, retry } = useWorkspace();
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  if (status === "loading") {
    return <>{children}</>;
  }

  if (status === "unavailable") {
    return (
      <div
        role="alert"
        className="flex min-h-full flex-col items-center justify-center gap-6 px-6 py-16 text-center"
      >
        <div className="flex size-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
          <AlertCircle className="size-7" />
        </div>
        <div className="max-w-md space-y-2">
          <h1 className="text-2xl font-semibold">We couldn&apos;t load your workspaces</h1>
          <p className="text-muted-foreground">
            Something went wrong while reaching the server. Your workspaces and
            data are safe. Check your connection and try again.
          </p>
        </div>
        <Button size="lg" onClick={retry} disabled={isFetching}>
          <RefreshCw className={isFetching ? "size-4 animate-spin" : "size-4"} />
          {isFetching ? "Retrying…" : "Try again"}
        </Button>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <>
        {refreshFailed ? (
          <div className="px-6 pt-4">
            <Alert className="mx-auto max-w-5xl">
              <AlertCircle className="size-4" />
              <AlertTitle>Couldn&apos;t refresh your workspaces</AlertTitle>
              <AlertDescription className="flex flex-wrap items-center justify-between gap-3 text-muted-foreground">
                <span>
                  You&apos;re still in your current workspace. Workspace details
                  may be out of date.
                </span>
                <Button variant="outline" size="sm" onClick={retry} disabled={isFetching}>
                  {isFetching ? "Retrying…" : "Try again"}
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        ) : null}
        {children}
      </>
    );
  }

  // status === "empty": the server confirmed this account has no workspaces.

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 px-6 py-16 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-sm">
        <Building2 className="size-7" />
      </div>
      <div className="max-w-md space-y-2">
        <h1 className="text-2xl font-semibold">Create your workspace</h1>
        <p className="text-muted-foreground">
          You don&apos;t belong to a workspace yet. Create one to start capturing
          leads, running campaigns, and booking appointments.
        </p>
      </div>
      <Button size="lg" onClick={() => setCreateDialogOpen(true)}>
        <Plus className="size-4" />
        Create workspace
      </Button>

      <CreateWorkspaceDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </div>
  );
}
