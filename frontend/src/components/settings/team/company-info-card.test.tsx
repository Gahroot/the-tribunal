import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyInfoCard } from "@/components/settings/team/company-info-card";

const { updateMock, workspaceMock } = vi.hoisted(() => ({
  updateMock: vi.fn(),
  workspaceMock: vi.fn(),
}));

vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: { update: updateMock },
}));
vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: workspaceMock,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function selectBrand(id: string, businessName: string) {
  workspaceMock.mockReturnValue({
    currentWorkspace: {
      workspace: { id, settings: { business_name: businessName, website: "https://example.org" } },
    },
  });
}

function card(workspaceId: string) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <CompanyInfoCard workspaceId={workspaceId} canEditWorkspace />
    </QueryClientProvider>
  );
}

describe("CompanyInfoCard brand email identity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockResolvedValue({});
    selectBrand("brand-a", "Brand A");
  });

  it("saves a blank name explicitly so customer emails can fall back to the brand name", async () => {
    const user = userEvent.setup();
    render(card("brand-a"));
    await user.clear(screen.getByLabelText("Business Name"));
    await user.click(screen.getByRole("button", { name: "Save Company Info" }));
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledWith("brand-a", {
        settings: expect.objectContaining({ business_name: "", website: "https://example.org" }),
      }),
    );
    expect(screen.getByText(/platform delivery is labeled/)).toHaveTextContent("via The Tribunal");
  });

  it("resets the form to Brand B rather than saving Brand A's settings", async () => {
    const view = render(card("brand-a"));
    selectBrand("brand-b", "Brand B");
    view.rerender(card("brand-b"));
    expect(screen.getByLabelText("Business Name")).toHaveValue("Brand B");
    await userEvent.setup().click(screen.getByRole("button", { name: "Save Company Info" }));
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledWith("brand-b", {
        settings: expect.objectContaining({ business_name: "Brand B" }),
      }),
    );
  });

  it("cannot write when the provider and requested brand differ", async () => {
    render(card("brand-b"));
    const input = screen.getByLabelText("Business Name");
    expect(input).toBeDisabled();
    expect(input).toHaveValue("");
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(updateMock).not.toHaveBeenCalled());
  });
});
