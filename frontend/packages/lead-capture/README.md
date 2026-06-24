# @tribunal/lead-capture

Extracted frontend package for the **lead-capture** block (lead-magnet builders,
runners, and content viewer).

> Mirrors `docs/blocks/lead-capture/BLOCK.md` (frontend surface).

## Exports

| Export                                                 | Adapter? | Purpose                                                                                                 |
| ------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------- |
| `LeadMagnetContent`                                    | no       | render a magnet's consumable content (quiz/calculator/rich/download) on the public offer page + preview |
| `QuizRunner` / `CalculatorRunner`                      | no       | interactive quiz / ROI-calculator runners                                                               |
| `QuizBuilder` / `CalculatorBuilder`                    | yes      | authoring builders; call the host AI-generation API via the adapter                                     |
| `RichTextEditor`                                       | no       | tiptap rich-text magnet editor                                                                          |
| `LeadCaptureAdapterProvider` / `useLeadCaptureAdapter` | —        | inject the host's lead-magnet AI-generation API                                                         |

## Adapter

The builders (`QuizBuilder`, `CalculatorBuilder`) call the host's lead-magnet
AI-generation API. The package stays free of `@/lib/api/*` imports; the host
injects a concrete adapter once (matching the `@tribunal/reviews` pattern):

```tsx
import {
  LeadCaptureAdapterProvider,
  QuizBuilder,
  type LeadCaptureAdapter,
} from "@tribunal/lead-capture";
import { leadMagnetsApi } from "@/lib/api/lead-magnets";

const adapter: LeadCaptureAdapter = { api: leadMagnetsApi };

<LeadCaptureAdapterProvider adapter={adapter}>
  <QuizBuilder workspaceId={workspaceId} value={quiz} onChange={setQuiz} />
</LeadCaptureAdapterProvider>;
```

`LeadMagnetContent` / `QuizRunner` / `CalculatorRunner` are pure presentational
components and render without any provider.

## Host coupling

Like `@tribunal/reviews`, this package resolves host UI primitives
(`@/components/ui/*`), shared utils (`@/lib/utils`, `@/lib/utils/number`,
`@/lib/utils/safe-formula`) and shared types (`@/types`) through the `@/*`
tsconfig path alias back to the host `frontend/src/`. Only the data layer (the
AI-generation API) is decoupled via the adapter. The host transpiles this
package via `transpilePackages` in `next.config.ts`.
