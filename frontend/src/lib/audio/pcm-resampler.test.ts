import { describe, expect, it } from "vitest";

import { createPcmResampler } from "./pcm-resampler";

describe("createPcmResampler", () => {
  it("keeps samples unchanged when the browser supplies 16 kHz", () => {
    const input = new Float32Array([0, 0.5, -0.5]);
    expect(createPcmResampler(16000, 16000)(input)).toBe(input);
  });

  it("converts 48 kHz microphone chunks continuously to 16 kHz", () => {
    const resample = createPcmResampler(48000, 16000);
    const input = Float32Array.from({ length: 4800 }, (_, i) => i / 4800);
    const first = resample(input.slice(0, 2400));
    const second = resample(input.slice(2400));
    expect(first.length + second.length).toBeGreaterThanOrEqual(1599);
    expect(first.length + second.length).toBeLessThanOrEqual(1600);
    expect(first.at(-1)).toBeCloseTo(second[0], 2);
    expect(second.at(-1)).toBeCloseTo(input.at(-1)!, 2);
  });
});
