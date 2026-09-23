import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CreateFollowupTaskDialog } from "@/components/contacts/create-followup-task-dialog";

const { createNudgeMock, getTeamMembersMock, toastSuccessMock } = vi.hoisted(() => ({
  createNudgeMock: vi.fn(),
  getTeamMembersMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}));

vi.mock("@/lib/api/nudges", () => ({
  nudgesApi: {
    create: createNudgeMock,
    update: vi.fn(),
    list: vi.fn(),
    act: vi.fn(),
    dismiss: vi.fn(),
    snooze: vi.fn(),
    getStats: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

vi.mock("@/lib/api/settings", () => ({
  settingsApi: { getTeamMembers: getTeamMembersMock },
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: vi.fn() },
}));

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <CreateFollowupTaskDialog workspaceId="ws_1" contactId={42} open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("CreateFollowupTaskDialog", () => {
  beforeEach(() => {
    createNudgeMock.mockReset().mockResolvedValue({});
    getTeamMembersMock.mockReset().mockResolvedValue([]);
    toastSuccessMock.mockReset();
  });

  it("creates a task, stays open, and clears only the quick-entry fields", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText(/title/i), "Send pricing recap");
    await user.click(screen.getByRole("button", { name: /^add task$/i }));

    await waitFor(() => expect(createNudgeMock).toHaveBeenCalledTimes(1));
    expect(createNudgeMock).toHaveBeenCalledWith(
      "ws_1",
      expect.objectContaining({
        contact_id: 42,
        title: "Send pricing recap",
        nudge_type: "follow_up",
        assigned_to_user_id: null,
        due_date: expect.any(String),
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalled();

    // Stay-open repeat behavior: the dialog never closes, the title clears,
    // and the next task can be added without reopening it.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText(/title/i)).toHaveValue(""));

    await user.type(screen.getByLabelText(/title/i), "Call after open house");
    await user.click(screen.getByRole("button", { name: /^add task$/i }));

    await waitFor(() => expect(createNudgeMock).toHaveBeenCalledTimes(2));
    expect(createNudgeMock).toHaveBeenLastCalledWith(
      "ws_1",
      expect.objectContaining({
        contact_id: 42,
        title: "Call after open house",
      }),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("blocks an empty title from submitting", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: /^add task$/i }));

    expect(createNudgeMock).not.toHaveBeenCalled();
    expect(await screen.findByText(/add a task title/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
