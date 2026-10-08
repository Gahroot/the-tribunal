import { expect, test } from "@playwright/test";

// All public API responses and destinations are local fixtures. No lead writes,
// bookings, payment requests or provider traffic are permitted by this test.
for (const kind of ["quiz", "calculator"] as const) {
  test(`${kind}: configured result link and host offer action`, async ({ page }) => {
    const unexpected: string[] = [];
    const magnet = (cta_action: string, cta_url?: string) => ({
      id: "fixture-magnet",
      name: "Fixture bonus",
      magnet_type: kind,
      delivery_method: "email",
      content_url: "",
      content_data:
        kind === "quiz"
          ? {
              title: "Quiz",
              questions: [
                {
                  id: "q",
                  text: "Choose a path",
                  type: "single_choice",
                  options: [{ id: "a", text: "North", score: 7 }],
                },
              ],
              results: [
                {
                  id: "r",
                  min_score: 7,
                  max_score: 7,
                  title: "North result",
                  description: "Fixture score preserved",
                  cta_text: "Continue",
                  cta_action,
                  cta_url,
                },
              ],
            }
          : {
              title: "Calculator",
              inputs: [{ id: "amount", label: "Amount", type: "number", required: true }],
              calculations: [],
              outputs: [
                {
                  id: "total",
                  label: "Total",
                  formula: "amount * 2",
                  format: "number",
                  highlight: true,
                },
              ],
              cta: { text: "Continue", cta_action, cta_url },
            },
    });
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() === "GET" && path.startsWith("/api/v1/p/offers/")) {
        const slug = path.split("/").pop();
        const destination = slug === "cta-destination";
        await route.fulfill({
          json: {
            name: "Fixture offer",
            headline: destination ? "Fixture destination reached" : "Fixture public host",
            require_email: true,
            require_name: false,
            require_phone: false,
            lead_magnets: destination
              ? []
              : [
                  magnet(
                    slug === "cta-host" ? "offer" : "booking",
                    slug === "cta-invalid"
                      ? "javascript:untrusted"
                      : slug === "cta-host"
                        ? undefined
                        : "/p/offers/cta-destination",
                  ),
                ],
          },
        });
      } else if (path === "/api/v1/auth/me") {
        await route.fulfill({ status: 200, json: null });
      } else {
        unexpected.push(`${request.method()} ${path}`);
        await route.abort();
      }
    });
    const complete = async () => {
      if (kind === "quiz") {
        await page.getByRole("radio", { name: "North" }).click();
        await page.getByRole("button", { name: "See My Result" }).click();
        await expect(page.getByText("North result")).toBeVisible();
      } else {
        await page.getByLabel("Amount").fill("6");
        await expect(page.getByText("12", { exact: true })).toBeVisible();
      }
    };
    await page.goto("/p/offers/cta-link");
    await complete();
    await page.getByRole("link", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Fixture destination reached" })).toBeVisible();
    await page.goto("/p/offers/cta-host");
    await complete();
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("form", { name: "Offer signup" })).toBeFocused();
    await expect(page.getByRole("button", { name: "Get Access Now" })).toBeDisabled();
    await page.goto("/p/offers/cta-invalid");
    await complete();
    await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
    await expect(page.getByText(/next step is currently unavailable/)).toBeVisible();
    expect(unexpected).toEqual([]);
  });
}
