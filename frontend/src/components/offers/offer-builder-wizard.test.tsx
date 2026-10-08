import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Suspense } from "react";
import { describe, expect, it, vi } from "vitest";

import PublicOfferPage from "@/app/p/offers/[slug]/page";
import { offersApi } from "@/lib/api/offers";
import { server } from "@/test/msw/server";
import type { Offer } from "@/types";

import { OfferBuilderWizard } from "./offer-builder-wizard";

// Keep real wizard steps and API serialization, without exit-animation timers.
vi.mock("motion/react", async () => {
  const { createElement } = await import("react");
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
    motion: new Proxy({}, { get: (_, tag: string) =>
      ({ children, ...props }: Record<string, unknown>) =>
        createElement(tag, Object.fromEntries(Object.entries(props).filter(([key]) =>
          !["initial", "animate", "exit", "layout", "transition"].includes(key)
        )), children as React.ReactNode),
    }),
  };
});

function fixture(overrides: Record<string, unknown> = {}) {
  let saved: Record<string, unknown> = {
    id: "offer-fixture", workspace_id: "workspace-fixture", name: "Fixture Offer",
    description: "Old description", headline: "Old headline", terms: "Keep terms",
    discount_type: "fixed", discount_value: 10, regular_price: 100, offer_price: 50,
    savings_amount: 0, guarantee_type: "money_back", guarantee_days: 0,
    guarantee_text: "Old guarantee", cta_text: "Join", is_active: true,
    is_public: true, public_slug: "fixture", require_email: false,
    require_phone: true, require_name: false,
    value_stack_items: [{ name: "Training", value: 100, included: true }],
    lead_magnets: [], created_at: "2026-01-01", updated_at: "2026-01-01",
    ...overrides,
  };
  const writes: Record<string, unknown>[] = [];
  server.use(
    http.get("*/api/v1/workspaces/workspace-fixture/lead-magnets", () => HttpResponse.json({ items: [] })),
    http.get("*/api/v1/workspaces/workspace-fixture/offers/offer-fixture", () => HttpResponse.json(saved)),
    http.put("*/api/v1/workspaces/workspace-fixture/offers/offer-fixture", async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      writes.push(body);
      saved = { ...saved, ...body };
      return HttpResponse.json(saved);
    }),
    http.post("*/api/v1/workspaces/workspace-fixture/offers", async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      writes.push(body);
      saved = { ...saved, ...body };
      return HttpResponse.json(saved, { status: 201 });
    }),
    http.get("*/api/v1/p/offers/fixture", () => HttpResponse.json(saved)),
  );
  return { offer: saved as unknown as Offer, writes };
}

function mount(existingOffer?: Offer, onSuccess = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    <OfferBuilderWizard workspaceId="workspace-fixture" existingOffer={existingOffer} onSuccess={onSuccess} />
  </QueryClientProvider>);
}

async function save(edit = true) {
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
  fireEvent.click(screen.getByRole("button", { name: edit ? "Update Offer" : "Create Offer" }));
}

