import { describe, expect, it } from "vitest";

import { getContactInitials, getInitialsFromName } from "./initials";

describe("getContactInitials", () => {
  it("uses the first letter of first and last name", () => {
    expect(
      getContactInitials({ first_name: "Jane", last_name: "Doe" }),
    ).toBe("JD");
  });

  it("uppercases lowercase names", () => {
    expect(
      getContactInitials({ first_name: "jane", last_name: "doe" }),
    ).toBe("JD");
  });

  it("falls back to only the present part", () => {
    expect(getContactInitials({ first_name: "Jane", last_name: null })).toBe(
      "J",
    );
    expect(getContactInitials({ first_name: null, last_name: "Doe" })).toBe(
      "D",
    );
  });

  it("returns '?' when both names are missing", () => {
    expect(getContactInitials({})).toBe("?");
    expect(
      getContactInitials({ first_name: null, last_name: undefined }),
    ).toBe("?");
    expect(getContactInitials({ first_name: "", last_name: "" })).toBe("?");
  });
});

describe("getInitialsFromName", () => {
  it("uses first letter of first two words for multi-word names", () => {
    expect(getInitialsFromName("Jane Doe")).toBe("JD");
    expect(getInitialsFromName("Mary Anne Smith")).toBe("MA");
  });

  it("uses the first two characters for a single word", () => {
    expect(getInitialsFromName("Madonna")).toBe("MA");
  });

  it("trims and collapses whitespace", () => {
    expect(getInitialsFromName("  Jane   Doe  ")).toBe("JD");
  });

  it("returns the default '??' fallback when name is missing", () => {
    expect(getInitialsFromName(undefined)).toBe("??");
    expect(getInitialsFromName(null)).toBe("??");
    expect(getInitialsFromName("")).toBe("??");
    expect(getInitialsFromName("   ")).toBe("??");
  });

  it("uses the fallback (e.g. email) when name is blank", () => {
    expect(getInitialsFromName(null, "alice@example.com")).toBe("AL");
    expect(getInitialsFromName("", "bob@example.com")).toBe("BO");
  });

  it("ignores the fallback when a name is provided", () => {
    expect(getInitialsFromName("Jane Doe", "x@y.com")).toBe("JD");
  });

  it("returns '??' when both name and fallback are empty", () => {
    expect(getInitialsFromName(null, "")).toBe("??");
  });
});
