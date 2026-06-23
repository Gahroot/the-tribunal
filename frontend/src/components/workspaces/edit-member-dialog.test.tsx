import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditMemberDialog } from "@/components/workspaces/edit-member-dialog";

const { updateMemberRoleMock, removeMemberMock, toastSuccessMock, toastErrorMock } = vi.hoisted(
  () => ({
    updateMemberRoleMock: vi.fn(),
    removeMemberMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastErrorMock: vi.fn(),
  }),
);

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: {
    updateMemberRole: updateMemberRoleMock,
    removeMember: removeMemberMock,
  },
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock },
}));

const member = {
  id: 7,
  email: "member@example.com",
  full_name: "Member Person",
  role: "member",
};

function renderDialog(overrides: Partial<React.ComponentProps<typeof EditMemberDialog>> = {}) {
  const onOpenChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <EditMemberDialog
        open
        onOpenChange={onOpenChange}
        member={member}
        currentUserRole="owner"
        {...overrides}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

describe("EditMemberDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("closes without an API call when the role is unchanged", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(updateMemberRoleMock).not.toHaveBeenCalled();
  });

  it("updates the role through the API when changed and closes on success", async () => {
    updateMemberRoleMock.mockResolvedValue({ user_id: 7, role: "admin", message: "ok" });
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Admin/ }));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(updateMemberRoleMock).toHaveBeenCalledWith("ws_1", 7, "admin"));
    expect(toastSuccessMock).toHaveBeenCalledWith("Member role updated");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders the owner role as read-only and disables saving", () => {
    renderDialog({ member: { ...member, role: "owner" } });

    expect(screen.getByText("owner (cannot be changed)")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  it("removes the member after confirming the destructive action", async () => {
    removeMemberMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.click(screen.getByRole("button", { name: /Remove/ }));
    await user.click(await screen.findByRole("button", { name: "Remove Member" }));

    await waitFor(() => expect(removeMemberMock).toHaveBeenCalledWith("ws_1", 7));
    expect(toastSuccessMock).toHaveBeenCalledWith("Member removed from workspace");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("hides the Remove action for a member without permission", () => {
    renderDialog({ currentUserRole: "member" });
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
  });
});
