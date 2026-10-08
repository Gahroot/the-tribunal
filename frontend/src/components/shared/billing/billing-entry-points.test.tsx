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
  getBillingAccount: vi.fn(),
  user: { id: 1 },
  createCheckout: vi.fn(),
  createPortal: vi.fn(),
  navigate: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  replace: vi.fn(),
  push: vi.fn(),
  searchParams: { value: new URLSearchParams() },
  activeBrand: "Brand B",
}));

vi.mock("@/providers/auth-provider", () => ({
  useAuth: () => ({ user: mocks.user }),
}));

vi.mock("@/lib/api/billing", () => ({
  getBillingAccount: mocks.getBillingAccount,
  getBillingStatus: mocks.getBillingStatus,
  createCheckout: mocks.createCheckout,
  createPortal: mocks.createPortal,
}));

vi.mock("@/components/shared/billing/billing-navigation", () => ({
  navigateToBillingProvider: mocks.navigate,
}));

vi.mock("@/components/layout/app-sidebar", () => ({
  AppSidebar: ({ children }: { children: ReactNode }) => <><span>Selected brand: {mocks.activeBrand}</span>{children}</>,
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
    billing_account: { id: "brand-a", name: "Brand A", kind: "workspace" },
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
  mocks.user = { id: 1 };
  mocks.activeBrand = "Brand B";
  window.history.replaceState({}, "", "/billing");
  mocks.getBillingAccount.mockResolvedValue({ id: "brand-a", name: "Brand A", kind: "workspace" });
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
    expect(screen.getByText("Billing account: Brand A")).toBeInTheDocument();
    expect(screen.getByText(/Shared company billing is not available yet/)).toBeInTheDocument();
    expect(mocks.getBillingStatus).toHaveBeenCalledWith("brand-a");
    // No fictional plan / card / invoice claims.
    expect(screen.queryByText(/Pro Plan|4242|Visa|Expires 12\/25/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get started|subscribe/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Manage subscription" }));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("https://billing.stripe.test/p"));
    expect(mocks.createPortal).toHaveBeenCalledWith("brand-a");
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

describe("billing account isolation", () => {
  it("shows account A with brand B selected and does not retarget on a sidebar switch", async () => {
    mocks.getBillingStatus.mockResolvedValue(status({ subscribed: true, portal_available: true }));
    mocks.createPortal.mockResolvedValue({ portal_url: "https://billing.stripe.test/a" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderWithClient(<BillingPage />, client);
    expect(await screen.findByText("Billing account: Brand A")).toBeInTheDocument();
    expect(screen.getByText("Selected brand: Brand B")).toBeInTheDocument();
    mocks.activeBrand = "Brand A";
    // Parent re-render after the sidebar context changes, keeping the query client.
    view.rerender(<QueryClientProvider client={client}><BillingPage /></QueryClientProvider>);
    expect(await screen.findByText("Billing account: Brand A")).toBeInTheDocument();
    expect(screen.getByText("Selected brand: Brand A")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Manage subscription" }));
    expect(mocks.createPortal).toHaveBeenCalledWith("brand-a");
    expect(mocks.getBillingStatus.mock.calls.every(([id]) => id === "brand-a")).toBe(true);
  });

  it("pins a returned explicit account instead of rediscovering a changed default", async () => {
    mocks.searchParams.value = new URLSearchParams("billing_account_id=brand-b");
    mocks.getBillingAccount.mockResolvedValue({ id: "brand-b", name: "Brand B", kind: "workspace" });
    mocks.getBillingStatus.mockResolvedValue(status({ billing_account: { id: "brand-b", name: "Brand B", kind: "workspace" }, subscribed: true, portal_available: true }));
    mocks.createPortal.mockResolvedValue({ portal_url: "https://billing.stripe.test/b" });
    renderWithClient(<BillingPage />);
    expect(await screen.findByText("Billing account: Brand B")).toBeInTheDocument();
    expect(mocks.getBillingAccount).toHaveBeenCalledWith("brand-b");
    expect(mocks.getBillingStatus).toHaveBeenCalledWith("brand-b");
    await userEvent.click(screen.getByRole("button", { name: "Manage subscription" }));
    expect(mocks.createPortal).toHaveBeenCalledWith("brand-b");
  });
  it("keys cached status by user and account, never by the active brand", () => {
    expect(queryKeys.billing.status(1, "brand-a")).not.toEqual(queryKeys.billing.status(1, "brand-b"));
    expect(queryKeys.billing.status(1, "brand-a")).not.toEqual(queryKeys.billing.status(2, "brand-a"));
    expect(queryKeys.billing.account(1)).not.toEqual(queryKeys.billing.account(2));
  });

  it("does not expose a cached owner's account to a different signed-in user", async () => {
    mocks.user = { id: 2 };
    mocks.getBillingAccount.mockRejectedValue(new Error("Admin access required"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(queryKeys.billing.account(1), { id: "brand-a", name: "Brand A", kind: "workspace" });
    client.setQueryData(queryKeys.billing.status(1, "brand-a"), status({ subscribed: true }));
    renderWithClient(<BillingSettingsTab />, client);
    expect(await screen.findByText("Couldn't load billing status")).toBeInTheDocument();
    expect(screen.queryByText("Billing account: Brand A")).not.toBeInTheDocument();
    expect(mocks.getBillingStatus).not.toHaveBeenCalled();
    expect(mocks.createPortal).not.toHaveBeenCalled();
  });
});

describe("unsubscribed accounts", () => {
  it("Settings hands off to the billing page so the price is seen before checkout", async () => {
    mocks.getBillingStatus.mockResolvedValue(status());
    renderWithClient(<BillingSettingsTab />);

    const link = await screen.findByRole("link", { name: "View plan and subscribe" });
    expect(link).toHaveAttribute("href", "/billing?billing_account_id=brand-a");
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
    expect(mocks.createCheckout).toHaveBeenCalledWith("brand-a");
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