describe("RF-023 exact bonus selection", () => {
  const magnets = ["First", "Second"].map((name, index) => ({
    id: `magnet-${index}`, name, magnet_type: "pdf", delivery_method: "email",
    is_active: true, download_count: 0,
  }));

  it.each([[2, 1], [1, 0], [2, 2]])("saves %s bonuses as %s without additive calls", async (initial, retained) => {
    const { offer, writes } = fixture({ lead_magnets: magnets.slice(0, initial) });
    server.use(http.get("*/api/v1/workspaces/workspace-fixture/lead-magnets", () => HttpResponse.json({ items: magnets })));
    const onSuccess = vi.fn();
    mount(offer, onSuccess);
    fireEvent.click(screen.getByRole("button", { name: "Lead Magnets" }));
    await screen.findByText("First");
    expect(screen.getAllByRole("checkbox").slice(0, initial).every((box) => box.getAttribute("data-state") === "checked")).toBe(true);
    for (let index = retained; index < initial; index++) {
      fireEvent.click(screen.getAllByRole("checkbox")[index]);
    }
    await save();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(writes).toEqual([initial === retained ? {} : { lead_magnet_ids: magnets.slice(0, retained).map((m) => m.id) }]);
  });

  it("keeps edits and does not report success after reconciliation fails", async () => {
    const { offer } = fixture({ lead_magnets: magnets.slice(0, 1) });
    const attempts: unknown[] = [];
    server.use(
      http.get("*/api/v1/workspaces/workspace-fixture/lead-magnets", () => HttpResponse.json({ items: magnets })),
      http.put("*/api/v1/workspaces/workspace-fixture/offers/offer-fixture", async ({ request }) => {
        attempts.push(await request.json());
        return HttpResponse.json({ detail: "Fixture transaction failed" }, { status: 500 });
      }),
    );
    const onSuccess = vi.fn();
    mount(offer, onSuccess);
    fireEvent.click(screen.getByRole("button", { name: "Lead Magnets" }));
    await screen.findByText("First");
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save");
    expect(onSuccess).not.toHaveBeenCalled();
    expect(attempts).toEqual([{ lead_magnet_ids: [] }]);
    fireEvent.click(screen.getByRole("button", { name: "Update Offer" }));
    await waitFor(() => expect(attempts).toHaveLength(2));
    expect(attempts[1]).toEqual({ lead_magnet_ids: [] });
  });
});

