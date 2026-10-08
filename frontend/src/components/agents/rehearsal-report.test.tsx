import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RehearsalReport } from "@/components/agents/rehearsal-report";
import type { RehearsalRun } from "@/types/roleplay";

const run: RehearsalRun = {
  id: "run",
  workspace_id: "workspace",
  agent_id: "agent",
  persona_id: "persona",
  agent_name: "Fixture agent",
  persona_name: "Prospect",
  rehearsee: "ai",
  channel: "sms",
  status: "completed",
  max_turns: 2,
  transcript: [{ role: "prospect", content: "Who is this?" }],
  overall_score: 82,
  objection_coverage: 75,
  tone_score: 80,
  booking_attempted: true,
  scores: { tone_label: "warm" },
  strengths: ["Clear reply"],
  gaps: [],
  suggestions: [],
  summary: "Good rapport",
  error: null,
  created_at: "2026-10-08",
  updated_at: "2026-10-08",
  completed_at: "2026-10-08",
};

describe("RehearsalReport evaluation validity", () => {
  it("shows scores for a completed evaluation", () => {
    render(<RehearsalReport run={run} />);
    expect(screen.getByText("Overall score")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("Good rapport")).toBeInTheDocument();
  });

  it("preserves partial transcript and recovery without scores or raw legacy errors", () => {
    render(
      <RehearsalReport run={{ ...run, status: "failed", error: "private provider diagnostic" }} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("No valid evaluation or score");
    expect(screen.getByRole("alert")).toHaveTextContent("retry with a new run");
    expect(screen.getByText("Who is this?")).toBeInTheDocument();
    expect(screen.queryByText("Overall score")).not.toBeInTheDocument();
    expect(screen.queryByText("82")).not.toBeInTheDocument();
    expect(screen.queryByText("Good rapport")).not.toBeInTheDocument();
    expect(screen.queryByText("Clear reply")).not.toBeInTheDocument();
    expect(screen.queryByText("Attempted booking")).not.toBeInTheDocument();
    expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
  });
});
