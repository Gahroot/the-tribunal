import { create } from "zustand";
import type { Contact, TimelineItem, Agent, Automation, ContactAgent, FilterDefinition } from "@/types";
import type { ContactSortBy } from "@/lib/api/contacts";

interface ContactStore {
  // Selected contact
  selectedContact: Contact | null;
  setSelectedContact: (contact: Contact | null) => void;

  // Contacts list
  contacts: Contact[];
  setContacts: (contacts: Contact[]) => void;

  // Timeline items for selected contact
  timeline: TimelineItem[];
  setTimeline: (items: TimelineItem[]) => void;
  addTimelineItem: (item: TimelineItem) => void;
  clearTimeline: () => void;

  // Loading states
  isLoadingContacts: boolean;
  setIsLoadingContacts: (loading: boolean) => void;
  isLoadingTimeline: boolean;
  setIsLoadingTimeline: (loading: boolean) => void;

  // Search
  searchQuery: string;
  setSearchQuery: (query: string) => void;

  // Filters
  statusFilter: string | null;
  setStatusFilter: (status: string | null) => void;

  // Sorting
  sortBy: ContactSortBy;
  setSortBy: (sortBy: ContactSortBy) => void;

  // Advanced filters
  filters: FilterDefinition | null;
  setFilters: (filters: FilterDefinition | null) => void;

  // AI Agents
  agents: Agent[];
  setAgents: (agents: Agent[]) => void;

  // Automations
  automations: Automation[];
  setAutomations: (automations: Automation[]) => void;
  toggleAutomation: (automationId: string) => void;

  // Contact-Agent assignments
  contactAgents: ContactAgent[];
  setContactAgents: (assignments: ContactAgent[]) => void;
  assignAgent: (contactId: number, agentId: string) => void;
  toggleContactAgent: (contactId: number) => void;
}

export const useContactStore = create<ContactStore>((set) => ({
  // Selected contact
  selectedContact: null,
  setSelectedContact: (contact) => set({ selectedContact: contact }),

  // Contacts list
  contacts: [],
  setContacts: (contacts) => set({ contacts }),

  // Timeline
  timeline: [],
  setTimeline: (items) => set({ timeline: items }),
  addTimelineItem: (item) => set((state) => ({
    timeline: [...state.timeline, item].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  })),
  clearTimeline: () => set({ timeline: [] }),

  // Loading states
  isLoadingContacts: false,
  setIsLoadingContacts: (loading) => set({ isLoadingContacts: loading }),
  isLoadingTimeline: false,
  setIsLoadingTimeline: (loading) => set({ isLoadingTimeline: loading }),

  // Search
  searchQuery: "",
  setSearchQuery: (query) => set({ searchQuery: query }),

  // Filters
  statusFilter: null,
  setStatusFilter: (status) => set({ statusFilter: status }),

  // Sorting
  sortBy: "created_at",
  setSortBy: (sortBy) => set({ sortBy }),

  // Advanced filters
  filters: null,
  setFilters: (filters) => set({ filters }),

  // AI Agents
  agents: [],
  setAgents: (agents) => set({ agents }),

  // Automations
  automations: [],
  setAutomations: (automations) => set({ automations }),
  toggleAutomation: (automationId) => set((state) => ({
    automations: state.automations.map((a) =>
      a.id === automationId ? { ...a, is_active: !a.is_active } : a
    ),
  })),

  // Contact-Agent assignments
  contactAgents: [],
  setContactAgents: (assignments) => set({ contactAgents: assignments }),
  assignAgent: (contactId, agentId) => set((state) => {
    const existing = state.contactAgents.find((ca) => ca.contact_id === contactId);
    if (existing) {
      return {
        contactAgents: state.contactAgents.map((ca) =>
          ca.contact_id === contactId
            ? { ...ca, agent_id: agentId, is_active: true, assigned_at: new Date().toISOString() }
            : ca
        ),
      };
    }
    return {
      contactAgents: [
        ...state.contactAgents,
        { contact_id: contactId, agent_id: agentId, is_active: true, assigned_at: new Date().toISOString() },
      ],
    };
  }),
  toggleContactAgent: (contactId) => set((state) => ({
    contactAgents: state.contactAgents.map((ca) =>
      ca.contact_id === contactId ? { ...ca, is_active: !ca.is_active } : ca
    ),
  })),
}));
