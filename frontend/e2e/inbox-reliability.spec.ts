import { expect, test, type Page } from "@playwright/test";

import type { InboxConversation } from "@/lib/api/conversations";

// Synthetic, intercepted boundaries only. No credentials, providers or live CRM.
// Real SQL/auth coverage lives in backend/tests/integration/test_inbox_postgres.py.
const workspace = "11111111-1111-4111-8111-111111111111";
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const stamp = "2026-09-24T12:00:00Z";

const runtimeErrors = new WeakMap<Page, string[]>();
test.afterEach(async ({ page }) => {
  expect(runtimeErrors.get(page) ?? []).toEqual([]);
});

async function installFixture(page: Page) {
  const errors: string[] = [];
  runtimeErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    // Intentional HTTP failure fixtures are asserted in the recovery tests.
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:"))
      errors.push(message.text());
  });
  const rows: InboxConversation[] = Array.from({ length: 122 }, (_, index) => ({
    id: id(index + 1),
    workspace_id: workspace,
    contact_id: index === 120 ? 121 : null,
    contact:
      index === 120
        ? {
            id: 121,
            first_name: "Fixture",
            last_name: "Lead",
            avatar_url: null,
            status: "new",
            lead_score: 50,
          }
        : null,
    contact_phone: `+1555${String(index + 1).padStart(7, "0")}`,
    workspace_phone: "+15550000000",
    channel: "sms",
    status: "active",
    ai_enabled: false,
    ai_paused: false,
    assigned_agent_id: null,
    unread_count: 1,
    last_message_at: stamp,
    created_at: stamp,
    last_message_direction: "inbound",
    needs_human_reply: true,
    last_message_preview:
      index === 120 ? "Unique appointment question" : `Fixture lead ${index + 1}`,
  }));
  const writes: string[] = [];
  let failSend = false;
  let failList = false;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/auth/me"))
      return json({ id: 1, email: "fixture@example.test", first_name: "Fixture", is_active: true });
    if (path.endsWith("/workspaces"))
      return json([
        {
          workspace: {
            id: workspace,
            name: "Inbox fixture",
            slug: "fixture",
            is_active: true,
            settings: {},
            created_at: stamp,
          },
          role: "owner",
          is_default: true,
        },
      ]);
    if (path.endsWith("/dashboard/today-queue"))
      return json({
        items: [
          {
            id: "replies_waiting",
            kind: "replies_waiting",
            priority: 100,
            title: "122 conversations need a reply",
            body: "Fixture follow-up queue",
            count: 122,
            cta_label: "Reply now",
            href: "/conversations?view=waiting",
            payload: {},
          },
        ],
        generated_at: stamp,
      });
    if (path.endsWith("/conversations/inbox") || path.endsWith("/conversations/inbox/search")) {
      if (failList) return json({ detail: "Fixture list failure" }, 503);
      const params = request.method() === "POST" ? new URLSearchParams(request.postDataJSON()) : url.searchParams;
      const q = (params.get("q") ?? "").toLowerCase();
      const view = params.get("view") ?? "all";
      const all = rows.filter(
        (row) =>
          (row.last_message_preview ?? "").toLowerCase().includes(q) || row.contact_phone.includes(q),
      );
      const waiting = all.filter((row) => row.needs_human_reply);
      const result = view === "waiting" ? waiting : view === "hot" ? [] : all;
      const current = Number(params.get("page") ?? "1");
      const pageSize = Number(params.get("page_size") ?? "50");
      return json({
        items: result.slice((current - 1) * pageSize, current * pageSize),
        counts: { all: all.length, waiting: waiting.length, hot: 0 },
        total: result.length,
        page: current,
        page_size: pageSize,
        pages: Math.ceil(result.length / pageSize),
      });
    }
    const match = path.match(
      /\/conversations\/([^/]+)\/(inbox-detail|messages|read|followup\/generate|ai)$/,
    );
    if (match) {
      const row = rows.find((r) => r.id === match[1]);
      if (!row) return json({ detail: "Conversation not found" }, 404);
      if (request.method() === "GET") {
        if (match[2] === "inbox-detail") return json(row);
        if (match[2] === "messages")
          return json([
            {
              id: id(999),
              conversation_id: row.id,
              channel: "sms",
              direction: "inbound",
              body: row.last_message_preview,
              status: "received",
              is_ai: false,
              created_at: stamp,
              attachments: [],
            },
          ]);
      }
      writes.push(path);
      if (match[2] === "read") {
        row.unread_count = 0;
        return json({ marked_read: true });
      }
      if (match[2] === "messages") {
        if (failSend) return json({ detail: "Fixture provider unavailable" }, 503);
        row.needs_human_reply = false;
        row.last_message_direction = "outbound";
        return json({
          id: id(998),
          conversation_id: row.id,
          body: request.postDataJSON().body,
          status: "queued",
          channel: "sms",
          direction: "outbound",
          is_ai: false,
          created_at: stamp,
        });
      }
      if (match[2] === "followup/generate")
        return json({ message: "Fixture draft: would tomorrow work?" });
    }
    // Shell counters and unrelated side panels get honest empty fixture data.
    if (path.endsWith("/contacts/121"))
      return json({
        id: 121,
        user_id: 1,
        workspace_id: workspace,
        first_name: "Fixture",
        last_name: "Lead",
        full_name: "Fixture Lead",
        phone_number: "+15550000121",
        email: "fixture@example.test",
        status: "new",
        lead_score: 50,
        tags: [],
        custom_fields: {},
        assigned_agent_id: null,
        created_at: stamp,
        updated_at: stamp,
      });
    if (path.endsWith("/integrations") || path.endsWith("/pipelines")) return json([]);
    if (path.endsWith("/agents"))
      return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    if (path.includes("/count")) return json({ count: 0, total: 0 });
    if (path.includes("/subscription")) return json({ status: "active", plan: "pro" });
    return json({ items: [], total: 0, page: 1, page_size: 50, pages: 0 });
  });
  return {
    rows,
    writes,
    setFailSend: (value: boolean) => {
      failSend = value;
    },
    setFailList: (value: boolean) => {
      failList = value;
    },
  };
}

