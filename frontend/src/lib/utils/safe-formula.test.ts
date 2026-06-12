import { describe, expect, it } from "vitest";

import { evaluateFormula } from "./safe-formula";

describe("evaluateFormula", () => {
  it("evaluates arithmetic with operator precedence", () => {
    expect(evaluateFormula("2 + 3 * 4", {})).toBe(14);
    expect(evaluateFormula("(2 + 3) * 4", {})).toBe(20);
    expect(evaluateFormula("10 / 4", {})).toBe(2.5);
  });

  it("resolves variable references from scope", () => {
    expect(evaluateFormula("input1 * (input2 / 100)", { input1: 1000, input2: 20 })).toBe(200);
    expect(evaluateFormula("calc1 * 12", { calc1: 200 })).toBe(2400);
  });

  it("handles unary minus", () => {
    expect(evaluateFormula("-input1 + 5", { input1: 3 })).toBe(2);
  });

  it("returns null for unknown variables", () => {
    expect(evaluateFormula("missing * 2", {})).toBeNull();
  });

  it("returns null for division by zero", () => {
    expect(evaluateFormula("input1 / 0", { input1: 10 })).toBeNull();
    expect(evaluateFormula("input1 / input2", { input1: 10, input2: 0 })).toBeNull();
  });

  it("refuses non-arithmetic or malformed input", () => {
    expect(evaluateFormula("alert('x')", {})).toBeNull();
    expect(evaluateFormula("2 +", {})).toBeNull();
    expect(evaluateFormula("2 ** 3", {})).toBeNull();
    expect(evaluateFormula("input1 input2", { input1: 1, input2: 2 })).toBeNull();
  });
});
