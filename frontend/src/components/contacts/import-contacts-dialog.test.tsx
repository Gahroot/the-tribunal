import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportContactsDialog } from "@/components/contacts/import-contacts-dialog";
import type { CSVPreviewResult, ImportResult } from "@/lib/api/contacts";

const { importCSVMock, previewCSVMock, toastSuccessMock, toastErrorMock, useWorkspaceIdMock } =
  vi.hoisted(() => ({
    importCSVMock: vi.fn(),
    previewCSVMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastErrorMock: vi.fn(),
    useWorkspaceIdMock: vi.fn(),
  }));

vi.mock("@/components/shared/file-dropzone", () => ({
  FileDropzone: ({ onFile }: { onFile: (file: File) => void }) => (
    <button type="button" onClick={() => onFile(new File(["csv"], "contacts.csv", { type: "text/csv" }))}>
      Upload CSV
    </button>
  ),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => useWorkspaceIdMock(),
}));

vi.mock("@/lib/api/contacts", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/contacts")>(
    "@/lib/api/contacts"
  );
  return {
    ...actual,
    contactsApi: {
      ...actual.contactsApi,
      importCSV: importCSVMock,
      previewCSV: previewCSVMock,
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

const previewResult: CSVPreviewResult = {
  headers: ["first_name", "phone_number"],
  sample_rows: [{ first_name: "Ada", phone_number: "+15551234567" }],
  suggested_mapping: {
    first_name: "first_name",
    phone_number: "phone_number",
  },
  contact_fields: [
    { name: "first_name", label: "First Name", required: true },
    { name: "phone_number", label: "Phone Number", required: true },
  ],
};

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <ImportContactsDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>
  );
}

async function completeImport(result: ImportResult) {
  previewCSVMock.mockResolvedValue(previewResult);
  importCSVMock.mockResolvedValue(result);

  const user = userEvent.setup();
  renderDialog();

  await user.click(screen.getByRole("button", { name: /upload csv/i }));
  await screen.findByRole("button", { name: /continue/i });
  await user.click(screen.getByRole("button", { name: /continue/i }));
  await user.click(screen.getByRole("button", { name: /import contacts/i }));

  await waitFor(() => expect(importCSVMock).toHaveBeenCalledTimes(1));
}

describe("ImportContactsDialog results", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceIdMock.mockReturnValue("ws_1");
  });

  it("shows a warning and remediation hint when every CSV row fails", async () => {
    await completeImport({
      successful: 0,
      failed: 1,
      skipped_duplicates: 0,
      total_rows: 1,
      created_contacts: [],
      errors: [{ row: 1, field: "phone_number", error: "Invalid phone number" }],
    });

    expect(await screen.findByText("Import Needs Attention")).toBeInTheDocument();
    expect(screen.getByText("No contacts imported")).toBeInTheDocument();
    expect(screen.getByText(/check your phone column mapping/i)).toBeInTheDocument();
    expect(screen.getByText("0")).toHaveClass("text-warning");
    expect(screen.getByText("0")).not.toHaveClass("text-success");
  });

  it("shows success styling and a View Contacts link after a successful import", async () => {
    await completeImport({
      successful: 1,
      failed: 0,
      skipped_duplicates: 0,
      total_rows: 1,
      created_contacts: [],
      errors: [],
    });

    expect(await screen.findByText("Import Complete")).toBeInTheDocument();
    expect(screen.getAllByText("1").some((element) => element.className.includes("text-success")))
      .toBe(true);

    const viewContactsLink = screen.getByRole("link", { name: /view contacts/i });
    expect(viewContactsLink).toHaveAttribute("href", "/contacts");
  });
});
