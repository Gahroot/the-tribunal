"use client";

import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { campaignsApi } from "@/lib/api/campaigns";
import { contactsApi } from "@/lib/api/contacts";
import { integrationsApi } from "@/lib/api/integrations";
import { phoneNumbersApi } from "@/lib/api/phone-numbers";
import { queryKeys } from "@/lib/query-keys";
import { useWorkspace } from "@/providers/workspace-provider";

export type SetupStepId = "phone" | "agent" | "contacts" | "calendar" | "campaign";

/** Static copy/targets for one checklist row. Completion is derived separately. */
export interface SetupStepDefinition {
  id: SetupStepId;
  title: string;
  description: string;
  /** Deep link straight to the screen where this step happens. */
  href: string;
}

/**
 * What a live check proved about one step:
 *  - `done`    — the probe (or its last good cached result) proves it is done
 *  - `todo`    — the probe proves it is not done yet
 *  - `unknown` — the probe failed and there is no earlier good result, so we
 *                cannot say either way (never shown as done OR as missing)
 */
export type SetupStepState = "done" | "todo" | "unknown";

export interface SetupStep extends SetupStepDefinition {
  /** True only when a live API response proves the step is done — never faked. */
  done: boolean;
  state: SetupStepState;
  /**
   * The latest check failed but an earlier successful result is still shown
   * (last known progress), so `state` may be out of date.
   */
  stale: boolean;
}

/**
 * Overall setup outcome, kept separate from "incomplete" and "complete" so a
 * failed probe is never read as success or as zero resources:
 *  - `loading`    — the first results have not arrived yet
 *  - `incomplete` — at least one step is proven not done
 *  - `unknown`    — no step is proven missing, but some could not be checked
 *  - `complete`   — every step is proven done
 */
export type SetupChecklistPhase = "loading" | "incomplete" | "unknown" | "complete";

export interface SetupChecklistStatus {
  workspaceId: string | null;
  /** True while the workspace (or any probe) has not resolved its first data. */
  isLoading: boolean;
  status: SetupChecklistPhase;
  /** True when any probe's latest check failed (with or without cached data). */
  isError: boolean;
  /** Steps whose latest check failed — the ones `retry()` re-checks. */
  failedStepIds: SetupStepId[];
  /** Steps that could not be checked at all (failed with no cached result). */
  unknownCount: number;
  /** True while a retry of failed checks is in flight. */
  isRetrying: boolean;
  /** Re-run only the failed checks. Never called automatically. */
  retry: () => void;
  steps: SetupStep[];
  completedCount: number;
  total: number;
  allComplete: boolean;
}

/**
 * The persistent "Finish setup" checklist.
 *
 * Each step checks real workspace state through the same public APIs the app
 * already uses (mirroring the backend's cold-start guidance where it exists):
 *
 *  1. phone     — an active, SMS-capable phone number exists
 *                 (backend's delivery prerequisite in SetupPrerequisiteService)
 *  2. agent     — the workspace has at least one agent (any active state)
 *  3. contacts  — the workspace has imported at least one contact
 *  4. calendar  — usable credentials and a booking calendar for the default agent
 *  5. campaign  — at least one campaign has left draft (i.e. it was launched)
 *
 * Mutations for each resource invalidate these same query keys, so the
 * checklist updates as soon as the user finishes a step elsewhere; the short
 * staleTime only covers changes made outside this client.
 */
export const SETUP_STEP_DEFINITIONS: readonly SetupStepDefinition[] = [
  {
    id: "phone",
    title: "Connect a phone number",
    description: "Add an SMS-enabled number so the AI can text and call leads.",
    href: "/phone-numbers",
  },
  {
    id: "agent",
    title: "Create your first agent",
    description: "Your AI rep answers, qualifies, and books meetings.",
    href: "/agents/create",
  },
  {
    id: "contacts",
    title: "Import contacts",
    description: "Upload a CSV or sync a CRM to fill your pipeline.",
    // Opens the CSV import dialog on arrival (ContactsPage strips the flag).
    href: "/contacts?import=true",
  },
  {
    id: "calendar",
    title: "Connect your calendar",
    description: "Connect Cal.com and configure your default agent's booking calendar.",
    href: "/settings?tab=integrations",
  },
  {
    id: "campaign",
    title: "Send your first campaign",
    description: "Launch SMS or voice outreach to your leads.",
    href: "/campaigns/new",
  },
];

// A failed probe must never take down the page it sits on (the checklist also
// renders in the app shell) — failures are shown inline with a retry instead of
// escalating to the app-wide error boundary (`throwOnError: false`). Mounting
// another checklist must not silently re-fire a failed probe either
// (`retryOnMount: false`); only the explicit retry does.

// Setup state only changes through explicit actions whose mutations invalidate
// these keys, so a short staleTime is enough to stay honest without polling.
const SETUP_STALE_TIME_MS = 30_000;

// page_size 1 probes: we only need existence (total > 0), never the rows
// themselves — except campaigns, where we must see a status.
const PHONE_PROBE_PARAMS = { page: 1, page_size: 1, active_only: true, sms_enabled: true } as const;
const AGENT_PROBE_PARAMS = { page: 1, page_size: 1, active_only: false } as const;
const CONTACT_PROBE_PARAMS = { page: 1, page_size: 1 } as const;
const CAMPAIGN_PROBE_PARAMS = { page: 1, page_size: 100 } as const;

