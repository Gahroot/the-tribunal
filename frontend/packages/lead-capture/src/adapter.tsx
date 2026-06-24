"use client";

// Data-layer adapter for the lead-capture block.
//
// The block's magnet *builders* call the host's lead-magnet AI-generation API.
// To keep the package free of `@/lib/api/*` imports (the host data layer), the
// host supplies a concrete `LeadCaptureAdapter` through
// `LeadCaptureAdapterProvider`; the builders read it via `useLeadCaptureAdapter()`.
// This mirrors the `@tribunal/reviews` adapter pattern. The runners and the
// content viewer need no adapter — they are pure presentational components.

import { createContext, useContext, type ReactNode } from "react";

import type { CalculatorContent, QuizContent } from "@/types";

export interface GenerateQuizRequest {
  topic: string;
  target_audience: string;
  goal: string;
  num_questions?: number;
}

export interface GeneratedQuizContent extends QuizContent {
  success: boolean;
  error?: string;
}

export interface GenerateCalculatorRequest {
  calculator_type: string;
  industry: string;
  target_audience: string;
  value_proposition: string;
}

export interface GeneratedCalculatorContent extends CalculatorContent {
  success: boolean;
  error?: string;
}

/** The host's lead-magnet AI-generation API surface the builders depend on
 * (structurally compatible with the host's `leadMagnetsApi`). */
export interface LeadCaptureApiClient {
  generateQuiz(
    workspaceId: string,
    data: GenerateQuizRequest,
  ): Promise<GeneratedQuizContent>;
  generateCalculator(
    workspaceId: string,
    data: GenerateCalculatorRequest,
  ): Promise<GeneratedCalculatorContent>;
}

export interface LeadCaptureAdapter {
  api: LeadCaptureApiClient;
}

const LeadCaptureAdapterContext = createContext<LeadCaptureAdapter | null>(null);

export function LeadCaptureAdapterProvider({
  adapter,
  children,
}: {
  adapter: LeadCaptureAdapter;
  children: ReactNode;
}) {
  return (
    <LeadCaptureAdapterContext.Provider value={adapter}>
      {children}
    </LeadCaptureAdapterContext.Provider>
  );
}

export function useLeadCaptureAdapter(): LeadCaptureAdapter {
  const adapter = useContext(LeadCaptureAdapterContext);
  if (!adapter) {
    throw new Error(
      "useLeadCaptureAdapter must be used within a <LeadCaptureAdapterProvider>. " +
        "Wrap the lead-magnet builders with the host adapter (see frontend/src/app/lead-magnets).",
    );
  }
  return adapter;
}
