import { describe, expect, it } from "vitest";

import { navigateToBillingProvider } from "@/components/shared/billing/billing-navigation";

describe("navigateToBillingProvider", () => {
  it.each(["", "/billing", "javascript:alert(1)", "http://checkout.stripe.test/cs"])(
    "refuses to follow %j",
    (url) => {
      expect(() => navigateToBillingProvider(url)).toThrow(/billing provider/);
    },
  );
});
