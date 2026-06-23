import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SaveTemplateDialog } from "@/components/experiments/save-template-dialog";

const { createMock, toastSuccessMock, toastErrorMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/lib/api/message-templates", () => ({
  messageTemplatesApi: { create: createMock },
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock },
}));

function renderDialog(props: Partial<React.ComponentProps<typeof SaveTemplateDialog>> = {}) {
  const onOpenChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SaveTemplateDialog
        open
        onOpenChange={onOpenChange}
        messageTemplate="Hi {{first_name}}"
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

describe("SaveTemplateDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("seeds the name field from defaultName and previews the message", () => {
    renderDialog({ defaultName: "Friendly Intro" });
    expect(screen.getByDisplayValue("Friendly Intro")).toBeInTheDocument();
    expect(screen.getByText("Hi {{first_name}}")).toBeInTheDocument();
  });

  it("requires a template name before submitting", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Save Template" }));

    expect(await screen.findByText("Please enter a template name")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("creates the template and closes on success", async () => {
    createMock.mockResolvedValue({ id: "tpl_1" });
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();

    await user.type(screen.getByPlaceholderText("e.g., Friendly Introduction"), "Bold opener");
    await user.click(screen.getByRole("button", { name: "Save Template" }));

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith("ws_1", {
        name: "Bold opener",
        message_template: "Hi {{first_name}}",
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Template saved successfully");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
