import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createCampaignFromCsv,
  onboard,
  parseCalcomUrl,
} from "@/lib/api/realtor";

import OnboardingPage from "./page";

// "workspace_default" is the user's default; the operator has selected the
// second workspace, which guided setup must target end to end (RF-005).
const workspaceState = vi.hoisted(() => ({
  currentWorkspaceId: "workspace_selected",
  workspaces: [
    { workspace: { id: "workspace_default", name: "Default Realty" }, is_default: true },
    { workspace: { id: "workspace_selected", name: "Second Team" }, is_default: false },
  ],
}));

vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: () => workspaceState,
}));

vi.mock("@/lib/api/realtor", () => ({
  createCampaignFromCsv: vi.fn(),
  importFubContacts: vi.fn(),
  onboard: vi.fn(),
  parseCalcomUrl: vi.fn(),
  verifyCalcom: vi.fn(),
  verifyFub: vi.fn(),
}));

function renderOnboarding() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <OnboardingPage />
    </QueryClientProvider>
  );
}

describe("Onboarding wizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("runs every setup call against the selected (non-default) workspace", async () => {
    vi.mocked(parseCalcomUrl).mockResolvedValue({ event_type_id: 42, slug: "intro" });
    vi.mocked(onboard).mockResolvedValue({
      workspace_id: "workspace_selected",
      agent_id: "agent_1",
      phone_number_id: "phone_1",
      phone_number: "+15555550100",
      phone_provisioned: true,
      calcom_connected: true,
      message: "ok",
    });
    vi.mocked(createCampaignFromCsv).mockResolvedValue({
      campaign_id: "campaign_1",
      campaign_name: "Lead Reactivation",
      campaign_status: "running",
      contacts_imported: 1,
      contacts_skipped: 0,
      contacts_failed: 0,
      phone_number_used: "+15555550100",
      agent_id: "agent_1",
      started_at: null,
      workspace_id: "workspace_selected",
    });

    const user = userEvent.setup();
    renderOnboarding();

    await user.click(
      screen.getByRole("button", { name: "Skip (I don't use Follow Up Boss)" })
    );
    await user.type(
      await screen.findByLabelText("Cal.com API Key"),
      "cal_live_test"
    );
    await user.type(
      screen.getByLabelText("Cal.com Booking URL"),
      "https://cal.com/realtor/intro"
    );
    await user.click(screen.getByRole("button", { name: "Next" }));

    await screen.findByRole("heading", { name: "Import Your Dead Leads" });
    const csv = new File(["first_name,phone\nAva,+15550000001\n"], "leads.csv", {
      type: "text/csv",
    });
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();
    await user.upload(fileInput as HTMLInputElement, csv);
    await screen.findByText("leads.csv");
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Second Team")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Launch Campaign" }));

    expect(
      await screen.findByRole("heading", { name: "Campaign launched" })
    ).toBeInTheDocument();
    expect(parseCalcomUrl).toHaveBeenCalledWith(
      "workspace_selected",
      "https://cal.com/realtor/intro",
      "cal_live_test"
    );
    expect(onboard).toHaveBeenCalledWith(
      "workspace_selected",
      expect.objectContaining({ calcom_event_type_id: 42 })
    );
    await waitFor(() =>
      expect(createCampaignFromCsv).toHaveBeenCalledWith(
        "workspace_selected",
        expect.any(File),
        expect.anything()
      )
    );
    expect(screen.getByText("Second Team")).toBeInTheDocument();
  });

  it("advances past Connect CRM with an empty Follow Up Boss API key", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    expect(
      screen.getByRole("heading", { name: "Connect Your CRM" })
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByRole("heading", { name: "Set Up Your Calendar" })
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Follow Up Boss API key is required.")
    ).not.toBeInTheDocument();
  });

  it("can reach Import Leads without Follow Up Boss and still requires CSV or FUB import before review", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    await user.click(
      screen.getByRole("button", {
        name: "Skip (I don't use Follow Up Boss)",
      })
    );
    expect(
      await screen.findByRole("heading", { name: "Set Up Your Calendar" })
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Cal.com API Key"), "cal_live_test");
    await user.type(
      screen.getByLabelText("Cal.com Booking URL"),
      "https://cal.com/realtor/intro"
    );
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByRole("heading", { name: "Import Your Dead Leads" })
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByText(
        "Import leads from Follow Up Boss or upload a CSV file."
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Review & Launch" })
    ).not.toBeInTheDocument();
  });
});
