import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { agentsApi } from "@/lib/api/agents";
import { campaignsApi } from "@/lib/api/campaigns";
import { contactsApi } from "@/lib/api/contacts";
import { integrationsApi } from "@/lib/api/integrations";
import { phoneNumbersApi } from "@/lib/api/phone-numbers";

import { SetupChecklist } from "./setup-checklist";
import { SetupGate } from "./setup-gate";

vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: () => ({ currentWorkspaceId: "ws_1", isPending: false }),
}));

vi.mock("@/lib/api/phone-numbers", () => ({ phoneNumbersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/agents", () => ({ agentsApi: { list: vi.fn() } }));
vi.mock("@/lib/api/contacts", () => ({ contactsApi: { list: vi.fn() } }));
vi.mock("@/lib/api/integrations", () => ({ integrationsApi: { bookingReadiness: vi.fn() } }));
vi.mock("@/lib/api/campaigns", () => ({ campaignsApi: { list: vi.fn() } }));

const { toastSuccess } = vi.hoisted(() => ({ toastSuccess: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: toastSuccess } }));

const phoneList = vi.mocked(phoneNumbersApi.list);
const agentList = vi.mocked(agentsApi.list);
const contactList = vi.mocked(contactsApi.list);
const integrationList = vi.mocked(integrationsApi.bookingReadiness);
const campaignList = vi.mocked(campaignsApi.list);

const page = (total: number, items: unknown[] = []) =>
  ({ items, total, page: 1, page_size: 1, pages: 1 }) as never;
const serverError = () => Object.assign(new Error("Internal Server Error"), { status: 500 });

/** Every probe answers with real data; `done` decides whether each step is proven done. */
function respondAll(done: boolean) {
  phoneList.mockResolvedValue(page(done ? 1 : 0));
  agentList.mockResolvedValue(page(done ? 2 : 0));
  contactList.mockResolvedValue(page(done ? 40 : 0));
  integrationList.mockResolvedValue({
    ready: done,
    description: done ? "Booking calendar configured." : "Connect Cal.com.",
    href: "/settings?tab=integrations",
  });
  campaignList.mockResolvedValue(page(done ? 1 : 0, done ? [{ status: "running" }] : []));
}

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      // Mirror the app: server errors escalate to the error boundary by
      // default, so the probes must opt out to stay inline.
      queries: { retry: false, staleTime: 0, throwOnError: true },
    },
  });
  const utils = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  return { ...utils, queryClient };
}

function stepLink(title: string) {
  return screen.getByRole("link", { name: new RegExp(title) });
}