export function useSetupChecklist(): SetupChecklistStatus {
  const { currentWorkspaceId, isPending: workspacePending } = useWorkspace();
  const workspaceId = currentWorkspaceId;
  const enabled = !!workspaceId;
  const staleTime = SETUP_STALE_TIME_MS;

  const phoneQuery = useQuery({
    queryKey: queryKeys.phoneNumbers.list(workspaceId ?? "", PHONE_PROBE_PARAMS),
    queryFn: () => phoneNumbersApi.list(workspaceId!, PHONE_PROBE_PARAMS),
    enabled,
    staleTime,
    throwOnError: false,
    retryOnMount: false,
  });

  const agentQuery = useQuery({
    queryKey: queryKeys.agents.list(workspaceId ?? "", AGENT_PROBE_PARAMS),
    queryFn: () => agentsApi.list(workspaceId!, AGENT_PROBE_PARAMS),
    enabled,
    staleTime,
    throwOnError: false,
    retryOnMount: false,
  });

  const contactQuery = useQuery({
    queryKey: queryKeys.contacts.list(workspaceId ?? "", CONTACT_PROBE_PARAMS),
    queryFn: () => contactsApi.list(workspaceId!, CONTACT_PROBE_PARAMS),
    enabled,
    staleTime,
    throwOnError: false,
    retryOnMount: false,
  });

  const integrationQuery = useQuery({
    queryKey: queryKeys.integrations.bookingReadiness(workspaceId ?? ""),
    queryFn: () => integrationsApi.bookingReadiness(workspaceId!),
    enabled,
    staleTime,
    throwOnError: false,
    retryOnMount: false,
  });

  const campaignQuery = useQuery({
    queryKey: queryKeys.campaigns.list(workspaceId ?? "", CAMPAIGN_PROBE_PARAMS),
    queryFn: () => campaignsApi.list(workspaceId!, CAMPAIGN_PROBE_PARAMS),
    enabled,
    staleTime,
    throwOnError: false,
    retryOnMount: false,
  });

  const probeById = {
    phone: phoneQuery,
    agent: agentQuery,
    contacts: contactQuery,
    calendar: integrationQuery,
    campaign: campaignQuery,
  } satisfies Record<SetupStepId, unknown>;
  const probes = Object.values(probeById);

  // TanStack Query puts a data-less errored query back into `pending` while it
  // refetches, so "pending" alone cannot tell a first load from a retry. A probe
  // that has failed before and still has no data stays unknown (not loading)
  // until a retry actually succeeds — otherwise the card would flash back to
  // its skeleton (and the shell gate would unmount it) on every retry.
  const hasNoResult = (probe: (typeof probes)[number]) =>
    probe.data === undefined && (probe.isError || probe.errorUpdateCount > 0);
  const hasFailed = (probe: (typeof probes)[number]) => probe.isError || hasNoResult(probe);

  const isLoading =
    workspacePending ||
    (enabled && probes.some((probe) => probe.isPending && !hasNoResult(probe)));
  const isError = probes.some(hasFailed);

  // Computed only from data that actually arrived. A failed probe with no data
  // stays undefined here (unknown) rather than collapsing to "zero resources".
  const doneById: Record<SetupStepId, boolean | undefined> = {
    phone: phoneQuery.data ? phoneQuery.data.total > 0 : undefined,
    agent: agentQuery.data ? agentQuery.data.total > 0 : undefined,
    contacts: contactQuery.data ? contactQuery.data.total > 0 : undefined,
    calendar: integrationQuery.data?.ready,
    campaign: campaignQuery.data
      ? campaignQuery.data.items.some((campaign) => campaign.status !== "draft")
      : undefined,
  };

  const steps: SetupStep[] = SETUP_STEP_DEFINITIONS.map((step) => {
    const probe = probeById[step.id];
    const done = doneById[step.id];
    // Only a failed check is unknown; without a workspace the probes never run
    // and the steps keep reading as not-yet-done, as before.
    const state: SetupStepState =
      done === undefined ? (hasNoResult(probe) ? "unknown" : "todo") : done ? "done" : "todo";
    return {
      ...step,
      ...(step.id === "calendar" && integrationQuery.data
        ? { description: integrationQuery.data.description, href: integrationQuery.data.href }
        : {}),
      done: state === "done",
      state,
      stale: probe.isError && done !== undefined,
    };
  });
  const completedCount = steps.filter((step) => step.state === "done").length;
  const unknownCount = steps.filter((step) => step.state === "unknown").length;
  const total = steps.length;
  const failedStepIds = SETUP_STEP_DEFINITIONS.filter((step) =>
    hasFailed(probeById[step.id]),
  ).map((step) => step.id);
  const isRetrying = probes.some((probe) => hasFailed(probe) && probe.isFetching);

  const status: SetupChecklistPhase = isLoading
    ? "loading"
    : steps.some((step) => step.state === "todo")
      ? "incomplete"
      : unknownCount > 0
        ? "unknown"
        : "complete";

  // Re-check only the failed probes; healthy sections keep their data. The
  // caller triggers this explicitly (button), so it cannot loop on its own.
  const retry = () => {
    for (const probe of probes) {
      if (hasFailed(probe) && !probe.isFetching) void probe.refetch();
    }
  };

  return {
    workspaceId,
    isLoading,
    status,
    isError,
    failedStepIds,
    unknownCount,
    isRetrying,
    retry,
    steps,
    completedCount,
    total,
    allComplete: status === "complete",
  };
}