test("Today to waiting inbox, search beyond 100, read, retry send and next", async ({ page }) => {
  const fixture = await installFixture(page);
  await page.goto("/today");
  await page.getByRole("link", { name: "Reply now" }).click();
  await expect(page).toHaveURL(/view=waiting/);
  await expect(page.getByRole("button", { name: /Waiting on me\s*122/ })).toBeVisible();
  const searchRequest = page.waitForRequest((request) => request.url().endsWith("/inbox/search"));
  await page.getByRole("textbox", { name: "Search conversations" }).fill("Unique appointment");
  const searched = await searchRequest;
  expect(searched.method()).toBe("POST");
  expect(searched.postDataJSON().q).toBe("Unique appointment");
  expect(page.url()).not.toContain("Unique");
  await expect(page.getByRole("status").filter({ hasText: "1 conversation" })).toBeVisible();
  await page.getByRole("button", { name: /Fixture Lead/ }).click();
  await expect(page).toHaveURL(new RegExp(id(121)));
  const composer = page.getByRole("textbox", { name: "Message", exact: true });
  await expect(composer).toBeEnabled();
  await expect(page.getByRole("button", { name: /Waiting on me\s*1$/ })).toBeVisible();
  expect(fixture.writes.filter((path) => path.endsWith("/messages"))).toHaveLength(0);
  await page.getByRole("button", { name: "Generate AI draft reply" }).click();
  await expect(composer).toHaveValue("Fixture draft: would tomorrow work?");
  expect(fixture.writes.filter((path) => path.endsWith("/messages"))).toHaveLength(0);
  fixture.setFailSend(true);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "draft is kept" })).toBeVisible();
  await expect(composer).toHaveValue("Fixture draft: would tomorrow work?");
  fixture.setFailSend(false);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(composer).toHaveValue("");
  await expect(
    page.getByText("This conversation is outside the current results. Your selection is kept."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page.getByRole("button", { name: "Next waiting reply" })).toBeEnabled();
  await page.getByRole("button", { name: "Next waiting reply" }).click();
  await expect(page).not.toHaveURL(new RegExp(id(121)));
  await expect(page.getByRole("button", { name: /Waiting on me\s*121$/ })).toBeVisible();
  await expect(page.locator('[aria-label="Conversation list"] ul button').first()).toBeVisible();
  await expect(page.getByText("Message queued", { exact: true })).toBeHidden({ timeout: 10000 });
  await page.screenshot({ path: "test-results/inbox-desktop.png", fullPage: true, animations: "disabled" });
});

