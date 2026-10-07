import { describe, expect, it } from "vitest";

import { buildLoginHref, getSafeReturnTo, invitePath } from "@/lib/auth/return-to";

describe("getSafeReturnTo", () => {
  it.each([
    ["/invite/abc123", "/invite/abc123"],
    ["/contacts?tab=all#top", "/contacts?tab=all#top"],
    ["/today", "/today"],
  ])("permits local path %s", (value, expected) => {
    expect(getSafeReturnTo(value)).toBe(expected);
  });

  it.each([
    ["absolute URL", "https://evil.example/invite/x"],
    ["protocol-relative URL", "//evil.example/invite/x"],
    ["backslash host", "/\\evil.example"],
    ["tab-smuggled protocol-relative", "/\t/evil.example"],
    ["newline", "/invite/x\n"],
    ["javascript scheme", "javascript:alert(1)"],
    ["relative path", "invite/x"],
    ["empty", ""],
    ["login loop", "/login?redirect=/invite/x"],
    ["register page", "/register"],
    ["api route", "/api/v1/auth/logout"],
    ["non-string", ["/invite/x"]],
    ["undefined", undefined],
    ["overlong", `/${"a".repeat(3000)}`],
  ])("rejects %s", (_label, value) => {
    expect(getSafeReturnTo(value)).toBeNull();
  });

  it("normalizes dot segments so they cannot escape to a blocked path", () => {
    expect(getSafeReturnTo("/invite/../login")).toBeNull();
    expect(getSafeReturnTo("/invite/../today")).toBe("/today");
  });
});

describe("buildLoginHref", () => {
  it("carries a permitted destination, encoded", () => {
    expect(buildLoginHref(invitePath("tok_1"))).toBe("/login?redirect=%2Finvite%2Ftok_1");
  });

  it("drops an unsafe destination", () => {
    expect(buildLoginHref("https://evil.example")).toBe("/login");
    expect(buildLoginHref(null)).toBe("/login");
  });
});
