// Public entry for @tribunal/lead-capture.
//
// Mirrors the `public_api` of docs/blocks/lead-capture/BLOCK.md (frontend
// surface). The magnet builders call the host's AI-generation API through the
// lead-capture adapter (see ./adapter); the host route supplies a concrete
// adapter and owns chrome. The runners + content viewer are pure presentational
// components and need no adapter.

export { CalculatorBuilder } from "./components/calculator-builder";
export { CalculatorRunner } from "./components/calculator-runner";
export { QuizBuilder } from "./components/quiz-builder";
export { QuizRunner } from "./components/quiz-runner";
export { RichTextEditor } from "./components/rich-text-editor";
export { LeadMagnetContent } from "./components/lead-magnet-content";

export {
  LeadCaptureAdapterProvider,
  useLeadCaptureAdapter,
  type LeadCaptureAdapter,
  type LeadCaptureApiClient,
  type GenerateQuizRequest,
  type GeneratedQuizContent,
  type GenerateCalculatorRequest,
  type GeneratedCalculatorContent,
} from "./adapter";
