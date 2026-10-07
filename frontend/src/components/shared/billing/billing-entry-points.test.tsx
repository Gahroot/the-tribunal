import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "@/app/billing/page";
import { BillingSettingsTab } from "@/components/settings/billing-settings-tab";
import type { BillingStatus } from "@/lib/api/billing";
import { queryKeys } from "@/lib/query-keys";

const mocks = vi.hoisted(() => ({
  getBillingStatus: vi.fn(),
  createCheckout: vi.fn(),
  createPortal: vi.fn(),
  navigate: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  replace: vi.fn(),
  push: vi.fn(),
  searchParams: { value: new URLSearchParams() },
}));

vi.mock("@/lib/api/billing", () => ({
  getBillingStatus: mocks.getBillingStatus,
  createCheckout: mocks.createCheckout,
  createPortal: mocks.createPortal,
}));

vi.mock("@/components/shared/billing/billing-navigation", () => ({
  navigateToBillingProvider: mocks.navigate,
}));

vi.mock("@/components/layout/app-sidebar", () => ({
  AppSidebar: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("sonner", () => ({
  toast: Object.assign(mocks.toastInfo, {
    error: mocks.toastError,
    success: mocks.toastSuccess,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
  useSearchParams: () => mocks.searchParams.value,
  usePathname: () => "/billing",
}));

function status(overrides: Partial<BillingStatus> = {}): BillingStatus {
  return {
    subscribed: false,
    plan: null,
    status: null,
    current_period_end: null,
    configured: true,
    checkout_available: true,
    portal_available: false,
    ...overrides,
  };
}

function renderWithClient(
  ui: ReactNode,
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const ENTRY_POINTS = [
  { name: "Settings → Billing", ui: () => <BillingSettingsTab /> },
  { name: "/billing page", ui: () => <BillingPage /> },
] as const;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.searchParams.value = new URLSearchParams();
});

describe.each(ENTRY_POINTS)("$name", ({ ui }) => {
  it("shows the real active subscription and opens the Stripe portal", async () => {
    mocks.getBillingStatus.mockResolvedValue(
      status({ subscribed: true, plan: "Realtor Monthly", status: "active", portal_available: true }),
    );
    mocks.createPortal.mockResolvedValue({ portal_url: "https://billing.stripe.test/p" });
    renderWithClient(ui());

    expect(await screen.findByText("Realtor Monthly")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    // No fictional plan / card / invoice claims.
    expect(screen.queryByText(/Pro Plan|4242|Visa|Expires 12\/25/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started|subscribe/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Manage subscription" }));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("https://billing.stripe.test/p"));
  });

  it("surfaces a portal failure instead of a dead click", async () => {
    mocks.getBillingStatus.mockResolvedValue(
      status({ subscribed: true, status: "active", portal_available: true }),
    );
    mocks.createPortal.mockRejectedValue(
      Object.assign(new Error("x"), { response: { data: { detail: "Stripe error: try later" } } }),
    );
    renderWithClient(ui());

    const button = await screen.findByRole("button", { name: "Manage subscription" });
    await userEvent.click(button);
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith("Stripe error: try later"));
    expect(mocks.navigate).not.toHaveBeenCalled();
    expect(button).toBeEnabled();
  });

  it("explains when billing isn't configured and offers no payment controls", async () => {
    mocks.getBillingStatus.mockResolvedValue(
      status({ configured: false, checkout_available: false }),
    );
    renderWithClient(ui());

    expect(await screen.findByText("Billing isn't set up yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started|manage|subscribe/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /subscribe/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(mocks.getBillingStatus).toHaveBeenCalledTimes(2));
  });

  it("shows a retryable error rather than treating a failed lookup as unsubscribed", async () => {
    mocks.getBillingStatus.mockRejectedValueOnce(
      Object.assign(new Error("x"), {
        response: { data: { detail: "Couldn't reach the billing provider. Please try again." } },
      }),
    );
    renderWithClient(ui());

    expect(await screen.findByText("Couldn't load billing status")).toBeInTheDocument();
    expect(screen.getByText(/Couldn't reach the billing provider/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started/i })).not.toBeInTheDocument();

    mocks.getBillingStatus.mockResolvedValueOnce(status({ subscribed: true, status: "active" }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Active")).toBeInTheDocument();
  });

  it("asks a past-due subscriber to fix payment, not to subscribe again", async () => {
    mocks.getBillingStatus.mockResolvedValue(
      status({ status: "past_due", portal_available: true }),
    );
    renderWithClient(ui());

    expect(await screen.findByText("Past due")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update payment details" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /subscribe/i })).not.toBeInTheDocument();
  });

  it("says when no plan is configured instead of offering checkout", async () => {
    mocks.getBillingStatus.mockResolvedValue(status({ checkout_available: false }));
    renderWithClient(ui());

    expect(await screen.findByText(/no plan is configured/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /subscribe/i })).not.toBeInTheDocument();
  });
});

describe("unsubscribed accounts", () => {
  it("Settings hands off to the billing page so the price is seen before checkout", async () => {
    mocks.getBillingStatus.mockResolvedValue(status());
    renderWithClient(<BillingSettingsTab />);

    const link = await screen.findByRole("link", { name: "View plan and subscribe" });
    expect(link).toHaveAttribute("href", "/billing");
    expect(screen.getByText("No active subscription")).toBeInTheDocument();
    expect(mocks.createCheckout).not.toHaveBeenCalled();
  });

  it("/billing starts Stripe Checkout with pending feedback", async () => {
    mocks.getBillingStatus.mockResolvedValue(status());
    let resolveCheckout: (v: { checkout_url: string }) => void = () => {};
    mocks.createCheckout.mockReturnValue(
      new Promise((resolve) => {
        resolveCheckout = resolve;
      }),
    );
    renderWithClient(<BillingPage />);

    const button = await screen.findByRole("button", { name: "Get Started" });
    expect(screen.getByText("No active subscription")).toBeInTheDocument();
    await userEvent.click(button);
    expect(button).toBeDisabled();
    resolveCheckout({ checkout_url: "https://checkout.stripe.test/cs" });
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("https://checkout.stripe.test/cs"));
  });
});

describe("/billing checkout return", () => {
  it("confirms a successful checkout, refreshes status, and clears the param", async () => {
    mocks.searchParams.value = new URLSearchParams("checkout=success");
    mocks.getBillingStatus.mockResolvedValue(status());
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderWithClient(<BillingPage />, client);

    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledTimes(1));
    expect(mocks.replace).toHaveBeenCalledWith("/billing");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.billing.status() });
  });

  it("tells the operator a canceled checkout didn't charge them", async () => {
    mocks.searchParams.value = new URLSearchParams("checkout=canceled");
    mocks.getBillingStatus.mockResolvedValue(status());
    renderWithClient(<BillingPage />);

    await waitFor(() =>
      expect(mocks.toastInfo).toHaveBeenCalledWith("Checkout canceled. You weren't charged."),
    );
    expect(mocks.replace).toHaveBeenCalledWith("/billing");
  });
});
