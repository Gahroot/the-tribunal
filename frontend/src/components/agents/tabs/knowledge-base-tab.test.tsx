import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeBaseTab } from "./knowledge-base-tab";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("@/lib/api/knowledge-documents", () => ({ knowledgeDocumentsApi: api }));
vi.mock("@/hooks/useWorkspaceId", () => ({ useWorkspaceId: () => "workspace-fixture" }));

const document = {
  id: "faq",
  title: "Uploaded FAQ",
  content: "Refunds within 37 days.",
  doc_type: "faq",
  token_count: 10,
  priority: 0,
  is_active: true,
  retrieval_ready: true,
  created_at: "2026-10-08T12:00:00Z",
  updated_at: "2026-10-08T12:00:00Z",
};
const response = (items = [document]) => ({
  items,
  total: items.length,
  total_tokens: 10,
  token_budget: 4000,
});

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgeBaseTab agentId="agent-fixture" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue(response());
});

describe("voice knowledge readiness", () => {
  it("shows ready indexed documents without a hidden tool setting", async () => {
    renderTab();
    expect(await screen.findByText("Ready for answers")).toBeVisible();
    expect(screen.getByText(/No tool setting is needed/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry indexing" })).not.toBeInTheDocument();
  });

  it("shows inactive documents as inactive, not ready", async () => {
    api.list.mockResolvedValue(
      response([{ ...document, is_active: false, retrieval_ready: false }]),
    );
    renderTab();
    expect(await screen.findByText("Inactive")).toBeVisible();
    expect(screen.queryByText("Ready for answers")).not.toBeInTheDocument();
  });

  it("retries indexing and updates readiness", async () => {
    api.list.mockResolvedValueOnce(response([{ ...document, retrieval_ready: false }]));
    api.update.mockResolvedValue(document);
    const user = userEvent.setup();
    renderTab();
    await user.click(await screen.findByRole("button", { name: "Retry indexing" }));
    expect(api.update).toHaveBeenCalledWith("workspace-fixture", "agent-fixture", "faq", {
      content: document.content,
    });
    expect(await screen.findByText("Ready for answers")).toBeVisible();
  });

  it("keeps indexing failure actionable", async () => {
    api.list.mockResolvedValue(response([{ ...document, retrieval_ready: false }]));
    api.update.mockRejectedValue(new Error("Embedding unavailable"));
    const user = userEvent.setup();
    renderTab();
    await user.click(await screen.findByRole("button", { name: "Retry indexing" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Embedding unavailable");
    expect(screen.getByRole("button", { name: "Retry indexing" })).toBeEnabled();
  });

  it("keeps upload text after indexing fails so saving can be retried", async () => {
    api.list.mockResolvedValue(response([]));
    api.create.mockRejectedValue(new Error("Indexing failed"));
    const user = userEvent.setup();
    renderTab();
    await user.click(await screen.findByRole("button", { name: "Add Document" }));
    await user.type(screen.getByLabelText("Title"), "Refund FAQ");
    await user.type(screen.getByLabelText("Content"), document.content);
    const buttons = screen.getAllByRole("button", { name: "Add Document" });
    await user.click(buttons[buttons.length - 1]);
    expect(await screen.findByRole("alert")).toHaveTextContent("retry saving");
    expect(screen.getByLabelText("Content")).toHaveValue(document.content);
  });

  it("distinguishes load failure from an empty knowledge base and retries", async () => {
    api.list.mockRejectedValueOnce(new Error("Offline"));
    const user = userEvent.setup();
    renderTab();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load");
    await user.click(screen.getByRole("button", { name: "Retry loading" }));
    await waitFor(() => expect(screen.getByText("Ready for answers")).toBeVisible());
  });
});
