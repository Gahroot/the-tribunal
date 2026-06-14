import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ContactsPage } from "@/components/contacts/contacts-page";

const { routerReplaceMock } = vi.hoisted(() => ({
  routerReplaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: routerReplaceMock }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/contacts/contact-form-dialog", () => ({
  ContactFormDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">Add Contact Dialog</div> : null,
}));

vi.mock("@/components/contacts/import-contacts-dialog", () => ({
  ImportContactsDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">Import Contacts</div> : null,
}));

vi.mock("@/components/contacts/scrape-leads-dialog", () => ({
  ScrapeLeadsDialog: () => null,
}));

vi.mock("@/components/contacts/bulk-tag-dialog", () => ({
  BulkTagDialog: () => null,
}));

vi.mock("@/components/contacts/contacts-toolbar", () => ({
  ContactsToolbar: () => null,
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/hooks/useContacts", () => ({
  useBulkDeleteContacts: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useBulkUpdateStatus: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useContactIds: () => ({ data: null, isFetching: false }),
  useContactsPaginated: () => ({
    data: { items: [], pages: 1, total: 0 },
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  }),
}));

vi.mock("@/lib/contact-store", () => ({
  useContactStore: () => ({
    contactsPage: 1,
    contactsPageSize: 25,
    filters: null,
    searchQuery: "",
    setContactsPage: vi.fn(),
    setFilters: vi.fn(),
    setSearchQuery: vi.fn(),
    setSortBy: vi.fn(),
    setStatusFilter: vi.fn(),
    sortBy: "created_at",
    statusFilter: null,
  }),
}));

function renderContactsPage() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <ContactsPage />
    </QueryClientProvider>,
  );
}

describe("ContactsPage empty state", () => {
  it("opens the import dialog from the first-run empty state", async () => {
    const user = userEvent.setup();
    renderContactsPage();

    const emptyState = screen.getByText("No contacts yet").closest("div");
    expect(emptyState).not.toBeNull();

    const importButton = within(emptyState as HTMLElement).getByRole("button", {
      name: /import csv/i,
    });
    await user.click(importButton);

    expect(screen.getByRole("dialog")).toHaveTextContent("Import Contacts");
  });
});
