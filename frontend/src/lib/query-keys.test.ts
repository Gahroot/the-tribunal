import { describe, expect, it } from "vitest";

import {
  createResourceQueryKeys,
  getResourceInvalidationKeys,
  queryKeys,
} from "./query-keys";

describe("createResourceQueryKeys", () => {
  const keys = createResourceQueryKeys("widgets");

  it("builds the root key for the whole resource across workspaces", () => {
    expect(keys.root()).toEqual(["widgets"]);
  });

  it("builds the workspace-scoped `all` key", () => {
    expect(keys.all("ws_1")).toEqual(["widgets", "ws_1"]);
  });

  it("returns the bare workspace key for an unfiltered list", () => {
    expect(keys.list("ws_1")).toEqual(["widgets", "ws_1"]);
    expect(keys.list("ws_1", undefined)).toEqual(["widgets", "ws_1"]);
    expect(keys.list("ws_1", null)).toEqual(["widgets", "ws_1"]);
  });

  it("appends normalized params for a filtered list", () => {
    expect(keys.list("ws_1", { status: "open", page: 2 })).toEqual([
      "widgets",
      "ws_1",
      { page: 2, status: "open" },
    ]);
  });

  it("treats a params object that is empty after normalization as unfiltered", () => {
    expect(keys.list("ws_1", {})).toEqual(["widgets", "ws_1"]);
    expect(keys.list("ws_1", { ignored: undefined })).toEqual(["widgets", "ws_1"]);
  });

  it("builds detail keys, preserving string and numeric ids", () => {
    expect(keys.detail("ws_1", "abc")).toEqual(["widgets", "ws_1", "abc"]);
    expect(keys.detail("ws_1", 42)).toEqual(["widgets", "ws_1", 42]);
    expect(keys.detail("ws_1", null)).toEqual(["widgets", "ws_1", null]);
    expect(keys.detail("ws_1", undefined)).toEqual(["widgets", "ws_1", undefined]);
  });
});

describe("query-key param normalization", () => {
  const keys = createResourceQueryKeys("widgets");

  it("is order-independent: differently ordered params produce equal keys", () => {
    const a = keys.list("ws_1", { b: 2, a: 1, c: 3 });
    const b = keys.list("ws_1", { c: 3, a: 1, b: 2 });
    expect(a).toEqual(b);
  });

  it("drops only undefined values, keeping null and falsy values", () => {
    expect(keys.list("ws_1", { a: undefined, b: null, c: 0, d: false, e: "" })).toEqual([
      "widgets",
      "ws_1",
      { b: null, c: 0, d: false, e: "" },
    ]);
  });

  it("recursively normalizes nested object params", () => {
    const nested = keys.list("ws_1", {
      outer: { z: 1, a: 2, skip: undefined },
    });
    expect(nested).toEqual([
      "widgets",
      "ws_1",
      { outer: { a: 2, z: 1 } },
    ]);
  });

  it("preserves array order while normalizing array elements", () => {
    const key = keys.list("ws_1", { ids: [{ b: 1, a: 2 }, { d: 3, c: 4 }] });
    expect(key).toEqual([
      "widgets",
      "ws_1",
      { ids: [{ a: 2, b: 1 }, { c: 4, d: 3 }] },
    ]);
  });

  it("produces structurally equal keys for equivalent param objects (cache-hit safe)", () => {
    // React Query compares keys by deep structural equality, so two calls with
    // semantically identical params must yield deeply equal arrays.
    const first = keys.list("ws_1", { search: "acme", page: 1 });
    const second = keys.list("ws_1", { page: 1, search: "acme" });
    expect(first).toStrictEqual(second);
  });
});

describe("getResourceInvalidationKeys", () => {
  it("returns the resource's own `all` key when there are no related resources", () => {
    expect(getResourceInvalidationKeys("tags", "ws_1")).toEqual([["tags", "ws_1"]]);
  });

  it("includes related resource `all` keys after the primary resource", () => {
    expect(getResourceInvalidationKeys("tags", "ws_1", ["contacts"])).toEqual([
      ["tags", "ws_1"],
      ["contacts", "ws_1"],
    ]);
  });

  it("preserves the order of related resources", () => {
    expect(
      getResourceInvalidationKeys("segments", "ws_9", ["contacts", "tags"]),
    ).toEqual([
      ["segments", "ws_9"],
      ["contacts", "ws_9"],
      ["tags", "ws_9"],
    ]);
  });

  it("scopes every related key to the same workspace", () => {
    const keys = getResourceInvalidationKeys("tags", "ws_42", ["contacts", "segments"]);
    for (const key of keys) {
      expect(key[1]).toBe("ws_42");
    }
  });
});

