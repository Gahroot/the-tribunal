"use client";

import { type SetupChecklistPhase, useSetupChecklist } from "@/hooks/useSetupChecklist";

export interface SetupStatus {
  isLoading: boolean;
  status: SetupChecklistPhase;
  needsSetup: boolean;
  workspaceId: string | null;
}

/**
 * Lightweight view over {@link useSetupChecklist} for the app shell.
 *
 * `needsSetup` is true while ANY step of the persistent setup checklist is
 * incomplete (first agent, phone number, contacts, calendar, campaign), so the
 * sidebar's "Finish setup" entry (`setupNavItem` → `/onboarding`) stays visible
 * for as long as setup has work left — not just until the first agent exists.
 *
 * Unknown status (a probe failed and no step is proven missing) also keeps the
 * entry visible: `/onboarding` is where the user can see what could not be
 * checked and retry, and a failure is never read as "setup complete".
 */
export function useSetupStatus(): SetupStatus {
  const { workspaceId, isLoading, status } = useSetupChecklist();

  const needsSetup = !!workspaceId && (status === "incomplete" || status === "unknown");

  return {
    isLoading,
    status,
    needsSetup,
    workspaceId,
  };
}
