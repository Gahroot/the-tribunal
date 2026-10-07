"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardPaste,
  ExternalLink,
  Key,
  Loader2,
  Plug,
  Settings,
} from "lucide-react";
import { useCallback, useId, useState } from "react";
import { useFormContext } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/status-badge";
import { connectFub, verifyFub } from "@/lib/api/realtor";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";

import type { OnboardingFormValues } from "../_state";

import { InstructionStep } from "./instruction-step";
import { useFubConnection } from "./onboarding-context";

interface FubStepProps {
  /** The workspace this guided setup targets; the key is saved there. */
  workspaceId: string | null;
  onSkip?: () => void;
}

type ConnectPhase = "idle" | "verifying" | "saving";

export function FubStep({ workspaceId, onSkip }: FubStepProps) {
  const form = useFormContext<OnboardingFormValues>();
  const queryClient = useQueryClient();
  const connection = useFubConnection(workspaceId);
  const apiKeyId = useId();
  const [phase, setPhase] = useState<ConnectPhase>("idle");
  const [testError, setTestError] = useState<string | null>(null);

  const { register, getValues } = form;
  const error = form.formState.errors.fub_api_key?.message;

  const handleConnect = useCallback(async () => {
    if (!workspaceId) {
      setTestError("No workspace selected. Pick a workspace, then try again.");
      return;
    }
    const apiKey = getValues("fub_api_key").trim();
    if (!apiKey) {
      toast.error("Paste your Follow Up Boss API key first.");
      return;
    }
    setTestError(null);

    // 1. Verify the key. A bad key or an outage writes nothing, so any
    //    previously saved connection stays as it was.
    setPhase("verifying");
    try {
      const result = await verifyFub(apiKey);
      if (!result.valid) {
        setTestError("That API key didn't work. Double-check and try again.");
        setPhase("idle");
        return;
      }
    } catch (err) {
      setTestError(getApiErrorMessage(err, "Couldn't check the key. Try again."));
      setPhase("idle");
      return;
    }

    // 2. Save it on the selected workspace. Only a successful save counts as
    //    connected; the status shown below comes from the saved record.
    setPhase("saving");
    try {
      const saved = await connectFub(workspaceId, apiKey);
      queryClient.setQueryData(
        queryKeys.realtor.fubConnection(workspaceId),
        saved
      );
      toast.success(
        saved.account_name
          ? `Connected as ${saved.account_name}`
          : "Follow Up Boss connected!"
      );
    } catch (err) {
      setTestError(
        getApiErrorMessage(
          err,
          "Your key works, but we couldn't save the connection. Try again."
        )
      );
    } finally {
      setPhase("idle");
    }
  }, [workspaceId, getValues, queryClient]);

  const busy = phase !== "idle";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Connect Your CRM</h2>
        <p className="text-muted-foreground mt-1">
          Optional: connect Follow Up Boss to import CRM leads, or skip this and
          upload a CSV instead.
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          How to find your API key:
        </p>
        <div className="space-y-2">
          <InstructionStep
            icon={ExternalLink}
            title="Log into Follow Up Boss"
            link="https://app.followupboss.com"
            linkLabel="Open Follow Up Boss"
          />
          <InstructionStep
            icon={Settings}
            title="Click Admin in the top menu, then click API"
          />
          <InstructionStep icon={Key} title="Copy your API key" />
          <InstructionStep icon={ClipboardPaste} title="Paste it below" />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={apiKeyId}>Follow Up Boss API Key (optional)</Label>
        <div className="relative">
          <Key className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id={apiKeyId}
            type="password"
            placeholder="fub_api_••••••••••••••••"
            className="pl-9"
            {...register("fub_api_key")}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <p className="text-xs text-muted-foreground">
          Don&apos;t use Follow Up Boss? Leave this blank and continue to upload a
          CSV.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={handleConnect}
          disabled={busy || !workspaceId}
        >
          {busy ? (
            <Loader2 className="size-4 mr-2 animate-spin" />
          ) : (
            <Plug className="size-4 mr-2" />
          )}
          {phase === "verifying"
            ? "Checking key..."
            : phase === "saving"
              ? "Saving connection..."
              : connection.connected
                ? "Reconnect"
                : "Connect"}
        </Button>

        {onSkip && (
          <Button type="button" variant="ghost" onClick={onSkip}>
            Skip (I don&apos;t use Follow Up Boss)
          </Button>
        )}

        {connection.connected && (
          <StatusBadge dotClass="bg-success">
            <CheckCircle2 className="size-3.5" />
            {connection.accountName
              ? `Connected as ${connection.accountName}`
              : "Connected"}
          </StatusBadge>
        )}

        {connection.checkFailed && (
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t check the saved connection.{" "}
            <button
              type="button"
              className="underline underline-offset-4"
              onClick={() => void connection.refetch()}
            >
              Check again
            </button>
          </p>
        )}

        {!workspaceId && (
          <p className="text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="size-3.5 shrink-0" />
            No workspace selected. Pick a workspace to connect Follow Up Boss.
          </p>
        )}

        {testError && (
          <p className="text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="size-3.5 shrink-0" />
            {testError}
          </p>
        )}
      </div>
    </div>
  );
}