test("direct selection outside page, pagination, filters, history and saved views", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto(`/conversations?view=all&conversation=${id(121)}`);
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEnabled();
  await expect(
    page.getByText("This conversation is outside the current results. Your selection is kept."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next inbox page" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Page 2 of 3" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(id(121)));
  await page.getByRole("button", { name: /555.*0051/ }).click();
  await expect(page).toHaveURL(new RegExp(id(51)));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(id(121)));
  await page.getByRole("button", { name: /Hot leads/ }).click();
  await expect(page.getByText("No matching conversations")).toBeVisible();
  await page.getByRole("button", { name: "Save view", exact: true }).click();
  await page.getByLabel("Saved view name").fill("My hot follow-up");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "My hot follow-up", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^All\s*122$/ }).click();
  await page.getByRole("button", { name: "My hot follow-up", exact: true }).click();
  await expect(page).toHaveURL(/view=hot/);
});

test("narrow keyboard path and contact-context sheet preserve a draft", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installFixture(page);
  await page.goto(`/conversations?view=waiting&conversation=${id(121)}`);
  const composer = page.getByRole("textbox", { name: "Message", exact: true });
  await expect(composer).toBeEnabled();
  await composer.fill("Keep this draft");
  const details = page.getByRole("button", { name: "Open contact details" });
  await details.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toBeFocused();
  await page.getByRole("button", { name: "Back to inbox" }).click();
  await expect(page.getByRole("textbox", { name: "Search conversations" })).toBeVisible();
  await page.goBack();
  await expect(composer).toHaveValue("Keep this draft");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: "test-results/inbox-mobile.png", fullPage: true });
});

test("list error is recoverable and missing selections never show another thread", async ({
  page,
}) => {
  const fixture = await installFixture(page);
  fixture.setFailList(true);
  await page.goto(`/conversations?view=waiting&conversation=${id(9999)}`);
  await expect(page.getByText("We couldn't load conversations.")).toBeVisible();
  await expect(
    page.getByText(
      "This conversation couldn't be opened. It may have been removed or be unavailable in this workspace.",
    ),
  ).toBeVisible();
  expect(await page.getByRole("textbox", { name: "Message", exact: true }).count()).toBe(0);
  fixture.setFailList(false);
  await page
    .locator("[data-slot='page-state']")
    .filter({ hasText: "We couldn't load conversations." })
    .getByRole("button", { name: "Try again" })
    .click();
  await expect(page.locator('[aria-label="Conversation list"] ul button').first()).toBeVisible();
  await page.screenshot({ path: "test-results/inbox-missing-selection.png", fullPage: true });
});


test("320px reflow keeps controls visible with reduced motion and forced colors", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce", forcedColors: "active" });
  await installFixture(page);
  await page.goto(`/conversations?view=waiting&conversation=${id(121)}`);
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEnabled();
  for (const name of ["Toggle theme", "Back to inbox", "Next waiting reply", "Open contact details", "Generate AI draft reply", "Send message"]) {
    const box = await page.getByRole("button", { name, exact: true }).boundingBox();
    expect(box, name).not.toBeNull();
    expect(box!.x, name).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width, name).toBeLessThanOrEqual(321);
  }
  await page.screenshot({ path: "test-results/inbox-forced-colors-320.png", fullPage: true, animations: "disabled" });
});