describe("queryKeys factory composition", () => {
  it("spreads the resource builders onto each namespace", () => {
    expect(queryKeys.agents.root()).toEqual(["agents"]);
    expect(queryKeys.agents.all("ws_1")).toEqual(["agents", "ws_1"]);
    expect(queryKeys.agents.detail("ws_1", "a1")).toEqual(["agents", "ws_1", "a1"]);
  });

  it("derives filtered-list helpers from the shared list builder", () => {
    expect(queryKeys.agents.activeOnly("ws_1")).toEqual([
      "agents",
      "ws_1",
      { active_only: true },
    ]);
    expect(queryKeys.phoneNumbers.smsEnabled("ws_1")).toEqual([
      "phone-numbers",
      "ws_1",
      { sms_enabled: true },
    ]);
    expect(queryKeys.phoneNumbers.activeTextCapable("ws_1")).toEqual([
      "phone-numbers",
      "ws_1",
      { active_only: true, text_capable: true },
    ]);
  });

  it("nests detail-scoped sub-resources under the detail key", () => {
    expect(queryKeys.agents.versions("ws_1", "a1")).toEqual([
      "agents",
      "ws_1",
      "a1",
      "versions",
    ]);
    expect(queryKeys.contacts.timeline("ws_1", 7)).toEqual([
      "contacts",
      "ws_1",
      7,
      "timeline",
    ]);
    expect(queryKeys.contacts.timeline("ws_1", 7, 25)).toEqual([
      "contacts",
      "ws_1",
      7,
      "timeline",
      { limit: 25 },
    ]);
  });

  it("nests stat keys under the workspace `all` key so a broad invalidate clears them", () => {
    const all = queryKeys.appointments.all("ws_1");
    const stats = queryKeys.appointments.stats("ws_1");
    expect(stats).toEqual([...all, "stats"]);
    expect(stats.slice(0, all.length)).toEqual([...all]);
  });

  it("derives contact filtered lists from `all` so cache invalidation cascades", () => {
    const all = queryKeys.appointments.all("ws_1");
    const byContact = queryKeys.appointments.byContact("ws_1", 5);
    expect(byContact).toEqual(["appointments", "ws_1", { contact_id: 5 }]);
    expect(byContact.slice(0, all.length)).toEqual([...all]);
  });

  it("normalizes infinite-contacts filters and prefixes with the contacts root", () => {
    expect(
      queryKeys.contacts.infinite("ws_1", { status: "lead", search: undefined }),
    ).toEqual(["contacts", "ws_1", "infinite", { status: "lead" }]);
    expect(queryKeys.contacts.infinite(null, {})).toEqual([
      "contacts",
      null,
      "infinite",
      undefined,
    ]);
  });

  it("keeps a detail key and an unfiltered list key distinguishable", () => {
    // detail appends the id; an unfiltered list stays at the workspace `all` key.
    expect(queryKeys.agents.detail("ws_1", "a1")).toEqual(["agents", "ws_1", "a1"]);
    expect(queryKeys.agents.list("ws_1")).toEqual(["agents", "ws_1"]);
    expect(queryKeys.agents.detail("ws_1", "a1")).not.toEqual(queryKeys.agents.list("ws_1"));
  });

  it("serializes a segment preview definition into a stable string segment", () => {
    const def = { all: [{ field: "status", op: "eq", value: "lead" }] };
    const key = queryKeys.segments.preview("ws_1", def);
    expect(key).toEqual(["segments", "ws_1", "preview", JSON.stringify(def)]);
    // A nullish definition still produces a deterministic key.
    expect(queryKeys.segments.preview("ws_1", null)).toEqual([
      "segments",
      "ws_1",
      "preview",
      "null",
    ]);
  });

  it("normalizes scorecard range params order-independently", () => {
    expect(queryKeys.scorecard.range("ws_1", { to: "b", from: "a" })).toEqual(
      queryKeys.scorecard.range("ws_1", { from: "a", to: "b" }),
    );
    expect(queryKeys.scorecard.range("ws_1")).toEqual(["scorecard", "ws_1", undefined]);
  });

  it("nests at-risk opportunities under the workspace `all` key", () => {
    const all = queryKeys.opportunities.all("ws_1");
    const atRisk = queryKeys.opportunities.atRisk("ws_1");
    expect(atRisk).toEqual([...all, "at-risk", null]);
    expect(atRisk.slice(0, all.length)).toEqual([...all]);
  });

  it("builds workspace-independent auth keys", () => {
    expect(queryKeys.auth.currentUser()).toEqual(["auth", "currentUser"]);
    expect(queryKeys.auth.session()).toEqual(["auth", "session"]);
  });

  it("derives appointment byContact from the workspace `all` key", () => {
    const all = queryKeys.appointments.all("ws_1");
    const byContact = queryKeys.appointments.byContact("ws_1", undefined);
    // An undefined contact id is normalized away, collapsing to the `all` key.
    expect(byContact.slice(0, all.length)).toEqual([...all]);
  });
});
