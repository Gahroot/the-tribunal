import { createContext, useContext } from "react";
import { create, useStore } from "zustand";

import type { ContactSortBy } from "@/lib/api/contacts";
import type { Contact, ContactAgent, FilterDefinition } from "@/types";

interface ContactStore {
  // Selected contact
  selectedContact: Contact | null;
  setSelectedContact: (contact: Contact | null) => void;

  // Pagination
  contactsPage: number;
  contactsPageSize: number;
  setContactsPage: (page: number) => void;
  setContactsPageSize: (size: number) => void;

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

  // Contact-Agent assignments (local UI state)
  contactAgents: ContactAgent[];
  setContactAgents: (assignments: ContactAgent[]) => void;
  assignAgent: (contactId: number, agentId: string) => void;
  toggleContactAgent: (contactId: number) => void;
}

// Only display preferences are user-wide. CRM selections, filters and local
// assignments belong to a brand session and must never survive its boundary.
const preferences = { contactsPageSize: 25, sortBy: "created_at" as ContactSortBy };

export function createContactStore(workspaceId?: string) {
  return create<ContactStore>((set) => ({
    // Selected contact
    selectedContact: null,
    setSelectedContact: (contact) => {
      if (contact?.workspace_id && workspaceId && contact.workspace_id !== workspaceId) return;
      set({ selectedContact: contact });
    },

    // Pagination
    contactsPage: 1,
    contactsPageSize: preferences.contactsPageSize,
    setContactsPage: (page) => set({ contactsPage: page }),
    setContactsPageSize: (size) => {
      preferences.contactsPageSize = size;
      set({ contactsPageSize: size, contactsPage: 1 });
    },

    // Search
    searchQuery: "",
    setSearchQuery: (query) => set({ searchQuery: query, contactsPage: 1 }),

    // Filters
    statusFilter: null,
    setStatusFilter: (status) => set({ statusFilter: status, contactsPage: 1 }),

    // Sorting
    sortBy: preferences.sortBy,
    setSortBy: (sortBy) => {
      preferences.sortBy = sortBy;
      set({ sortBy, contactsPage: 1 });
    },

    // Advanced filters
    filters: null,
    setFilters: (filters) => set({ filters, contactsPage: 1 }),

    // Contact-Agent assignments
    contactAgents: [],
    setContactAgents: (assignments) => set({ contactAgents: assignments }),
    assignAgent: (contactId, agentId) =>
      set((state) => {
        const existing = state.contactAgents.find((ca) => ca.contact_id === contactId);
        if (existing) {
          return {
            contactAgents: state.contactAgents.map((ca) =>
              ca.contact_id === contactId
                ? {
                    ...ca,
                    agent_id: agentId,
                    is_active: true,
                    assigned_at: new Date().toISOString(),
                  }
                : ca,
            ),
          };
        }
        return {
          contactAgents: [
            ...state.contactAgents,
            {
              contact_id: contactId,
              agent_id: agentId,
              is_active: true,
              assigned_at: new Date().toISOString(),
            },
          ],
        };
      }),
    toggleContactAgent: (contactId) =>
      set((state) => ({
        contactAgents: state.contactAgents.map((ca) =>
          ca.contact_id === contactId ? { ...ca, is_active: !ca.is_active } : ca,
        ),
      })),
  }));
}

export const ContactStoreContext = createContext<ReturnType<typeof createContactStore> | null>(
  null,
);
const fallbackStore = createContactStore();

// Preserve the standalone store API used by existing component fixtures. In the
// app every caller gets the session's instance, so an old async setter can only
// write to its detached old store — including after switching back to Brand A.
export const useContactStore = Object.assign(
  function useContactStore() {
    const store = useContext(ContactStoreContext);
    return useStore(store ?? fallbackStore);
  },
  { getState: fallbackStore.getState, setState: fallbackStore.setState },
);
