import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContactlessThread } from "@/components/conversations/contactless-thread";
import type { InboxConversation } from "@/lib/api/conversations";

const api = vi.hoisted(() => ({
  getMessages: vi.fn(),
  sendMessage: vi.fn(),
  generateFollowup: vi.fn(),
  toggleAI: vi.fn(),
}));
vi.mock("@/lib/api/conversations", () => ({ conversationsApi: api }));

export const conversationFixture: InboxConversation = {
  id: "11111111-1111-4111-8111-111111111111",
  workspace_id: "workspace-a",
  contact_id: null,
  contact: null,
  workspace_phone: "+15550000000",
  contact_phone: "+15550000001",
  channel: "sms",
  ai_enabled: false,
  ai_paused: false,
  assigned_agent_id: null,
  status: "active",
  unread_count: 1,
  last_message_at: "2026-09-24T12:00:00Z",
  last_message_preview: "Question",
  last_message_direction: "inbound",
  needs_human_reply: true,
  created_at: "2026-09-24T12:00:00Z",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function setup() {
  const onViewed = vi.fn().mockResolvedValue(undefined);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0, gcTime: 0 } },
  });
  function Harness({ conversation = conversationFixture }: { conversation?: InboxConversation }) {
    const [drafts, setDrafts] = useState<Record<string, string>>({});
    return (
      <QueryClientProvider client={client}>
        <ContactlessThread
          key={conversation.id}
          workspaceId={conversation.workspace_id}
          conversation={conversation}
          onViewed={onViewed}
          draft={drafts[conversation.id] ?? ""}
          onDraftChange={(value) => setDrafts((old) => ({ ...old, [conversation.id]: value }))}
        />
      </QueryClientProvider>
    );
  }
  return { ...render(<Harness />), Harness, onViewed, client };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getMessages.mockResolvedValue([]);
  api.sendMessage.mockResolvedValue({ status: "sent" });
  api.generateFollowup.mockResolvedValue({ message: "Draft suggestion" });
  api.toggleAI.mockResolvedValue({});
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("exact inbox thread", () => {
  it("acknowledges only after messages load, without sending", async () => {
    const pending = deferred<never[]>();
    api.getMessages.mockReturnValue(pending.promise);
    const { onViewed } = setup();
    expect(onViewed).not.toHaveBeenCalled();
    await act(async () => pending.resolve([]));
    await waitFor(() => expect(onViewed).toHaveBeenCalledWith(conversationFixture));
    expect(api.sendMessage).not.toHaveBeenCalled();
  });

  it("preserves text after failure, and sends on the selected conversation", async () => {
    api.sendMessage.mockRejectedValueOnce(new Error("Delivery unavailable"));
    setup();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    const composer = screen.getByRole("textbox");
    fireEvent.change(composer, { target: { value: "My reply" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    expect(composer).toHaveValue("My reply");
    expect(api.sendMessage).toHaveBeenCalledWith("workspace-a", conversationFixture.id, "My reply");
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(composer).toHaveValue(""));
  });

  it("prevents duplicate sends while the first request is pending", async () => {
    const pending = deferred<{ status: string }>();
    api.sendMessage.mockReturnValue(pending.promise);
    setup();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "One reply" } });
    const send = screen.getByRole("button", { name: "Send message" });
    fireEvent.click(send);
    fireEvent.click(send);
    expect(api.sendMessage).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve({ status: "queued" }));
  });

  it("keeps newer typing when an AI draft arrives late", async () => {
    const pending = deferred<{ message: string }>();
    api.generateFollowup.mockReturnValue(pending.promise);
    setup();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate AI draft reply" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate AI draft reply" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "My newer edits" } });
    await act(async () => pending.resolve({ message: "Stale AI text" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your edits were kept");
    expect(screen.getByRole("textbox")).toHaveValue("My newer edits");
    expect(api.sendMessage).not.toHaveBeenCalled();
  });

  it("aborts a draft on thread switch and preserves each thread's own text", async () => {
    const pending = deferred<{ message: string }>();
    api.generateFollowup.mockReturnValue(pending.promise);
    const { rerender, Harness } = setup();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Original thread draft" } });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate AI draft reply" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate AI draft reply" }));
    const signal = api.generateFollowup.mock.calls[0][3] as AbortSignal;
    rerender(
      <Harness
        conversation={{ ...conversationFixture, id: "22222222-2222-4222-8222-222222222222" }}
      />,
    );
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Other thread draft" } });
    await act(async () => pending.resolve({ message: "Wrong thread text" }));
    expect(screen.getByRole("textbox")).toHaveValue("Other thread draft");
    rerender(<Harness />);
    expect(screen.getByRole("textbox")).toHaveValue("Original thread draft");
  });

  it("asks before replacing existing text and inserts drafts without sending", async () => {
    setup();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Keep me" } });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate AI draft reply" })).toBeEnabled(),
    );
    vi.mocked(window.confirm).mockReturnValueOnce(false);
    fireEvent.click(screen.getByRole("button", { name: "Generate AI draft reply" }));
    expect(api.generateFollowup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Generate AI draft reply" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("Draft suggestion"));
    expect(api.sendMessage).not.toHaveBeenCalled();
  });

  it("does not acknowledge failed message loading", async () => {
    api.getMessages.mockRejectedValue(new Error("offline"));
    const { onViewed } = setup();
    await screen.findByText("We couldn't load this conversation. Please try again.");
    expect(onViewed).not.toHaveBeenCalled();
  });
});
