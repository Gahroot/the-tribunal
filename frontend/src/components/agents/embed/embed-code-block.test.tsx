import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmbedCodeBlock } from "./embed-code-block";
import type { EmbedFormValues } from "./embed-types";

const values: EmbedFormValues = {
  embedEnabled: true,
  allowedDomains: ["example.com"],
  buttonText: "Talk to AI",
  theme: "auto",
  position: "bottom-right",
  primaryColor: "#6366f1",
  mode: "voice",
  display: "floating",
};

describe("EmbedCodeBlock", () => {
  it("hides copy-paste snippets and explains the saved-domain requirement", () => {
    render(
      <EmbedCodeBlock
        values={{ ...values, allowedDomains: [] }}
        baseUrl="https://app.example.com"
        publicId="agent_public_id"
        canCopySnippets={false}
        blockedReason="Add the domain where this widget will run, or it will be blocked."
      />,
    );

    expect(
      screen.getByText("Installation code locked until your domain is saved"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Add the domain where this widget will run, or it will be blocked."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Quick Start")).not.toBeInTheDocument();
    expect(screen.queryByText(/widget\/v1\/loader\.js/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy code" })).toBeNull();
  });

  it("shows copyable snippets after prerequisites are saved", () => {
    render(
      <EmbedCodeBlock
        values={values}
        baseUrl="https://app.example.com"
        publicId="agent_public_id"
        canCopySnippets
        blockedReason=""
      />,
    );

    expect(screen.getByText("Quick Start")).toBeInTheDocument();
    expect(screen.getByText(/widget\/v1\/loader\.js/)).toHaveTextContent(
      'data-agent-id="agent_public_id"',
    );
    expect(screen.getByRole("button", { name: "Copy code" })).toBeEnabled();
  });
});
