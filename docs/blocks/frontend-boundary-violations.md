# Frontend Module-Boundary Violations

Generated from `cd frontend && npm run lint` (rule `boundaries/element-types`).

## What this tracks

`frontend/eslint.config.mjs` enforces module boundaries between the per-block
component folders under `frontend/src/components/<block>/`. The model:

- **Shared layers** — `components/ui`, `components/shared`, `lib`, `providers`,
  `types` — may be imported by any block. The widget-safe embed contract
  `lib/embed` is also importable by the widget.
- **Blocks** — every other `components/<block>` folder. A block may import shared
  layers, itself, and any cross-block edge **declared** in
  `BLOCK_CROSS_DEPENDENCIES` (seeded from `docs/blocks/registry.json`
  `depends_on`). Any other cross-block import is a **warning** listed below.
- **Widget** — `src/widget/` is isolated and standalone-embeddable. It may only
  import `lib/embed`; importing `components/**` or other `lib/**` app code is an
  **error**.

## Enforcement levels

| Rule | Level | Status |
| --- | --- | --- |
| Widget isolation (`src/widget` ⇏ `components/**`, `lib/**` app code) | **error** | enforced, passing |
| Shared one-way (`ui`/`shared`/`lib`/`providers`/`types` ⇏ blocks/widget) | **error** | enforced, passing |
| Undeclared cross-block imports | **warning** | tracked below |

`make ci.frontend` runs `npm run lint`, so the error-level rules block CI while
the warnings keep the build green until the coupling below is decoupled.

## How to resolve a violation

1. **Legitimate dependency?** Add the target folder to the source block's entry
   in `BLOCK_CROSS_DEPENDENCIES` in `frontend/eslint.config.mjs` (and reflect it
   in `docs/blocks/registry.json` `depends_on` if it is a real block-level edge).
2. **Accidental coupling?** Move the shared piece into `components/shared`,
   `components/ui`, or `lib/`, then import it from there.
3. Re-run `cd frontend && npm run lint` and update this file.

## Notes on common offenders

- `resource-list`, `suggestions`, `actions`, `landing`, `layout`, `wizard`,
  `assistant`, `queue`, `onboarding`, `workspaces`, `conversation` are
  cross-cutting UI folders not yet modeled as blocks in `registry.json`. Most are
  candidates to fold into `components/shared` (or to register as their own
  blocks with explicit `depends_on`).
- `tags`/`segments`/`filters`/`contacts` are all owned by the **contacts** block
  in `registry.json`; their intra-domain imports are flagged only because each
  is a separate top-level folder. Folding them under a single block boundary (or
  declaring the edges) would clear those.

## Current cross-block violations (warnings)

### `agents → landing` (1)

- `src/components/agents/agents-list.tsx:26`

### `agents → resource-list` (1)

- `src/components/agents/agents-list.tsx:34`

### `agents → suggestions` (1)

- `src/components/agents/prompt-improvement-dialog.tsx:8`

### `campaigns → resource-list` (1)

- `src/components/campaigns/campaigns-list.tsx:30`

### `campaigns → suggestions` (1)

- `src/components/campaigns/campaign-detail.tsx:21`

### `campaigns → wizard` (1)

- `src/components/campaigns/base-campaign-wizard-layout.tsx:7`

### `contacts → actions` (1)

- `src/components/contacts/contact-sidebar.tsx:8`

### `contacts → filters` (1)

- `src/components/contacts/contacts-toolbar.tsx:5`

### `contacts → resource-list` (1)

- `src/components/contacts/contacts-page.tsx:18`

### `contacts → tags` (4)

- `src/components/contacts/bulk-tag-dialog.tsx:7`
- `src/components/contacts/bulk-tag-dialog.tsx:8`
- `src/components/contacts/contact-card.tsx:8`
- `src/components/contacts/contact-sidebar/contact-info-section.tsx:6`

### `conversation → calls` (1)

- `src/components/conversation/call-message-item.tsx:16`

### `experiments → resource-list` (1)

- `src/components/experiments/experiments-list.tsx:28`

### `experiments → segments` (1)

- `src/components/experiments/message-test-wizard.tsx:17`

### `experiments → wizard` (1)

- `src/components/experiments/message-test-wizard.tsx:32`

### `filters → segments` (1)

- `src/components/filters/contact-filter-builder.tsx:7`

### `filters → tags` (1)

- `src/components/filters/contact-filter-builder.tsx:8`

### `knowledge → layout` (1)

- `src/components/knowledge/knowledge-base-page.tsx:7`

### `layout → contacts` (3)

- `src/components/layout/conversation-layout.tsx:7`
- `src/components/layout/unified-inbox.tsx:6`
- `src/components/layout/unified-inbox.tsx:7`

### `layout → conversation` (2)

- `src/components/layout/conversation-layout.tsx:8`
- `src/components/layout/unified-inbox.tsx:8`

### `layout → onboarding` (1)

- `src/components/layout/app-sidebar.tsx:11`

### `layout → queue` (1)

- `src/components/layout/conversation-layout.tsx:9`

### `layout → workspaces` (2)

- `src/components/layout/app-sidebar.tsx:51`
- `src/components/layout/workspace-switcher.tsx:19`

### `pending-actions → assistant` (1)

- `src/components/pending-actions/pending-action-card.tsx:8`

### `reviews → layout` (1)

- `src/components/reviews/reviews-page.tsx:7`

### `segments → layout` (1)

- `src/components/segments/segments-page.tsx:8`

### `settings → resource-list` (1)

- `src/components/settings/lead-sources-settings-tab.tsx:16`

### `settings → tags` (1)

- `src/components/settings/settings-page.tsx:15`

### `settings → workspaces` (2)

- `src/components/settings/team-settings-tab.tsx:10`
- `src/components/settings/team/team-member-role-dialog.tsx:3`

---

_Total: 36 cross-block warnings across 28 edges. 0 errors._
