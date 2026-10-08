import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FollowupSection } from "@/components/actions/followup-section";
import { ContactActions } from "@/components/contacts/contact-sidebar/contact-actions";
import { useContactSidebarData } from "@/components/contacts/contact-sidebar/use-contact-sidebar-data";
import { useUpdateFollowupSettings } from "@/hooks/useFollowups";
import { contactsApi } from "@/lib/api/contacts";
import { useContactStore } from "@/lib/contact-store";
import { queryKeys } from "@/lib/query-keys";
import { server } from "@/test/msw/server";
import type { Contact } from "@/types";

vi.mock("@/hooks/useWorkspaceId", () => ({ useWorkspaceId: () => "ws_1" }));
vi.mock("@/lib/api/appointments", () => ({ appointmentsApi: { list: async () => ({ items: [] }) } }));
vi.mock("@/lib/api/phone-numbers", () => ({ phoneNumbersApi: { list: async () => ({ items: [] }) } }));

const ROUTE = "http://localhost:3000/api/v1/workspaces/:workspaceId/conversations";
const contact = (id: number) => ({ id, first_name: "Fixture" }) as Contact;
const page = (items: object[]) => ({ items, total: items.length, pages: items.length ? 1 : 0, page: 1, page_size: 100 });
const target = { id: "target", contact_id: 101, ai_enabled: true, channel: "sms" };

afterEach(() => vi.restoreAllMocks());

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
  vi.spyOn(contactsApi, "getTimeline").mockResolvedValue([]);
  return { queryClient, wrapper };
}

function scopedServer() {
  const requests: string[] = [];
  // The selected thread sits after 105 newer workspace threads. A workspace
  // page cannot contain it; only a server-side contact filter returns it.
  const newer = Array.from({ length: 105 }, (_, i) => ({ id: `new-${i}`, contact_id: i + 1000, ai_enabled: false }));
  server.use(http.get(ROUTE, ({ request }) => {
    const id = new URLSearchParams(new URL(request.url).search).get("contact_id");
    requests.push(id ?? "workspace");
    return HttpResponse.json(page(id === "101" ? [target, { ...target, id: "older", channel: "email", ai_enabled: false }] : id ? [] : newer.slice(0, 100)));
  }));
  return requests;
}