describe("RF-024 offer edits", () => {
  it.each([
    { regular_price: null, offer_price: 0, expected: "$0" },
    { regular_price: 0, offer_price: 0, expected: "$0" },
    { regular_price: 100, offer_price: null, expected: null },
  ])("renders a free price without requiring an anchor, but not a null price: %j", async ({ expected, ...prices }) => {
    fixture(prices);
    const params = Object.assign(Promise.resolve({ slug: "fixture" }), { status: "fulfilled", value: { slug: "fixture" } });
    render(<QueryClientProvider client={new QueryClient()}><Suspense fallback={null}>
      <PublicOfferPage params={params} />
    </Suspense></QueryClientProvider>);
    await screen.findByText("Old headline");
    if (expected) expect(screen.getByText(expected)).toBeInTheDocument();
    else expect(screen.queryByText("$0")).not.toBeInTheDocument();
    expect(document.querySelector(".line-through")).not.toBeInTheDocument();
  });
  it("saves clears, an empty stack and zero price, reads them back, and publicly renders $0", async () => {
    const { offer, writes } = fixture();
    const view = mount(offer);
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Pricing" }));
    fireEvent.change(screen.getByLabelText("Your Price ($)"), { target: { value: "0" } });
    expect(screen.getByLabelText("Your Price ($)")).toHaveValue(0);
    fireEvent.click(screen.getByRole("button", { name: "Guarantee" }));
    expect(screen.getByLabelText("Guarantee Period (Days)")).toHaveValue(0);
    fireEvent.change(screen.getByLabelText("Custom Guarantee Text"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Value Stack" }));
    // The existing icon-only remove button, scoped to its item card.
    const item = screen.getByDisplayValue("Training").closest("[data-slot='card-content']")!;
    fireEvent.click(item.querySelector("button.text-destructive")!);
    await save();
    await waitFor(() => expect(writes).toEqual([{
      description: null, offer_price: 0, guarantee_text: null, value_stack_items: [],
    }]));
    const reopened = await offersApi.get("workspace-fixture", offer.id);
    expect(reopened).toMatchObject({ ...offer, description: null, offer_price: 0, guarantee_text: null, value_stack_items: [] });
    view.unmount();
    const params = Object.assign(Promise.resolve({ slug: "fixture" }), { status: "fulfilled", value: { slug: "fixture" } });
    render(<QueryClientProvider client={new QueryClient()}><Suspense fallback={null}>
      <PublicOfferPage params={params} />
    </Suspense></QueryClientProvider>);
    expect(await screen.findByText("$0")).toBeInTheDocument();
    expect(screen.getByText("$100")).toHaveClass("line-through");
    expect(screen.queryByText("Old guarantee")).not.toBeInTheDocument();
    expect(screen.queryByText("Training")).not.toBeInTheDocument();
  });

  it.each([
    ["accepted", "accepted"], ["failed", "failed"], ["unavailable", "unavailable"],
    ["accepted", "failed"], ["missing_email", "missing_email"], ["pending", "pending"],
  ])("reports bonus acceptance truthfully (%s/%s) with direct recovery", async (first, second) => {
    fixture({
      require_email: true, require_phone: false,
      lead_magnets: ["first", "second"].map((id) => ({
        id, name: `${id} guide`, magnet_type: "pdf", delivery_method: "email",
        content_url: `https://example.test/${id}.pdf`,
      })),
    });
    let submissions = 0;
    server.use(http.post("*/api/v1/p/offers/fixture/opt-in", () => {
      submissions += 1;
      return HttpResponse.json({ success: true, message: "Signup saved", deliveries: [
        { lead_magnet_id: "first", status: first }, { lead_magnet_id: "second", status: second },
      ] });
    }));
    const params = Object.assign(Promise.resolve({ slug: "fixture" }), { status: "fulfilled", value: { slug: "fixture" } });
    render(<QueryClientProvider client={new QueryClient()}><Suspense fallback={null}>
      <PublicOfferPage params={params} />
    </Suspense></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "fixture@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Join" }));
    expect(await screen.findByRole("heading", { name: "You're In!" })).toBeInTheDocument();
    const accepted = [first, second].filter((state) => state === "accepted").length;
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Your signup is saved.");
    if (accepted) {
      expect(status).toHaveTextContent(`${accepted} of 2 bonus emails accepted`);
      expect(status).toHaveTextContent("does not confirm inbox receipt");
    } else expect(status).not.toHaveTextContent("check your inbox");
    expect(screen.queryByText(/will be delivered shortly/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Join" })).not.toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Access" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://example.test/first.pdf", "https://example.test/second.pdf",
    ]);
    expect(submissions).toBe(1);
  });

  it("omits untouched fields including inactive/public flags and absent optional values", async () => {
    const { offer, writes } = fixture({ is_active: false, is_public: false, offer_price: null, guarantee_days: null });
    mount(offer);
    await save();
    await waitFor(() => expect(writes).toEqual([{}]));
    expect(await offersApi.get("workspace-fixture", offer.id)).toMatchObject({
      is_active: false, is_public: false, offer_price: null, guarantee_days: null,
    });
  });

  it.each([
    ["Pricing", "Your Price ($)", "offer_price"],
    ["Pricing", "Regular Price ($)", "regular_price"],
    ["Pricing", "Savings Amount ($)", "savings_amount"],
    ["Guarantee", "Guarantee Period (Days)", "guarantee_days"],
  ])("distinguishes clearing %s/%s from setting it to zero", async (step, label, field) => {
    const { offer, writes } = fixture();
    mount(offer);
    fireEvent.click(screen.getByRole("button", { name: step }));
    fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    await save();
    await waitFor(() => expect(writes).toEqual([{ [field]: null }]));
    expect(await offersApi.get("workspace-fixture", offer.id)).toMatchObject({ [field]: null });
  });

  it.each([false, true])("preserves creation defaults (explicit free price: %s)", async (explicitFree) => {
    const { writes } = fixture();
    mount();
    fireEvent.change(screen.getByLabelText("Offer Name *"), { target: { value: "Free fixture" } });
    fireEvent.click(screen.getByRole("button", { name: "Pricing" }));
    if (explicitFree) {
      fireEvent.change(screen.getByLabelText("Your Price ($)"), { target: { value: "5" } });
      fireEvent.change(screen.getByLabelText("Your Price ($)"), { target: { value: "0" } });
    }
    await save(false);
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ discount_type: "percentage", discount_value: 0, is_active: true, is_public: false, require_email: true, require_phone: false, require_name: false });
    if (explicitFree) expect(writes[0]).toHaveProperty("offer_price", 0);
    else expect(writes[0]).not.toHaveProperty("offer_price");
    expect(writes[0]).not.toHaveProperty("regular_price");
    expect(writes[0]).not.toHaveProperty("guarantee_type");
  });
});
