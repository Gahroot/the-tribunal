/**
 * Centralized React Query key factory.
 *
 * Inspired by TkDodo's "Effective React Query Keys" — each resource exposes
 * builder functions that return `readonly` tuples, so invalidation, prefetch,
 * and cache access all share a single source of truth.
 *
 * @example
 * ```ts
 * import { queryKeys } from "@/lib/query-keys";
 *
 * useQuery({
 *   queryKey: queryKeys.contacts.detail(workspaceId, contactId),
 *   queryFn: () => fetchContact(contactId),
 * });
 *
 * // Invalidate every contact query for a workspace
 * queryClient.invalidateQueries({ queryKey: queryKeys.contacts.all(workspaceId) });
 * ```
 *
 * NOTE: migration of inline keys is incremental — see follow-up PRs. Existing
 * components still use ad-hoc string arrays; prefer this factory for all new code.
 */

type Key = readonly unknown[];

const resource = <Name extends string>(name: Name) => ({
  all: (workspaceId: string) => [name, workspaceId] as const,
  list: (workspaceId: string, params?: Record<string, unknown>) =>
    (params ? ([name, workspaceId, "list", params] as const) : ([name, workspaceId, "list"] as const)) as Key,
  detail: (workspaceId: string, id: string) => [name, workspaceId, "detail", id] as const,
});

export const queryKeys = {
  agents: {
    ...resource("agents"),
    versions: (workspaceId: string, agentId: string) =>
      ["agents", workspaceId, "detail", agentId, "versions"] as const,
  },
  appointments: resource("appointments"),
  auth: {
    currentUser: () => ["auth", "currentUser"] as const,
    session: () => ["auth", "session"] as const,
  },
  automations: resource("automations"),
  billing: {
    all: (workspaceId: string) => ["billing", workspaceId] as const,
    subscription: (workspaceId: string) => ["billing", workspaceId, "subscription"] as const,
    invoices: (workspaceId: string) => ["billing", workspaceId, "invoices"] as const,
    usage: (workspaceId: string) => ["billing", workspaceId, "usage"] as const,
  },
  calls: {
    ...resource("calls"),
    transcript: (workspaceId: string, callId: string) =>
      ["calls", workspaceId, "detail", callId, "transcript"] as const,
  },
  campaignReports: resource("campaign-reports"),
  campaigns: resource("campaigns"),
  contacts: {
    ...resource("contacts"),
    timeline: (workspaceId: string, contactId: string) =>
      ["contacts", workspaceId, "detail", contactId, "timeline"] as const,
    conversations: (workspaceId: string, contactId: string) =>
      ["contacts", workspaceId, "detail", contactId, "conversations"] as const,
    tags: (workspaceId: string, contactId: string) =>
      ["contacts", workspaceId, "detail", contactId, "tags"] as const,
  },
  conversations: {
    ...resource("conversations"),
    messages: (workspaceId: string, conversationId: string) =>
      ["conversations", workspaceId, "detail", conversationId, "messages"] as const,
  },
  dashboard: {
    all: (workspaceId: string) => ["dashboard", workspaceId] as const,
    stats: (workspaceId: string) => ["dashboard", workspaceId, "stats"] as const,
    activity: (workspaceId: string) => ["dashboard", workspaceId, "activity"] as const,
  },
  findLeadsAi: resource("find-leads-ai"),
  humanProfiles: resource("human-profiles"),
  improvementSuggestions: resource("improvement-suggestions"),
  integrations: resource("integrations"),
  invitations: resource("invitations"),
  knowledgeDocuments: resource("knowledge-documents"),
  leadMagnets: resource("lead-magnets"),
  leadSources: resource("lead-sources"),
  messageTemplates: resource("message-templates"),
  messageTests: resource("message-tests"),
  nudges: resource("nudges"),
  offers: resource("offers"),
  opportunities: resource("opportunities"),
  pendingActions: {
    ...resource("pending-actions"),
    count: (workspaceId: string) => ["pending-actions", workspaceId, "count"] as const,
  },
  phoneNumbers: resource("phone-numbers"),
  promptVersions: resource("prompt-versions"),
  publicDemo: {
    all: () => ["public-demo"] as const,
    detail: (slug: string) => ["public-demo", "detail", slug] as const,
  },
  publicOffers: {
    all: () => ["public-offers"] as const,
    detail: (slug: string) => ["public-offers", "detail", slug] as const,
  },
  realtor: {
    all: (workspaceId: string) => ["realtor", workspaceId] as const,
    onboarding: (workspaceId: string) => ["realtor", workspaceId, "onboarding"] as const,
  },
  scraping: resource("scraping"),
  segments: {
    ...resource("segments"),
    contacts: (workspaceId: string, segmentId: string) =>
      ["segments", workspaceId, "detail", segmentId, "contacts"] as const,
  },
  settings: {
    all: (workspaceId: string) => ["settings", workspaceId] as const,
    detail: (workspaceId: string, section: string) =>
      ["settings", workspaceId, "detail", section] as const,
  },
  smsCampaigns: resource("sms-campaigns"),
  tags: resource("tags"),
  voiceCampaigns: resource("voice-campaigns"),
  workspaces: {
    all: () => ["workspaces"] as const,
    detail: (workspaceId: string) => ["workspaces", "detail", workspaceId] as const,
    members: (workspaceId: string) => ["workspaces", "detail", workspaceId, "members"] as const,
  },
} as const;
