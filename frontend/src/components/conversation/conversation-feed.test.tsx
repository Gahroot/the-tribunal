import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ConversationFeed } from "@/components/conversation/conversation-feed";
import { queryKeys } from "@/lib/query-keys";
import type { Contact } from "@/types";

const api = vi.hoisted(() => ({ list: vi.fn(), sendMessageToContact: vi.fn() }));
const notify = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/lib/api/conversations", () => ({ conversationsApi: api }));
vi.mock("sonner", () => ({ toast: notify }));
vi.mock("@/hooks/useWorkspaceId", () => ({ useWorkspaceId: () => "workspace-a" }));
vi.mock("@/lib/contact-store", () => ({ useContactStore: () => ({ selectedContact: null }) }));
vi.mock("@/hooks/useAgents", () => ({ useAgents: () => ({ data: { items: [] } }) }));
vi.mock("@/hooks/useContacts", () => ({
  useContactTimeline: () => ({ data: [], isPending: false, isError: false }),
  useToggleContactAI: () => ({ mutate: vi.fn() }),
  useAssignContactAgent: () => ({ mutate: vi.fn() }),
}));
vi.mock("@/hooks/useConversations", () => ({
  useClearConversationHistory: () => ({ mutate: vi.fn() }),
}));
vi.mock("@/hooks/usePhoneNumbers", () => ({ usePhoneNumbers: () => ({ data: { items: [] } }) }));
vi.mock("./chat-header", () => ({ ChatHeader: () => null }));

const contact = {
  id: 19, workspace_id: "workspace-a", phone_number: "+12025550101",
  first_name: "Fixture", last_name: "Contact",
} as Contact;

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ items: [] });
  api.sendMessageToContact.mockResolvedValue({ status: "sent" });
});

it.each(["rejected", "failed-object"])("keeps a contact draft after %s and clears only on accepted retry", async (outcome) => {
  if (outcome === "rejected") api.sendMessageToContact.mockRejectedValueOnce(new Error("Text not accepted"));
  else api.sendMessageToContact.mockResolvedValueOnce({ status: "failed" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><ConversationFeed contact={contact} /></QueryClientProvider>);
  const composer = screen.getByRole("textbox");
  fireEvent.change(composer, { target: { value: "Keep my draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(notify.error).toHaveBeenCalledOnce());
  expect(composer).toHaveValue("Keep my draft");
  expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.contacts.timeline("workspace-a", 19) });
  expect(api.sendMessageToContact).toHaveBeenCalledWith("workspace-a", 19, "Keep my draft", undefined);
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(composer).toHaveValue(""));
  expect(api.sendMessageToContact).toHaveBeenCalledTimes(2);
});
