"use client";

import { useSetupChecklist } from "@/hooks/useSetupChecklist";

export interface SetupStatus {
  isLoading: boolean;
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
 * Conservative on errors: if any probe fails we treat the workspace as
 * configured (`needsSetup: false`) rather than nagging on unknown state.
 */
export function useSetupStatus(): SetupStatus {
  const { workspaceId, isLoading, isError, allComplete } = useSetupChecklist();

  const needsSetup = !!workspaceId && !isLoading && !isError && !allComplete;

  return {
    isLoading,
    needsSetup,
    workspaceId,
  };
}
