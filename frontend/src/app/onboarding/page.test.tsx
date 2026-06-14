import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import OnboardingPage from "./page";

vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: () => ({ currentWorkspaceId: "workspace_1" }),
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
        name: "Skip — I don't use Follow Up Boss",
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
