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

export interface SetupStep extends SetupStepDefinition {
  /** True only when a live API response proves the step is done — never faked. */
  done: boolean;
}

export interface SetupChecklistStatus {
  workspaceId: string | null;
  /** True while the workspace (or any probe) has not resolved its first data. */
  isLoading: boolean;
  /** True when any probe failed — callers should hide rather than guess state. */
  isError: boolean;
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
 *  4. calendar  — an active Cal.com integration is connected
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
    href: "/contacts",
  },
  {
    id: "calendar",
    title: "Connect your calendar",
    description: "Let leads book time with you through Cal.com.",
    href: "/settings?tab=integrations",
  },
  {
    id: "campaign",
    title: "Send your first campaign",
    description: "Launch SMS or voice outreach to your leads.",
    href: "/campaigns/new",
  },
];

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
  });

  const agentQuery = useQuery({
    queryKey: queryKeys.agents.list(workspaceId ?? "", AGENT_PROBE_PARAMS),
    queryFn: () => agentsApi.list(workspaceId!, AGENT_PROBE_PARAMS),
    enabled,
    staleTime,
  });

  const contactQuery = useQuery({
    queryKey: queryKeys.contacts.list(workspaceId ?? "", CONTACT_PROBE_PARAMS),
    queryFn: () => contactsApi.list(workspaceId!, CONTACT_PROBE_PARAMS),
    enabled,
    staleTime,
  });

  const integrationQuery = useQuery({
    queryKey: queryKeys.integrations.all(workspaceId ?? ""),
    queryFn: () => integrationsApi.list(workspaceId!),
    enabled,
    staleTime,
  });

  const campaignQuery = useQuery({
    queryKey: queryKeys.campaigns.list(workspaceId ?? "", CAMPAIGN_PROBE_PARAMS),
    queryFn: () => campaignsApi.list(workspaceId!, CAMPAIGN_PROBE_PARAMS),
    enabled,
    staleTime,
  });

  const probes = [phoneQuery, agentQuery, contactQuery, integrationQuery, campaignQuery];
  const isLoading =
    workspacePending || (enabled && probes.some((probe) => probe.isPending));
  const isError = probes.some((probe) => probe.isError);

  const doneById: Record<SetupStepId, boolean> = {
    phone: (phoneQuery.data?.total ?? 0) > 0,
    agent: (agentQuery.data?.total ?? 0) > 0,
    contacts: (contactQuery.data?.total ?? 0) > 0,
    calendar: (integrationQuery.data ?? []).some(
      (integration) => integration.integration_type === "calcom" && integration.is_active,
    ),
    campaign: (campaignQuery.data?.items ?? []).some(
      (campaign) => campaign.status !== "draft",
    ),
  };

  const steps = SETUP_STEP_DEFINITIONS.map((step) => ({
    ...step,
    done: doneById[step.id],
  }));
  const completedCount = steps.filter((step) => step.done).length;
  const total = steps.length;

  return {
    workspaceId,
    isLoading,
    isError,
    steps,
    completedCount,
    total,
    allComplete: total > 0 && completedCount === total,
  };
}
