import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContactDetailPanel } from "@/components/contacts/contact-detail-panel";
import { ConversationFeed } from "@/components/conversation/conversation-feed";
import { useRowSelection } from "@/hooks/useRowSelection";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import type { WorkspaceWithMembership } from "@/lib/api/workspaces";
import { useContactStore } from "@/lib/contact-store";
import { queryKeys } from "@/lib/query-keys";
import { brandSwitchDestination } from "@/providers/brand-switch-boundary";
import { WorkspaceProvider, useWorkspace } from "@/providers/workspace-provider";
import type { Contact } from "@/types";

const mocks = vi.hoisted(() => ({
  getContact: vi.fn(),
  generate: vi.fn(),
  send: vi.fn(),
  list: vi.fn(),
  replace: vi.fn(),
  pathname: "/contacts",
  search: "",
}));
vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useSearchParams: () => new URLSearchParams(mocks.search),
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("@/providers/auth-provider", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/lib/api/workspaces", () => ({ workspacesApi: { list: mocks.list } }));
vi.mock("@/hooks/useContacts", () => ({
  useContact: (workspaceId: string, id: number) =>
    useQuery({
      queryKey: queryKeys.contacts.detail(workspaceId, id),
      queryFn: () => mocks.getContact(workspaceId, id),
      enabled: !!workspaceId,
    }),
  useContactTimeline: () => ({ data: [], isPending: false, isError: false }),
  useToggleContactAI: () => ({}),
  useAssignContactAgent: () => ({}),
}));
vi.mock("@/hooks/useConversations", () => ({ useClearConversationHistory: () => ({}) }));
vi.mock("@/hooks/useAgents", () => ({ useAgents: () => ({ data: { items: [] } }) }));
vi.mock("@/hooks/usePhoneNumbers", () => ({ usePhoneNumbers: () => ({ data: { items: [] } }) }));
vi.mock("@/lib/api/conversations", () => ({
  conversationsApi: {
    list: async () => ({ items: [{ id: "thread", contact_id: 7 }] }),
    generateFollowup: mocks.generate,
    sendMessageToContact: mocks.send,
  },
}));
vi.mock("@/components/contacts/contact-sidebar", () => ({
  ContactSidebar: () => {
    const { selectedContact } = useContactStore();
    return <div data-testid="sidebar">{selectedContact?.first_name}</div>;
  },
}));
vi.mock("@/components/conversation/chat-header", () => ({ ChatHeader: () => null }));
vi.mock("@/components/conversation/message-composer", () => ({
  MessageComposer: (props: {
    message: string;
    onMessageChange: (value: string) => void;
    onSend: () => void;
    selectedFromNumber?: string;
    onFromNumberChange: (value: string) => void;
    onGenerateDraft?: () => void;
  }) => (
    <div>
      <input
        aria-label="Draft"
        value={props.message}
        onChange={(e) => props.onMessageChange(e.target.value)}
      />
      <input
        aria-label="Sender"
        value={props.selectedFromNumber ?? ""}
        onChange={(e) => props.onFromNumberChange(e.target.value)}
      />
      <button onClick={props.onGenerateDraft}>Generate</button>
      <button onClick={props.onSend}>Send</button>
    </div>
  ),
}));

const contact = (brand: string): Contact => ({
  id: 7,
  user_id: 1,
  workspace_id: brand,
  first_name: `Brand ${brand}`,
  status: "new",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
});
const brands = ["A", "B"].map(
  (id) => ({ workspace: { id }, is_default: id === "A", role: "owner" }) as WorkspaceWithMembership,
);

// Uses the actual panel, contact composer, store and row hook. The controls
// stand in for route/list chrome; only network data and visual leaf nodes stub.
let retainedSetter: ReturnType<typeof useContactStore>["setSelectedContact"];
function Fixture() {
  const { setCurrentWorkspace, currentWorkspaceId } = useWorkspace();
  const workspaceId = useWorkspaceId();
  const store = useContactStore();
  const selection = useRowSelection({ rowIds: [7, 8] });
  const [allMatching, setAllMatching] = useState<number[]>([]);
  useEffect(() => {
    if (workspaceId === "A" && !retainedSetter) retainedSetter = store.setSelectedContact;
  }, [workspaceId, store.setSelectedContact]);
  return (
    <div>
      <output data-testid="brand">{currentWorkspaceId}</output>
      <button onClick={() => setCurrentWorkspace("A")}>Brand A</button>
      <button onClick={() => setCurrentWorkspace("B")}>Brand B</button>
      <button onClick={() => setCurrentWorkspace("missing")}>Invalid brand</button>
      <button
        onClick={() => {
          selection.toggle(7);
          setAllMatching([7, 8]);
          store.setSearchQuery("A search");
          store.setContactsPageSize(50);
        }}
      >
        Select rows
      </button>
      <output data-testid="selection">
        {selection.selectedCount}:{allMatching.length}:{store.searchQuery}:{store.contactsPageSize}
      </output>
      <ContactDetailPanel contactId={7} onClose={() => {}} />
      <ConversationFeed enableAIDraft />
    </div>
  );
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  const tree = (
    <QueryClientProvider client={client}>
      <WorkspaceProvider>
        <Fixture />
      </WorkspaceProvider>
    </QueryClientProvider>
  );
  const view = render(tree);
  return {
    client,
    ...view,
    refresh: () =>
      view.rerender(
        <QueryClientProvider client={client}>
          <WorkspaceProvider>
            <Fixture />
          </WorkspaceProvider>
        </QueryClientProvider>,
      ),
    user: userEvent.setup(),
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.pathname = "/contacts";
  mocks.search = "";
  retainedSetter = undefined as unknown as typeof retainedSetter;
  mocks.list.mockResolvedValue(brands);
  mocks.getContact.mockImplementation(async (brand: string) => contact(brand));
});

describe("RF-029 brand sessions", () => {
  it("clears open contact/draft/sender/row and all-matching selections when B fails, and stays clear on switch-back", async () => {
    mocks.getContact.mockImplementation(async (brand: string) => {
      if (brand === "B") throw new Error("B unavailable");
      return contact(brand);
    });
    const { user } = setup();
    expect(await screen.findByTestId("sidebar")).toHaveTextContent("Brand A");
    await user.type(screen.getByLabelText("Draft"), "A private draft");
    await user.type(screen.getByLabelText("Sender"), "+15555550001");
    await user.click(screen.getByText("Select rows"));
    expect(screen.getByTestId("selection")).toHaveTextContent("1:2:A search:50");
    await user.click(screen.getByText("Brand B"));
    await screen.findByText("Contact not found");
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Draft")).not.toBeInTheDocument();
    expect(screen.getByTestId("selection")).toHaveTextContent("0:0::50");
    await user.click(screen.getByText("Brand A"));
    expect(await screen.findByTestId("sidebar")).toHaveTextContent("Brand A");
    expect(screen.getByLabelText("Draft")).toHaveValue("");
    expect(screen.getByLabelText("Sender")).toHaveValue("");
    expect(screen.getByTestId("selection")).toHaveTextContent("0:0::50");
    await user.click(screen.getByText("Invalid brand"));
    expect(screen.getByTestId("brand")).toHaveTextContent("A");
  });

  it("does not adopt late old-store updates or generated drafts, even after switch-back", async () => {
    const draft = deferred<{ message: string }>();
    mocks.generate.mockReturnValue(draft.promise);
    const { user } = setup();
    await screen.findByTestId("sidebar");
    await user.click(screen.getByText("Generate"));
    await waitFor(() => expect(mocks.generate).toHaveBeenCalledWith("A", "thread"));
    await user.click(screen.getByText("Brand B"));
    await waitFor(() => expect(screen.getByTestId("sidebar")).toHaveTextContent("Brand B"));
    await user.click(screen.getByText("Brand A"));
    await waitFor(() => expect(screen.getByTestId("sidebar")).toHaveTextContent("Brand A"));
    await act(async () => {
      retainedSetter({ ...contact("A"), first_name: "Late private result" });
      draft.resolve({ message: "Late A draft" });
    });
    expect(screen.getByTestId("sidebar")).toHaveTextContent("Brand A");
    expect(screen.getByLabelText("Draft")).toHaveValue("");
  });

  it("allows an in-flight A send to complete against A without restoring its failed draft in B", async () => {
    const send = deferred<void>();
    mocks.send.mockReturnValue(send.promise);
    const { user, client } = setup();
    await screen.findByTestId("sidebar");
    await user.type(screen.getByLabelText("Draft"), "Send for A");
    await user.click(screen.getByText("Send"));
    expect(mocks.send).toHaveBeenCalledWith("A", 7, "Send for A", undefined);
    const mutation = client.getMutationCache().build(client, { mutationFn: () => send.promise });
    const operation = mutation.execute(undefined).catch(() => undefined);
    await user.click(screen.getByText("Brand B"));
    await waitFor(() => expect(screen.getByTestId("sidebar")).toHaveTextContent("Brand B"));
    expect(client.getMutationCache().getAll()).toContain(mutation);
    await act(async () => {
      send.reject(new Error("A send failed"));
      await operation;
    });
    expect(screen.getByLabelText("Draft")).toHaveValue("");
    expect(screen.getByTestId("sidebar")).toHaveTextContent("Brand B");
  });

  it("discards a late A contact fetch rather than adopting it under B", async () => {
    const oldContact = deferred<Contact>();
    mocks.getContact.mockImplementation((brand: string) =>
      brand === "A" ? oldContact.promise : Promise.reject(new Error("B failed")),
    );
    const { user } = setup();
    await waitFor(() => expect(screen.getByTestId("brand")).toHaveTextContent("A"));
    await user.click(screen.getByText("Brand B"));
    await screen.findByText("Contact not found");
    await act(async () => oldContact.resolve(contact("A")));
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Draft")).not.toBeInTheDocument();
  });

  it("hides the old contact route until replace finishes, without fetching B for the old id", async () => {
    mocks.pathname = "/contacts/7";
    mocks.search = "contact=7&filters=private";
    const { user, refresh } = setup();
    await screen.findByTestId("sidebar");
    await user.click(screen.getByText("Brand B"));
    expect(mocks.replace).toHaveBeenCalledWith("/contacts", { scroll: false });
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(mocks.getContact).not.toHaveBeenCalledWith("B", 7);
    mocks.pathname = "/contacts";
    mocks.search = "";
    refresh();
    await waitFor(() => expect(screen.getByTestId("brand")).toHaveTextContent("B"));
    expect(brandSwitchDestination("/contacts", "contact=7&filters=private")).toBe("/contacts");
    expect(brandSwitchDestination("/conversations", "thread=A-thread")).toBe("/conversations");
  });
});
