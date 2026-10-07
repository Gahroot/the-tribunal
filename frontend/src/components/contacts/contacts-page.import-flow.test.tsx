import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useSyncExternalStore } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContactsPage } from "@/components/contacts/contacts-page";
import { SETUP_STEP_DEFINITIONS } from "@/hooks/useSetupChecklist";

// A minimal stand-in for the App Router: `replace` really changes the current
// URL and re-renders subscribers, so the page's URL cleanup runs end to end and
// a loop of replaces would show up as extra calls.
const { location, routerReplaceMock, pushMock } = vi.hoisted(() => {
  const state = { url: "/contacts", listeners: new Set<() => void>() };
  return {
    location: state,
    pushMock: vi.fn(),
    routerReplaceMock: vi.fn((url: string) => {
      state.url = url;
      state.listeners.forEach((listener) => listener());
    }),
  };
});

const searchParamsCache = new Map<string, URLSearchParams>();
function useCurrentUrl() {
  return useSyncExternalStore(
    (listener) => {
      location.listeners.add(listener);
      return () => location.listeners.delete(listener);
    },
    () => location.url,
  );
}

vi.mock("next/navigation", () => ({
  usePathname: () => useCurrentUrl().split("?")[0],
  useRouter: () => ({ push: pushMock, replace: routerReplaceMock }),
  useSearchParams: () => {
    const query = useCurrentUrl().split("?")[1] ?? "";
    let params = searchParamsCache.get(query);
    if (!params) {
      params = new URLSearchParams(query);
      searchParamsCache.set(query, params);
    }
    return params;
  },
}));

// The real ImportContactsDialog is rendered; only unrelated heavy children are stubbed.
vi.mock("@/components/contacts/contact-detail-panel", () => ({
  ContactDetailPanel: () => <div>Contact detail</div>,
}));

vi.mock("@/components/contacts/contact-form-dialog", () => ({
  ContactFormDialog: () => null,
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

const { setFiltersMock } = vi.hoisted(() => ({ setFiltersMock: vi.fn() }));
vi.mock("@/lib/contact-store", () => ({
  useContactStore: () => ({
    contactsPage: 1,
    contactsPageSize: 25,
    filters: null,
    searchQuery: "",
    setContactsPage: vi.fn(),
    setFilters: setFiltersMock,
    setSearchQuery: vi.fn(),
    setSelectedContact: vi.fn(),
    setSortBy: vi.fn(),
    setStatusFilter: vi.fn(),
    sortBy: "created_at",
    statusFilter: null,
  }),
}));

const checklistImportHref = SETUP_STEP_DEFINITIONS.find((step) => step.id === "contacts")!.href;

function visit(url: string) {
  location.url = url;
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  const tree = () => (
    <QueryClientProvider client={client}>
      <ContactsPage />
    </QueryClientProvider>
  );
  const view = render(tree());
  return { ...view, rerenderPage: () => view.rerender(tree()) };
}

function importDialog() {
  return screen.queryByRole("dialog", { name: "Import Contacts" });
}

afterEach(() => {
  vi.clearAllMocks();
  location.listeners.clear();
});

describe("ContactsPage ?import=true first-use path", () => {
  it("opens the real import dialog from the checklist link and keeps it open after the flag is stripped", async () => {
    expect(checklistImportHref).toBe("/contacts?import=true");
    visit(checklistImportHref);

    expect(importDialog()).toBeInTheDocument();
    expect(screen.getByText("Upload a CSV file to import contacts in bulk.")).toBeInTheDocument();

    // The flag is removed in place: stays on Contacts, exactly one replace, no push.
    await waitFor(() => expect(location.url).toBe("/contacts"));
    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
    expect(routerReplaceMock).toHaveBeenCalledWith("/contacts", { scroll: false });
    expect(pushMock).not.toHaveBeenCalled();
    expect(importDialog()).toBeInTheDocument();
  });

  it("closes onto Contacts and does not reopen on rerender or reload", async () => {
    const user = userEvent.setup();
    const view = visit(checklistImportHref);
    await waitFor(() => expect(location.url).toBe("/contacts"));

    await user.keyboard("{Escape}");
    await waitFor(() => expect(importDialog()).not.toBeInTheDocument());
    expect(location.url).toBe("/contacts");
    expect(screen.getByText("No contacts yet")).toBeInTheDocument();

    view.rerenderPage();
    expect(importDialog()).not.toBeInTheDocument();

    // Reload: the cleaned URL no longer carries the flag.
    view.unmount();
    visit(location.url);
    expect(importDialog()).not.toBeInTheDocument();
    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
  });

  it("does not open the dialog or touch the URL on a normal Contacts visit", () => {
    visit("/contacts?contact=7");
    expect(importDialog()).not.toBeInTheDocument();
    expect(routerReplaceMock).not.toHaveBeenCalled();
  });

  it("opens when the flag arrives on an already-mounted Contacts page", async () => {
    visit("/contacts");
    expect(importDialog()).not.toBeInTheDocument();

    act(() => {
      location.url = "/contacts?import=true";
      location.listeners.forEach((listener) => listener());
    });

    expect(importDialog()).toBeInTheDocument();
    await waitFor(() => expect(location.url).toBe("/contacts"));
    expect(importDialog()).toBeInTheDocument();
  });

  it("removes only the one-shot params and preserves unrelated ones", async () => {
    const filters = JSON.stringify({ logic: "and", rules: [{ field: "status", operator: "equals", value: "new" }] });
    visit(`/contacts?contact=7&import=true&view=compact&filters=${encodeURIComponent(filters)}`);

    expect(importDialog()).toBeInTheDocument();
    await waitFor(() => expect(location.url).toBe("/contacts?contact=7&view=compact"));
    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
    expect(setFiltersMock).toHaveBeenCalledWith(JSON.parse(filters));
    expect(importDialog()).toBeInTheDocument();
    expect(screen.getByText("Contact detail")).toBeInTheDocument();
  });
});
