import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  connectFub,
  createCampaignFromCsv,
  getFubConnection,
  importFubContacts,
  launchFubCampaign,
  onboard,
  parseCalcomUrl,
  verifyFub,
} from "@/lib/api/realtor";

import OnboardingPage from "./page";

// "workspace_default" is the user's default; the operator has selected the
// second workspace, which guided setup must target end to end (RF-005).
const workspaceState = vi.hoisted(() => ({
  currentWorkspaceId: "workspace_selected" as string | null,
  workspaces: [
    {
      workspace: { id: "workspace_default", name: "Default Realty" },
      is_default: true,
    },
    {
      workspace: { id: "workspace_selected", name: "Second Team" },
      is_default: false,
    },
  ],
}));

vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: () => workspaceState,
}));

vi.mock("@/lib/api/realtor", () => ({
  connectFub: vi.fn(),
  createCampaignFromCsv: vi.fn(),
  getFubConnection: vi.fn(),
  importFubContacts: vi.fn(),
  launchFubCampaign: vi.fn(),
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
    </QueryClientProvider>,
  );
}

describe("Onboarding wizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.currentWorkspaceId = "workspace_selected";
    vi.mocked(getFubConnection).mockResolvedValue({ connected: false });
  });

  it("runs every setup call against the selected (non-default) workspace", async () => {
    vi.mocked(parseCalcomUrl).mockResolvedValue({
      event_type_id: 42,
      slug: "intro",
    });
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

    await user.click(screen.getByRole("button", { name: "Skip (I don't use Follow Up Boss)" }));
    await user.type(await screen.findByLabelText("Cal.com API Key"), "cal_live_test");
    await user.type(screen.getByLabelText("Cal.com Booking URL"), "https://cal.com/realtor/intro");
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

    expect(await screen.findByRole("heading", { name: "Campaign launched" })).toBeInTheDocument();
    expect(parseCalcomUrl).toHaveBeenCalledWith(
      "workspace_selected",
      "https://cal.com/realtor/intro",
      "cal_live_test",
    );
    expect(onboard).toHaveBeenCalledWith(
      "workspace_selected",
      expect.objectContaining({ calcom_event_type_id: 42 }),
    );
    await waitFor(() =>
      expect(createCampaignFromCsv).toHaveBeenCalledWith(
        "workspace_selected",
        expect.any(File),
        expect.anything(),
      ),
    );
    expect(screen.getByText("Second Team")).toBeInTheDocument();
  });

  it("advances past Connect CRM with an empty Follow Up Boss API key", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    expect(screen.getByRole("heading", { name: "Connect Your CRM" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByRole("heading", { name: "Set Up Your Calendar" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Follow Up Boss API key is required.")).not.toBeInTheDocument();
  });

  it("can reach Import Leads without Follow Up Boss and still requires CSV or FUB import before review", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    await user.click(
      screen.getByRole("button", {
        name: "Skip (I don't use Follow Up Boss)",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "Set Up Your Calendar" }),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Cal.com API Key"), "cal_live_test");
    await user.type(screen.getByLabelText("Cal.com Booking URL"), "https://cal.com/realtor/intro");
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByRole("heading", { name: "Import Your Dead Leads" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByText("Import leads from Follow Up Boss or upload a CSV file."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review & Launch" })).not.toBeInTheDocument();
  });
});

describe("Onboarding wizard: Follow Up Boss connect + import (RF-008)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.currentWorkspaceId = "workspace_selected";
    vi.mocked(getFubConnection).mockResolvedValue({ connected: false });
  });

  async function connectWithKey(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Follow Up Boss API Key (optional)"), "fub_test_key");
    await user.click(screen.getByRole("button", { name: "Connect" }));
  }

  async function goToLeads(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.type(await screen.findByLabelText("Cal.com API Key"), "cal_live_test");
    await user.type(screen.getByLabelText("Cal.com Booking URL"), "https://cal.com/realtor/intro");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: "Import Your Dead Leads" });
  }

  it("verifies, saves on the selected (non-default) workspace, then imports there", async () => {
    vi.mocked(verifyFub).mockResolvedValue({ valid: true, name: "Pat Agent" });
    // The status endpoint reflects what the save persisted, as the backend does.
    const saved = { connected: true, account_name: "Pat Agent" };
    vi.mocked(connectFub).mockImplementation(async () => {
      vi.mocked(getFubConnection).mockResolvedValue(saved);
      return saved;
    });
    vi.mocked(importFubContacts).mockResolvedValue({
      imported: 2,
      skipped: 0,
      failed: 1,
      failures: [{ fub_id: 103, reason: "missing_phone" }],
    });
    const user = userEvent.setup();
    renderOnboarding();

    await connectWithKey(user);

    expect(await screen.findByText("Connected as Pat Agent")).toBeInTheDocument();
    expect(verifyFub).toHaveBeenCalledWith("fub_test_key");
    expect(connectFub).toHaveBeenCalledWith("workspace_selected", "fub_test_key");
    expect(vi.mocked(verifyFub).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(connectFub).mock.invocationCallOrder[0],
    );

    await goToLeads(user);
    await user.click(screen.getByRole("button", { name: "Import All Leads" }));

    expect(await screen.findByText(/2 leads imported/)).toBeInTheDocument();
    expect(screen.getByText(/1 couldn't be imported/)).toBeInTheDocument();
    expect(screen.getByText(/Follow Up Boss lead 103: no phone number/)).toBeInTheDocument();
    expect(importFubContacts).toHaveBeenCalledWith(
      "workspace_selected",
      true,
      undefined,
      undefined,
      false,
    );
    expect(connectFub).not.toHaveBeenCalledWith("workspace_default", expect.anything());
    expect(importFubContacts).not.toHaveBeenCalledWith("workspace_default", expect.anything());
  });

  it.each(["running", "deferred", "scheduled", "blocked"] as const)(
    "launches partial FUB imports and shows the authoritative %s outcome",
    async (launchStatus) => {
      vi.mocked(getFubConnection).mockResolvedValue({ connected: true });
      vi.mocked(importFubContacts).mockResolvedValue({
        imported: 2,
        skipped: 1,
        failed: 1,
        contact_ids: [11, 12, 13],
        failures: [{ fub_id: 103, reason: "missing_phone" }],
      });
      vi.mocked(parseCalcomUrl).mockResolvedValue({
        event_type_id: 42,
        slug: "intro",
      });
      vi.mocked(onboard).mockResolvedValue({
        workspace_id: "workspace_selected",
        agent_id: "agent_1",
        phone_number_id: "phone_1",
        phone_number: "+15555550100",
        phone_provisioned: true,
        calcom_connected: true,
        message: "ok",
      });
      vi.mocked(launchFubCampaign).mockResolvedValue({
        campaign_id: "fub_campaign_1",
        campaign_status:
          launchStatus === "blocked"
            ? "draft"
            : launchStatus === "deferred"
              ? "running"
              : launchStatus,
        launch_status: launchStatus,
        message:
          launchStatus === "blocked" ? "No SMS consent on file" : "Authoritative launch result",
      });
      const user = userEvent.setup();
      renderOnboarding();
      await screen.findByText("Connected");
      await goToLeads(user);
      await user.click(screen.getByRole("button", { name: "Import All Leads" }));
      await screen.findByText(/2 leads imported/);
      expect(screen.queryByRole("heading", { name: "Campaign launched" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Next" }));
      await user.click(screen.getByRole("button", { name: "Launch Campaign" }));
      const heading = launchStatus === "running" ? "Campaign launched" : `Campaign ${launchStatus}`;
      await screen.findByRole("heading", { name: heading });
      expect(screen.getByText(/Campaign ID: fub_campaign_1/)).toBeInTheDocument();
      expect(launchFubCampaign).toHaveBeenCalledWith(
        "workspace_selected",
        [11, 12, 13],
        "Lead Reactivation",
      );
      expect(createCampaignFromCsv).not.toHaveBeenCalled();
      expect(screen.getByText(/1 row could not be/)).toBeInTheDocument();
      if (launchStatus === "blocked") {
        await user.click(screen.getByRole("button", { name: "Review and retry launch" }));
        await user.click(screen.getByRole("button", { name: "Launch Campaign" }));
        await screen.findByRole("heading", { name: heading });
        expect(launchFubCampaign).toHaveBeenCalledTimes(2);
        expect(importFubContacts).toHaveBeenCalledTimes(1);
        expect(onboard).toHaveBeenCalledTimes(1);
      }
    },
  );

  it("does not show connected or enable import when saving fails", async () => {
    vi.mocked(verifyFub).mockResolvedValue({ valid: true, name: "Pat Agent" });
    vi.mocked(connectFub).mockRejectedValue(new Error("db down"));
    const user = userEvent.setup();
    renderOnboarding();

    await connectWithKey(user);

    expect(await screen.findByText(/couldn't save the connection|db down/)).toBeInTheDocument();
    expect(screen.queryByText(/Connected as/)).not.toBeInTheDocument();

    await goToLeads(user);
    expect(screen.getByRole("button", { name: "Import All Leads" })).toBeDisabled();
    expect(importFubContacts).not.toHaveBeenCalled();
  });

  it("blocks connecting when no workspace is selected", async () => {
    workspaceState.currentWorkspaceId = null;
    const user = userEvent.setup();
    renderOnboarding();

    expect(
      screen.getByText(/No workspace selected. Pick a workspace to connect/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
    await user.type(screen.getByLabelText("Follow Up Boss API Key (optional)"), "fub_test_key");
    expect(verifyFub).not.toHaveBeenCalled();
    expect(connectFub).not.toHaveBeenCalled();
    expect(getFubConnection).not.toHaveBeenCalled();
  });

  it("shows a saved connection after reload without re-entering the key", async () => {
    vi.mocked(getFubConnection).mockResolvedValue({
      connected: true,
      account_name: "Pat Agent",
    });
    const user = userEvent.setup();
    renderOnboarding();

    expect(await screen.findByText("Connected as Pat Agent")).toBeInTheDocument();
    expect(getFubConnection).toHaveBeenCalledWith("workspace_selected");

    await goToLeads(user);
    expect(screen.getByRole("button", { name: "Import All Leads" })).toBeEnabled();
    expect(verifyFub).not.toHaveBeenCalled();
  });

  it("keeps a saved connection when a new key check fails transiently", async () => {
    vi.mocked(getFubConnection).mockResolvedValue({
      connected: true,
      account_name: "Pat Agent",
    });
    vi.mocked(verifyFub).mockRejectedValue(new Error("Network Error"));
    const user = userEvent.setup();
    renderOnboarding();

    await screen.findByText("Connected as Pat Agent");
    await user.type(screen.getByLabelText("Follow Up Boss API Key (optional)"), "fub_other_key");
    await user.click(screen.getByRole("button", { name: "Reconnect" }));

    expect(await screen.findByText(/Network Error|Couldn't check the key/)).toBeInTheDocument();
    expect(screen.getByText("Connected as Pat Agent")).toBeInTheDocument();
    expect(connectFub).not.toHaveBeenCalled();
  });

  it("re-running the import reports already-present leads instead of duplicating", async () => {
    vi.mocked(getFubConnection).mockResolvedValue({ connected: true });
    vi.mocked(importFubContacts)
      .mockResolvedValueOnce({
        imported: 2,
        skipped: 0,
        failed: 0,
        failures: [],
      })
      .mockResolvedValueOnce({
        imported: 0,
        skipped: 2,
        failed: 0,
        failures: [],
      });
    const user = userEvent.setup();
    renderOnboarding();

    await screen.findByText("Connected");
    await goToLeads(user);
    await user.click(screen.getByRole("button", { name: "Import All Leads" }));
    expect(await screen.findByText(/2 leads imported/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Import Again" }));
    expect(await screen.findByText(/2 already in this workspace/)).toBeInTheDocument();
    expect(screen.getByText(/0 leads imported/)).toBeInTheDocument();
    expect(importFubContacts).toHaveBeenCalledTimes(2);
    for (const call of vi.mocked(importFubContacts).mock.calls) {
      expect(call).toEqual(["workspace_selected", true, undefined, undefined, false]);
    }
  });
});