describe("contact sidebar scoped follow-up state (RF-013)", () => {
  it("finds a contact beyond the first 100 and preserves newest-channel selection", async () => {
    const requests = scopedServer();
    const { wrapper } = setup();
    const { result, rerender } = renderHook(({ id }) => useContactSidebarData({ workspaceId: "ws_1", contact: contact(id) }), { wrapper, initialProps: { id: 101 } });
    expect(result.current.aiLoading).toBe(true);
    await waitFor(() => expect(result.current.aiEnabled).toBe(true));
    expect(requests).toEqual(["101"]);
    rerender({ id: 202 });
    expect(result.current.aiLoading).toBe(true);
    await waitFor(() => expect(result.current.aiLoading).toBe(false));
    expect(result.current.aiEnabled).toBe(false);
    expect(result.current.aiError).toBe(false);
    expect(requests).toEqual(["101", "202"]);
  });

  it("reports errors as unknown, not disabled, and disables the toggle", async () => {
    server.use(http.get(ROUTE, () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })));
    const { wrapper } = setup();
    const { result } = renderHook(() => useContactSidebarData({ workspaceId: "ws_1", contact: contact(101) }), { wrapper });
    await waitFor(() => expect(result.current.aiError).toBe(true));
    const actions = { hasPhoneNumber: true, aiEnabled: false, isCalling: false, isTogglingAi: false, onCall: vi.fn(), onSchedule: vi.fn(), onEdit: vi.fn(), onToggleAi: vi.fn(), onDelete: vi.fn() };
    const view = render(<ContactActions {...actions} aiLoading />);
    expect(screen.getByRole("button", { name: "Loading AI" })).toBeDisabled();
    expect(screen.queryByText("AI Off")).not.toBeInTheDocument();
    view.rerender(<ContactActions {...actions} aiError />);
    expect(screen.getByRole("button", { name: "AI unavailable" })).toBeDisabled();
  });

  it("keeps optimistic updates scoped and refreshes the original contact after switching", async () => {
    scopedServer();
    const { wrapper, queryClient } = setup();
    let finish!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    let enabled = true;
    server.use(http.get(ROUTE, ({ request }) => {
      const id = new URL(request.url).searchParams.get("contact_id");
      return HttpResponse.json(page(id === "101" ? [{ ...target, ai_enabled: enabled }] : []));
    }));
    vi.spyOn(contactsApi, "toggleAI").mockImplementation(async () => {
      await pending;
      enabled = false;
      return { ai_enabled: false, conversation_id: "target" };
    });
    const otherKey = [...queryKeys.conversations.byContact("other_workspace", 101), "scoped"];
    queryClient.setQueryData(otherKey, page([target]));
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result, rerender } = renderHook(({ id }) => useContactSidebarData({ workspaceId: "ws_1", contact: contact(id) }), { wrapper, initialProps: { id: 101 } });
    await waitFor(() => expect(result.current.aiEnabled).toBe(true));
    act(() => { result.current.setAiEnabled(false); result.current.toggleAIMutation.mutate({ contactId: 101, enabled: false }); });
    await waitFor(() => expect(result.current.aiEnabled).toBe(false));
    const key = [...queryKeys.conversations.byContact("ws_1", 101), "scoped"];
    await waitFor(() => expect(queryClient.getQueryData(key)).toMatchObject({ items: [{ ai_enabled: false }] }));
    rerender({ id: 202 });
    await waitFor(() => expect(result.current.aiLoading).toBe(false));
    act(() => finish());
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.contacts.aiState("ws_1", 101) }));
    expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryData(otherKey)).toMatchObject({ items: [{ ai_enabled: true }] });
    rerender({ id: 101 });
    await waitFor(() => expect(queryClient.getQueryState(key)?.isInvalidated).toBe(false));
    expect(result.current.aiEnabled).toBe(false);
  });

  it("rolls back the scoped optimistic cache when a toggle fails", async () => {
    scopedServer();
    const { wrapper, queryClient } = setup();
    vi.spyOn(contactsApi, "toggleAI").mockRejectedValue(new Error("Rejected"));
    const { result } = renderHook(() => useContactSidebarData({ workspaceId: "ws_1", contact: contact(101) }), { wrapper });
    await waitFor(() => expect(result.current.aiEnabled).toBe(true));
    await act(async () => { await expect(result.current.toggleAIMutation.mutateAsync({ contactId: 101, enabled: false })).rejects.toThrow("Rejected"); });
    await waitFor(() => expect(queryClient.getQueryData([...queryKeys.conversations.byContact("ws_1", 101), "scoped"])).toMatchObject({ items: [{ ai_enabled: true }, { ai_enabled: false }] }));
  });

  it("can enable AI before a conversation exists and discovers the created conversation", async () => {
    const { wrapper, queryClient } = setup();
    let created = false;
    server.use(http.get(ROUTE, () => HttpResponse.json(page(created ? [target] : []))));
    vi.spyOn(contactsApi, "toggleAI").mockImplementation(async () => {
      created = true;
      return { ai_enabled: true, conversation_id: "target" };
    });
    const { result } = renderHook(() => useContactSidebarData({ workspaceId: "ws_1", contact: contact(101) }), { wrapper });
    await waitFor(() => expect(result.current.aiLoading).toBe(false));
    expect(result.current.aiEnabled).toBe(false);
    act(() => {
      result.current.setAiEnabled(true);
      result.current.toggleAIMutation.mutate({ contactId: 101, enabled: true });
    });
    expect(result.current.aiEnabled).toBe(true);
    await waitFor(() => expect(queryClient.getQueryData(queryKeys.conversations.scopedContact("ws_1", 101))).toMatchObject({ items: [{ id: "target", ai_enabled: true }] }));
    expect(result.current.aiEnabled).toBe(true);
  });

  it("clears local optimistic state on workspace changes and ignores old callbacks", async () => {
    const { wrapper } = setup();
    server.use(http.get(ROUTE, () => HttpResponse.json(page([]))));
    const { result, rerender } = renderHook(({ workspaceId }) => useContactSidebarData({ workspaceId, contact: contact(101) }), { wrapper, initialProps: { workspaceId: "ws_1" } });
    await waitFor(() => expect(result.current.aiLoading).toBe(false));
    const oldCallback = result.current.setAiEnabled;
    act(() => oldCallback(true));
    expect(result.current.aiEnabled).toBe(true);
    rerender({ workspaceId: "ws_2" });
    await waitFor(() => expect(result.current.aiLoading).toBe(false));
    expect(result.current.aiEnabled).toBe(false);
    act(() => oldCallback(true));
    expect(result.current.aiEnabled).toBe(false);
  });

  it("refreshes the exact follow-up settings cache after a settings toggle", async () => {
    const { wrapper, queryClient } = setup();
    server.use(http.patch(`${ROUTE}/:conversationId/followup/settings`, () => HttpResponse.json({ enabled: true })));
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useUpdateFollowupSettings("ws_1"), { wrapper });
    await act(async () => { await result.current.mutateAsync({ conversationId: "target", settings: { enabled: true } }); });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.conversations.followupSettings("ws_1", "target") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.conversations.all("ws_1") });
  });
});

describe("FollowupSection state", () => {
  it("does not report no conversation while loading, then shows the beyond-100 thread", async () => {
    scopedServer();
    server.use(http.get(`${ROUTE}/:conversationId/followup/status`, () => HttpResponse.json({ enabled: true, delay_hours: 24, max_count: 3, count_sent: 0 })));
    useContactStore.setState({ selectedContact: contact(101) });
    const { wrapper } = setup();
    render(<FollowupSection />, { wrapper });
    expect(screen.getByRole("status")).toHaveTextContent("Loading follow-up settings");
    expect(screen.queryByText(/No conversation yet/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("switch")).toBeChecked());
  });

  it("shows genuinely missing conversations only after successful lookup", async () => {
    scopedServer();
    useContactStore.setState({ selectedContact: contact(202) });
    const { wrapper } = setup();
    render(<FollowupSection />, { wrapper });
    await screen.findByText(/No conversation yet/);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it.each(["conversations", "settings"])("shows an error rather than disabled follow-up when %s fails", async (failure) => {
    scopedServer();
    server.use(http.get(failure === "conversations" ? ROUTE : `${ROUTE}/:conversationId/followup/status`, () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })));
    useContactStore.setState({ selectedContact: contact(101) });
    const { wrapper } = setup();
    render(<FollowupSection />, { wrapper });
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load follow-up settings");
    expect(screen.queryByText(/No conversation yet/)).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });
});
