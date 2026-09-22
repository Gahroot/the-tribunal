import { defineConfig } from "vitest/config";

// Standalone test config for the embeddable widget package. The widget is
// framework-agnostic vanilla TS exercised in jsdom — no MSW/Next setup needed,
// which keeps the package independently testable outside the host app.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
