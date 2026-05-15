import { describe, expect, it } from "vitest";

import { formatPhoneNumber } from "./phone";

describe("formatPhoneNumber", () => {
  it("formats a 10-digit number as (XXX) XXX-XXXX", () => {
    expect(formatPhoneNumber("5551234567")).toBe("(555) 123-4567");
  });

  it("strips non-digits before formatting", () => {
    expect(formatPhoneNumber("555-123-4567")).toBe("(555) 123-4567");
    expect(formatPhoneNumber("(555) 123 4567")).toBe("(555) 123-4567");
  });

  it("formats an 11-digit US number with +1 prefix", () => {
    expect(formatPhoneNumber("15551234567")).toBe("+1 (555) 123-4567");
    expect(formatPhoneNumber("+1 555 123 4567")).toBe("+1 (555) 123-4567");
  });

  it("returns the input unchanged for unrecognised shapes", () => {
    expect(formatPhoneNumber("+44 20 7123 4567")).toBe("+44 20 7123 4567");
    expect(formatPhoneNumber("123")).toBe("123");
  });

  it("does not treat an 11-digit number that doesn't start with 1 as US", () => {
    // 11 digits but country code != 1 → returned as-is
    expect(formatPhoneNumber("25551234567")).toBe("25551234567");
  });

  it("returns an empty string for nullish or empty input", () => {
    expect(formatPhoneNumber(undefined)).toBe("");
    expect(formatPhoneNumber(null)).toBe("");
    expect(formatPhoneNumber("")).toBe("");
  });
});