beforeEach(() => {
  respondAll(false);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("SetupChecklist", () => {
  it("keeps guidance and offers a retry when every probe fails initially", async () => {
    for (const list of [phoneList, agentList, contactList, integrationList, campaignList]) {
      list.mockRejectedValue(serverError());
    }
    renderWithClient(<SetupChecklist />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't check your setup");
    // Failures are neither success nor zero resources: every step is unknown.
    expect(stepLink("Connect a phone number")).toHaveAccessibleName(/couldn't check/);
    expect(stepLink("Create your first agent")).toHaveAttribute("href", "/agents/create");
    // The import step deep-links into the Contacts import dialog, not the bare list.
    expect(stepLink("Import contacts")).toHaveAttribute("href", "/contacts?import=true");
    expect(screen.getByText("0 of 5 complete, 5 not checked")).toBeInTheDocument();
    expect(screen.queryByText("You're all set!")).not.toBeInTheDocument();
    expect(screen.queryByText(/\(todo\)/)).not.toBeInTheDocument();

    // No automatic retry loop: each probe ran exactly once.
    expect(phoneList).toHaveBeenCalledTimes(1);

    // Retry recovers to a confirmed-empty (incomplete) setup. While it is in
    // flight the guidance stays up (no skeleton flash) and retry is disabled.
    respondAll(false);
    let releasePhone: () => void = () => {};
    phoneList.mockImplementationOnce(
      () => new Promise((resolve) => (releasePhone = () => resolve(page(0)))),
    );
    await userEvent.click(within(alert).getByRole("button", { name: "Retry check" }));

    expect(await screen.findByRole("button", { name: "Checking…" })).toBeDisabled();
    expect(stepLink("Connect a phone number")).toHaveAccessibleName(/couldn't check/);
    releasePhone();

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByText("0 of 5 complete")).toBeInTheDocument();
    expect(stepLink("Connect a phone number")).toHaveAccessibleName(/\(todo\)/);
    expect(phoneList).toHaveBeenCalledTimes(2);
  });

  it("keeps working sections on a partial failure and retries only the failed probe", async () => {
    respondAll(true);
    phoneList.mockRejectedValue(serverError());
    renderWithClient(<SetupChecklist />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't check 1 of 5 steps");
    expect(stepLink("Connect a phone number")).toHaveAccessibleName(/couldn't check/);
    expect(stepLink("Create your first agent")).toHaveAccessibleName(/\(complete\)/);
    expect(screen.getByText("4 of 5 complete, 1 not checked")).toBeInTheDocument();
    // Unknown is not complete.
    expect(screen.queryByText("You're all set!")).not.toBeInTheDocument();

    phoneList.mockResolvedValue(page(1));
    await userEvent.click(within(alert).getByRole("button", { name: "Retry check" }));

    expect(await screen.findByText("You're all set!")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(phoneList).toHaveBeenCalledTimes(2);
    for (const list of [agentList, contactList, integrationList, campaignList]) {
      expect(list).toHaveBeenCalledTimes(1);
    }
    // Revealing already-finished steps is not "just finished setup".
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("keeps the last valid progress when a later refresh fails", async () => {
    respondAll(false);
    agentList.mockResolvedValue(page(1));
    const { queryClient } = renderWithClient(<SetupChecklist />);

    expect(await screen.findByText("1 of 5 complete")).toBeInTheDocument();

    agentList.mockRejectedValue(serverError());
    await queryClient.invalidateQueries();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't refresh your setup progress");
    expect(alert).toHaveTextContent("Showing your last known progress.");
    expect(stepLink("Create your first agent")).toHaveAccessibleName(/\(complete\)/);
    expect(screen.getByText("1 of 5 complete")).toBeInTheDocument();
  });

  it("keeps an active connection with no event type incomplete and links to the control", async () => {
    respondAll(true);
    integrationList.mockResolvedValue({
      ready: false,
      description: "Set the Cal.com Event Type ID for your default agent.",
      href: "/agents/default?setup=calendar",
    });
    renderWithClient(<SetupChecklist />);
    expect(await screen.findByText("4 of 5 complete")).toBeInTheDocument();
    expect(stepLink("Connect your calendar")).toHaveAttribute("href", "/agents/default?setup=calendar");
    expect(stepLink("Connect your calendar")).toHaveAccessibleName(/\(todo\)/);
    expect(screen.getByText(/Set the Cal.com Event Type ID/)).toBeInTheDocument();
  });

  it("preserves calendar readiness as unknown on failure and recovers on retry", async () => {
    respondAll(true);
    integrationList.mockRejectedValue(serverError());
    renderWithClient(<SetupChecklist />);
    expect(await screen.findByText("4 of 5 complete, 1 not checked")).toBeInTheDocument();
    expect(stepLink("Connect your calendar")).toHaveAccessibleName(/couldn't check/);
    respondAll(true);
    await userEvent.click(screen.getByRole("button", { name: "Retry check" }));
    expect(await screen.findByText("You're all set!")).toBeInTheDocument();
  });

  it("keeps cached calendar readiness stale when a refresh fails", async () => {
    respondAll(true);
    const { queryClient } = renderWithClient(<SetupChecklist />);
    await screen.findByText("You're all set!");
    integrationList.mockRejectedValue(serverError());
    await queryClient.invalidateQueries();
    expect(await screen.findByRole("alert")).toHaveTextContent("last known progress");
    expect(stepLink("Connect your calendar")).toHaveAccessibleName(/\(complete\)/);
  });

  it("celebrates a genuinely completed setup without an error notice", async () => {
    respondAll(true);
    renderWithClient(<SetupChecklist />);

    expect(await screen.findByText("You're all set!")).toBeInTheDocument();
    expect(screen.getByText("5 of 5 complete")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Go to Today/ })).toHaveAttribute("href", "/today");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("SetupGate", () => {
  it("shows the checklist with a retry instead of disappearing when probes fail", async () => {
    contactList.mockRejectedValue(serverError());
    renderWithClient(<SetupGate />);

    const card = await screen.findByRole("region", { name: "Finish setup checklist" });
    expect(within(card).getByRole("alert")).toHaveTextContent("We couldn't check 1 of 5 steps");
    expect(within(card).getByRole("button", { name: "Retry check" })).toBeEnabled();

    // Mounting the card inside the gate must not re-fire the failed probe
    // (which would unmount and remount the card in a loop).
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(contactList).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("region", { name: "Finish setup checklist" })).toBeInTheDocument();
  });
});
