import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CallsList } from "@/components/calls/calls-list";
import type { CallsListResponse } from "@/lib/api/calls";
import type { CallRecord } from "@/types";

const { listCallsMock } = vi.hoisted(() => ({
  listCallsMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "workspace-1",
}));

vi.mock("@/lib/api/calls", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/calls")>("@/lib/api/calls");
  return {
    ...actual,
    callsApi: {
      ...actual.callsApi,
      list: listCallsMock,
    },
  };
});

vi.mock("@/components/calls/call-outcome-controls", () => ({
  CallOutcomeControls: () => null,
}));

const firstCall: CallRecord = {
  id: "call-1",
  conversation_id: "conversation-1",
  direction: "outbound",
  channel: "voice",
  status: "completed",
  from_number: "+15551110000",
  to_number: "+15552220000",
  contact_name: "Ada Lovelace",
  duration_seconds: 90,
  agent_name: "Reception AI",
  is_ai: true,
  booking_outcome: "success",
  captured_messages: [
    {
      id: "message-1",
      caller_name: "Ada Lovelace",
      reason: "Wants a showing",
      urgency: "high",
      message_body: "Please call back, thanks",
      status: "new",
      created_at: "2026-06-14T12:05:00Z",
    },
  ],
  transcript: "Agent: Hello\nLead: Hi",
  recording_url: "https://example.test/recording.mp3",
  created_at: "2026-06-14T12:00:00Z",
};

const secondCall: CallRecord = {
  id: "call-2",
  conversation_id: "conversation-2",
  direction: "inbound",
  channel: "voice",
  status: "no_answer",
  from_number: "+15553330000",
  to_number: "+15554440000",
  contact_name: "Grace Hopper",
  created_at: "2026-06-14T13:00:00Z",
};

function paginatedCalls(items: CallRecord[], pages: number): CallsListResponse {
  return {
    items,
    total: 101,
    page: 1,
    page_size: 50,
    pages,
    completed_count: 1,
    total_duration_seconds: 90,
  };
}

function renderCallsList() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <CallsList />
    </QueryClientProvider>,
  );
}

describe("CallsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:csv");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    listCallsMock.mockImplementation((_workspaceId: string, params: { page?: number; page_size?: number }) => {
      if (params.page_size === 100) {
        return Promise.resolve(paginatedCalls(params.page === 2 ? [secondCall] : [firstCall], 2));
      }

      return Promise.resolve(paginatedCalls([firstCall], 1));
    });
  });

  it("downloads a CSV of all currently filtered calls when Export is clicked", async () => {
    const user = userEvent.setup();
    renderCallsList();

    const exportButton = await screen.findByRole("button", { name: /export/i });
    await user.click(exportButton);

    await waitFor(() => expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1));
    expect(listCallsMock).toHaveBeenCalledWith(
      "workspace-1",
      expect.objectContaining({ page: 1, page_size: 100 }),
    );
    expect(listCallsMock).toHaveBeenCalledWith(
      "workspace-1",
      expect.objectContaining({ page: 2, page_size: 100 }),
    );

    const blob = vi.mocked(URL.createObjectURL).mock.calls[0]?.[0] as Blob;
    const csv = await blob.text();
    expect(csv).toContain("Call ID,Created At,Contact,Direction,Status");
    expect(csv).toContain("call-1,2026-06-14T12:00:00Z,Ada Lovelace,outbound,completed");
    expect(csv).toContain("call-2,2026-06-14T13:00:00Z,Grace Hopper,inbound,no_answer");
    expect(csv).toContain('"Agent: Hello\nLead: Hi"');
  });
});
