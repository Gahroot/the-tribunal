import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { safeGetItem, safeRemoveItem, safeSetItem } from "@/lib/utils/storage";

const KEY = "tribunal:test";

beforeEach(() => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("safeGetItem", () => {
  it("returns the stored value when present", () => {
    window.localStorage.setItem(KEY, "value");

    expect(safeGetItem(KEY)).toBe("value");
  });

  it("returns null when the key is missing", () => {
    expect(safeGetItem("missing")).toBeNull();
  });

  it("returns null and warns when localStorage.getItem throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    expect(safeGetItem(KEY)).toBeNull();
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining(KEY),
      expect.any(Error),
    );
  });
});

describe("safeSetItem", () => {
  it("writes the value to localStorage", () => {
    safeSetItem(KEY, "value");

    expect(window.localStorage.getItem(KEY)).toBe("value");
  });

  it("swallows quota errors and warns instead of throwing", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });

    expect(() => safeSetItem(KEY, "value")).not.toThrow();
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining(KEY),
      expect.any(Error),
    );
  });
});

describe("safeRemoveItem", () => {
  it("removes the key from localStorage", () => {
    window.localStorage.setItem(KEY, "value");

    safeRemoveItem(KEY);

    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("swallows errors and warns", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    expect(() => safeRemoveItem(KEY)).not.toThrow();
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining(KEY),
      expect.any(Error),
    );
  });
});
