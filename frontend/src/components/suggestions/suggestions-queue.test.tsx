import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildPromptLineDiff, PromptDiff } from "@/components/suggestions/suggestions-queue";

describe("buildPromptLineDiff", () => {
  it("marks removed and added prompt lines against unchanged context", () => {
    expect(buildPromptLineDiff("Keep this\nOld close", "Keep this\nNew close")).toEqual([
      {
        type: "unchanged",
        oldLineNumber: 1,
        newLineNumber: 1,
        text: "Keep this",
      },
      {
        type: "removed",
        oldLineNumber: 2,
        text: "Old close",
      },
      {
        type: "added",
        newLineNumber: 2,
        text: "New close",
      },
    ]);
  });
});

describe("PromptDiff", () => {
  it("renders current/source and suggested prompt changes", () => {
    render(<PromptDiff sourceText="Ask one question" suggestedText="Ask one warm question" />);

    expect(screen.getByText("− Current/source prompt")).toBeInTheDocument();
    expect(screen.getByText("+ Suggested prompt")).toBeInTheDocument();

    const removedRow = screen.getByText("Ask one question").closest("div");
    const addedRow = screen.getByText("Ask one warm question").closest("div");

    expect(removedRow).not.toBeNull();
    expect(addedRow).not.toBeNull();
    expect(within(removedRow as HTMLElement).getByText("−")).toBeInTheDocument();
    expect(within(addedRow as HTMLElement).getByText("+")).toBeInTheDocument();
  });
});
