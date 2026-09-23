"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { SetupChecklist } from "@/components/onboarding/setup-checklist";
import { useSetupChecklist } from "@/hooks/useSetupChecklist";
import { dismissSetupCard, isSetupCardDismissed } from "@/lib/onboarding-status";

/**
 * Persistent first-run setup checklist (replaces the old force-redirect into
 * the onboarding wizard — finding RF-002).
 *
 * Renders the "Finish setup" card at the top of the authenticated shell while
 * the workspace's checklist is incomplete (and, after completion, until the
 * celebration banner is dismissed). Every step checks live workspace state and
 * links straight to its screen; `/onboarding` renders the same card full-page,
 * which is what the sidebar's `setupNavItem` entry point now points at.
 */
export function SetupGate() {
  const { workspaceId, isLoading, isError } = useSetupChecklist();
  const pathname = usePathname();
  const [hidden, setHidden] = useState(false);

  // Hooks run unconditionally above; from here on we decide what to render:
  // /onboarding already renders the checklist full-page — never stack a
  // second copy on top of it.
  if (pathname.startsWith("/onboarding")) return null;
  // While probes are in flight (or failing) we can't prove real state, so we
  // render nothing rather than a misleading card.
  if (isLoading || isError || !workspaceId) return null;
  if (hidden || isSetupCardDismissed(workspaceId)) return null;
  // Once every step is done the same card keeps rendering as the completion
  // celebration ("You're all set!") until the user dismisses it.

  return (
    <div className="border-b px-6 py-4">
      <div className="mx-auto max-w-5xl">
        <SetupChecklist
          onDismiss={() => {
            dismissSetupCard(workspaceId);
            setHidden(true);
          }}
        />
      </div>
    </div>
  );
}
