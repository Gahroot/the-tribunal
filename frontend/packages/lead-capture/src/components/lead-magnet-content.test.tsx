import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { LeadMagnet, ResultCTADestination } from "@/types";

import { LeadMagnetContent } from "./lead-magnet-content";
import { ResultCTAEditor } from "./result-cta";

type Magnet = Pick<
  LeadMagnet,
  "magnet_type" | "delivery_method" | "content_url" | "content_data" | "name"
>;

const text = (value: string, marks?: unknown[]) => ({ type: "text", text: value, marks });
const paragraph = (...content: unknown[]) => ({ type: "paragraph", content });
const doc = (...content: unknown[]) => ({ type: "doc", content });
const richMagnet = (content: unknown): Magnet => ({
  name: "Local fixture magnet",
  magnet_type: "rich_text",
  delivery_method: "email",
  content_url: "",
  content_data: { title: "Field guide", description: "A short overview", content },
});

const interactiveMagnet = (
  kind: "quiz" | "calculator",
  destination: ResultCTADestination,
): Magnet => ({
  ...richMagnet(undefined),
  magnet_type: kind,
  content_data:
    kind === "quiz"
      ? {
          title: "Quiz",
          questions: [
            {
              id: "q",
              text: "Choose",
              type: "single_choice",
              options: [{ id: "a", text: "North", score: 7 }],
            },
          ],
          results: [
            { id: "wrong", min_score: 0, max_score: 0, title: "Wrong band", description: "" },
            {
              id: "r",
              min_score: 7,
              max_score: 7,
              title: "Right band",
              description: "",
              cta_text: "Next step",
              ...destination,
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
          cta: { text: "Next step", ...destination },
        },
});

async function complete(kind: "quiz" | "calculator") {
  if (kind === "quiz") {
    await userEvent.click(screen.getByRole("radio", { name: "North" }));
    await userEvent.click(screen.getByRole("button", { name: "See My Result" }));
    expect(screen.getByText("Right band")).toBeVisible();
    expect(screen.queryByText("Wrong band")).not.toBeInTheDocument();
  } else {
    await userEvent.type(screen.getByLabelText("Amount"), "6");
    expect(screen.getByText("12")).toBeVisible();
  }
}

describe.each(["quiz", "calculator"] as const)("%s result CTA", (kind) => {
  it.each(["booking", "offer"] as const)(
    "completes and activates an explicit %s parent action",
    async (cta_action) => {
      const callback = vi.fn();
      render(
        <LeadMagnetContent
          magnet={interactiveMagnet(kind, { cta_action })}
          onBooking={callback}
          onOffer={callback}
        />,
      );
      await complete(kind);
      await userEvent.click(screen.getByRole("button", { name: "Next step" }));
      expect(callback).toHaveBeenCalledOnce();
    },
  );

  it.each(["https://example.com/book", "/p/offers/fixture-offer"])(
    "preserves configured destination in preview and public: %s",
    async (cta_url) => {
      const callback = vi.fn();
      const magnet = interactiveMagnet(kind, { cta_url });
      const { rerender } = render(<LeadMagnetContent magnet={magnet} />);
      await complete(kind);
      expect(screen.getByRole("link", { name: "Next step" })).toHaveAttribute("href", cta_url);
      rerender(<LeadMagnetContent magnet={magnet} onOffer={callback} />);
      expect(screen.getByRole("link", { name: "Next step" })).toHaveAttribute("href", cta_url);
      expect(callback).not.toHaveBeenCalled();
    },
  );

  it.each([
    undefined,
    "javascript:untrusted",
    "http:example.com",
    "https:///example.com",
    "//example.com",
    "https://user:password@example.com",
    "/appointments",
    "https://example.com/\\\\bad",
    "https://example.com/\npath",
  ])("disables absent or unsafe destinations, even with a host callback: %j", async (cta_url) => {
    const callback = vi.fn();
    render(
      <LeadMagnetContent
        magnet={interactiveMagnet(kind, { cta_action: cta_url ? "offer" : "link", cta_url })}
        onOffer={callback}
      />,
    );
    await complete(kind);
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();
    expect(screen.getByText(/next step is currently unavailable/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Next step" })).not.toBeInTheDocument();
    expect(callback).not.toHaveBeenCalled();
  });

  it("does not fake a booking in preview without a destination or callback", async () => {
    render(<LeadMagnetContent magnet={interactiveMagnet(kind, { cta_action: "booking" })} />);
    await complete(kind);
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();
  });

  it("fails closed for unsupported stored actions", async () => {
    render(
      <LeadMagnetContent
        magnet={interactiveMagnet(kind, {
          cta_action: "payment" as ResultCTADestination["cta_action"],
          cta_url: "https://example.com",
        })}
      />,
    );
    await complete(kind);
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();
  });
});

describe("Result CTA authoring", () => {
  it("explains missing and invalid destinations and saves a working preview destination", async () => {
    function AuthoringFixture() {
      const [destination, setDestination] = useState<ResultCTADestination>({});
      return (
        <>
          <ResultCTAEditor
            destination={destination}
            onChange={(updates) => setDestination((previous) => ({ ...previous, ...updates }))}
          />
          <LeadMagnetContent magnet={interactiveMagnet("quiz", destination)} />
        </>
      );
    }
    render(<AuthoringFixture />);
    expect(screen.getByText(/Configure a destination to enable this CTA/)).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText("CTA action"), "booking");
    await userEvent.type(screen.getByLabelText("CTA destination URL"), "javascript:untrusted");
    expect(screen.getByText(/Unsafe destinations are disabled/)).toBeVisible();
    await complete("quiz");
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("CTA destination URL"));
    await userEvent.type(screen.getByLabelText("CTA destination URL"), "https://example.com/book");
    expect(screen.getByRole("link", { name: "Next step" })).toHaveAttribute(
      "href",
      "https://example.com/book",
    );
  });
});

describe("LeadMagnetContent", () => {
  it("shows the distinctive saved article, with editor formatting and safe links", () => {
    const { container } = render(
      <LeadMagnetContent
        magnet={richMagnet(
          doc(
            {
              type: "heading",
              attrs: { level: 2 },
              content: [text("Map the copper lantern route")],
            },
            paragraph(
              text("Saved body: follow the turquoise waypoint.", [{ type: "bold" }]),
              { type: "hardBreak" },
              text("Check the shoreline", [{ type: "italic" }]),
              text(" Reference", [
                {
                  type: "link",
                  attrs: { href: "https://example.com/guide", onclick: "untrusted" },
                },
              ]),
              text(" Old", [{ type: "strike" }]),
              text(" Underlined", [{ type: "underline" }]),
              text(" inline", [{ type: "code" }]),
            ),
            {
              type: "bulletList",
              content: [{ type: "listItem", content: [paragraph(text("Pack the blue compass"))] }],
            },
            {
              type: "orderedList",
              attrs: { start: 3 },
              content: [{ type: "listItem", content: [paragraph(text("Count the markers"))] }],
            },
            { type: "blockquote", content: [paragraph(text("Keep this saved quotation"))] },
            { type: "codeBlock", content: [text("route = 'copper'")] },
            { type: "horizontalRule" },
          ),
        )}
      />,
    );

    expect(screen.getByRole("heading", { name: "Field guide" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Map the copper lantern route", level: 2 }),
    ).toBeVisible();
    expect(screen.getByText("Saved body: follow the turquoise waypoint.").tagName).toBe("STRONG");
    expect(screen.getByText("Check the shoreline").tagName).toBe("EM");
    expect(screen.getByRole("link", { name: "Reference" })).toHaveAttribute(
      "href",
      "https://example.com/guide",
    );
    expect(container.querySelector("a")).not.toHaveAttribute("onclick");
    expect(container.querySelector("ul li")).toHaveTextContent("Pack the blue compass");
    expect(container.querySelector("ol")).toHaveAttribute("start", "3");
    expect(container.querySelector("blockquote")).toHaveTextContent("Keep this saved quotation");
    expect(container.querySelector("pre code")).toHaveTextContent("route = 'copper'");
    expect(container.querySelector("br")).toBeInTheDocument();
    expect(container.querySelector("hr")).toBeInTheDocument();
    expect(container.querySelector("s")).toHaveTextContent("Old");
    expect(container.querySelector("u")).toHaveTextContent("Underlined");
    expect(screen.queryByText("No article content is available yet.")).not.toBeInTheDocument();
  });

  it("escapes markup, drops unsupported nodes and attributes, and keeps unsafe links as text", () => {
    const unsafeUrls = [
      "javascript:alert(1)",
      "data:text/html,untrusted",
      "vbscript:untrusted",
      "//example.com",
      "java\nscript:untrusted",
      "/relative",
    ];
    const { container } = render(
      <LeadMagnetContent
        magnet={richMagnet(
          doc(
            paragraph(
              text("<script>untrusted markup</script>"),
              ...unsafeUrls.map((href, index) =>
                text(`Blocked link ${index}`, [{ type: "link", attrs: { href } }]),
              ),
            ),
            { type: "script", content: [text("Unsupported script body")] },
            { type: "image", attrs: { src: "https://example.com/tracking", onerror: "untrusted" } },
            {
              type: "paragraph",
              attrs: { style: "untrusted", onclick: "untrusted" },
              content: [text("Stored safe paragraph")],
            },
          ),
        )}
      />,
    );
    expect(screen.getByText(/<script>untrusted markup<\/script>/)).toBeVisible();
    expect(screen.getByText(/Blocked link 0/)).toBeVisible();
    expect(
      container.querySelector("script, img, iframe, a, [onclick], [onerror], [style]"),
    ).toBeNull();
    expect(screen.queryByText("Unsupported script body")).not.toBeInTheDocument();
    expect(screen.getByText("Stored safe paragraph")).toBeVisible();
  });

  it.each([
    undefined,
    null,
    "<p>Stored HTML is not TipTap JSON</p>",
    {},
    doc(),
    doc(paragraph()),
    doc(paragraph(text("  \n "))),
    doc({ type: "unknown", content: [text("Hidden unsupported content")] }),
  ])("makes empty or invalid article bodies explicit: %j", (content) => {
    render(<LeadMagnetContent magnet={richMagnet(content)} />);
    expect(screen.getByText("A short overview")).toBeVisible();
    expect(screen.getByText("No article content is available yet.")).toBeVisible();
    expect(screen.queryByText(/delivered after you sign up/)).not.toBeInTheDocument();
  });

  it("handles missing metadata and content, and retains an optional download", () => {
    const { rerender } = render(
      <LeadMagnetContent magnet={{ ...richMagnet(undefined), content_data: undefined }} />,
    );
    expect(screen.getByText("No article content is available yet.")).toBeVisible();
    rerender(
      <LeadMagnetContent
        magnet={{
          ...richMagnet(doc(paragraph(text("Saved downloadable article")))),
          content_url: "https://example.com/article.pdf",
          delivery_method: "download",
        }}
      />,
    );
    expect(screen.getByText("Saved downloadable article")).toBeVisible();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "https://example.com/article.pdf",
    );
  });

  it("bounds deeply nested stored content without crashing", () => {
    let content: unknown = paragraph(text("Deep body"));
    for (let i = 0; i < 40; i++) content = { type: "blockquote", content: [content] };
    render(<LeadMagnetContent magnet={richMagnet(doc(content))} />);
    expect(screen.getByText("No article content is available yet.")).toBeVisible();
  });

  it("keeps quizzes interactive", async () => {
    render(
      <LeadMagnetContent
        magnet={{
          ...richMagnet(undefined),
          magnet_type: "quiz",
          content_data: {
            title: "Quiz",
            questions: [
              {
                id: "q",
                text: "Choose a path",
                type: "single_choice",
                options: [{ id: "a", text: "North", score: 1 }],
              },
            ],
            results: [
              {
                id: "r",
                min_score: 1,
                max_score: 1,
                title: "North result",
                description: "Your saved quiz result",
              },
            ],
          },
        }}
      />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "North" }));
    await userEvent.click(screen.getByRole("button", { name: /result/i }));
    expect(screen.getByText("Your saved quiz result")).toBeVisible();
    expect(screen.queryByText("No article content is available yet.")).not.toBeInTheDocument();
  });

  it("keeps calculator inputs and results working", async () => {
    render(
      <LeadMagnetContent
        magnet={{
          ...richMagnet(undefined),
          magnet_type: "calculator",
          content_data: {
            title: "Calculator",
            inputs: [
              { id: "amount", label: "Amount", type: "number", required: true, default_value: 4 },
            ],
            calculations: [],
            outputs: [
              {
                id: "total",
                label: "Total",
                formula: "amount * 2",
                format: "number",
                highlight: false,
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("8")).toBeVisible();
    await userEvent.clear(screen.getByLabelText("Amount"));
    await userEvent.type(screen.getByLabelText("Amount"), "6");
    expect(screen.getByText("12")).toBeVisible();
  });

  it.each(["video", "webinar", "pdf"] as const)("preserves %s access", (magnet_type) => {
    render(
      <LeadMagnetContent
        magnet={{
          ...richMagnet(undefined),
          magnet_type,
          content_data: undefined,
          content_url: "https://example.com/resource",
        }}
      />,
    );
    expect(
      screen.getByRole("link", { name: magnet_type === "pdf" ? "Access" : "Watch" }),
    ).toHaveAttribute("href", "https://example.com/resource");
  });

  it("preserves the unconfigured document delivery state", () => {
    render(
      <LeadMagnetContent
        magnet={{ ...richMagnet(undefined), magnet_type: "pdf", content_data: undefined }}
      />,
    );
    expect(screen.getByText("This bonus will be delivered after you sign up.")).toBeVisible();
  });
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
