import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SaveSegmentDialog } from "@/components/segments/save-segment-dialog";
import type { FilterDefinition } from "@/types";

const { createMutateAsync, toastSuccessMock, toastErrorMock } = vi.hoisted(() => ({
  createMutateAsync: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}));

vi.mock("@/hooks/useSegments", () => ({
  useCreateSegment: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useSegmentPreview: () => ({ data: { total: 42 }, isFetching: false }),
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock },
}));

const filters: FilterDefinition = {
  logic: "and",
  rules: [{ field: "tag", operator: "contains", value: "vip" }],
} as unknown as FilterDefinition;

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SaveSegmentDialog
        open
        onOpenChange={onOpenChange}
        filters={filters}
        workspaceId="ws_1"
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

describe("SaveSegmentDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the matched-contact preview from the filter definition", () => {
    renderDialog();
    expect(screen.getByText("Filter rules (1)")).toBeInTheDocument();
    expect(screen.getByText("~42 contacts match")).toBeInTheDocument();
  });

  it("blocks submit and shows a validation error when the name is empty", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Save Segment" }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(createMutateAsync).not.toHaveBeenCalled();
  });

  it("creates the segment with trimmed values and closes on success", async () => {
    createMutateAsync.mockResolvedValue({ id: "seg_1" });
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.type(screen.getByPlaceholderText("e.g., High-value leads"), "  VIP leads  ");
    await user.type(screen.getByPlaceholderText("Describe this segment..."), " top tier ");
    await user.click(screen.getByRole("button", { name: "Save Segment" }));

    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith({
        name: "VIP leads",
        description: "top tier",
        definition: filters,
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Segment saved");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("surfaces a server error as a toast and keeps the dialog open", async () => {
    createMutateAsync.mockRejectedValue({
      isAxiosError: true,
      response: { data: { code: "internal_error", message: "Segment save failed" } },
    });
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.type(screen.getByPlaceholderText("e.g., High-value leads"), "VIP leads");
    await user.click(screen.getByRole("button", { name: "Save Segment" }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Segment save failed"));
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
