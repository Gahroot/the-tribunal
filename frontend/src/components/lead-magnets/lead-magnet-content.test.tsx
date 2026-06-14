import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LeadMagnetContent } from "@/components/lead-magnets/lead-magnet-content";
import type { LeadMagnet } from "@/types";

describe("LeadMagnetContent", () => {
  it("renders backend static lead-magnet downloads as same-origin proxy links", () => {
    const magnet = {
      name: "Dead Lead Reactivation Scripts",
      magnet_type: "pdf",
      delivery_method: "download",
      content_url: "/static/lead-magnets/dead-lead-reactivation-scripts.pdf",
      content_data: undefined,
    } satisfies Pick<
      LeadMagnet,
      "magnet_type" | "delivery_method" | "content_url" | "content_data" | "name"
    >;

    render(<LeadMagnetContent magnet={magnet} />);

    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/static/lead-magnets/dead-lead-reactivation-scripts.pdf",
    );
  });
});
