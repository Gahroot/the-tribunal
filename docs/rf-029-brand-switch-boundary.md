# RF-029 — brand-switch state boundary

A **workspace** remains the existing persisted/API container for a **brand** (ORG-001). No organization schema, company grouping, tenancy migration, or backend ownership change is introduced.

## Local-state contract

- `WorkspaceProvider` accepts only a listed brand; choosing the current brand is a no-op. The last good membership list survives a failed refresh.
- `BrandSwitchBoundary` remounts brand-owned descendants on every resolved brand change, including membership fallback. `ContactsPage` row selection, all-matching overlays, dialogs and debounced inputs; conversation route/layout selections; inbox drafts; and composer sender identities therefore start fresh. `useRowSelection` stays a generic, provider-independent hook: the shared boundary resets its component instance rather than adding a hidden workspace dependency.
- Contact stores are per-session instances. All callers use the nearest context. A late mutation callback can only write its detached old instance, including after A → B → A. The standalone store API remains for existing component fixtures.
- Theme/auth/query providers stay above the boundary. Contact page size and sorting remain user-wide display preferences; contact selections, searches, filters, pagination position and local agent assignments do not carry across brands.
- Contact/conversation detail routes and their query selections are replaced with the list route on switching. While Next navigation is outstanding, descendants are hidden: no new-brand request is issued for the old route. Initial authorized deep links remain valid.
- Panels check workspace identity as well as contact ID and do not prefer a selected contact over a failed fetch. Full conversation routes wait for their own fetched contact before rendering the layout. Composer instances are also keyed by contact/thread identity; explicit `null` means no contact, not fallback to the store.
- Only old-brand queries are cancelled/removed. User-scoped caches and mutation objects survive; old server operations keep their captured workspace IDs and workspace-aware invalidation keys. Cancelling a query is not a promise that its HTTP/server work stops. Detached UI state prevents late adoption regardless. Completed old-brand sends still invalidate their original keys, but cannot restore drafts or announce composer results in the new session.

This is a frontend isolation boundary, not authorization. Existing backend workspace/contact ownership checks remain required and unchanged. Optional legacy contact `workspace_id` values are not invented; session origin provides isolation, with explicit mismatches rejected when the API supplies identity.

## Working-code reference

Read via `steroids`: `MCPJam/inspector`, `mcpjam-inspector/client/src/components/billing/AutoTopupDialogBody.tsx:89–104`, revision `6005e14f2feb7f55c03797b5ab1784de9bbf0daa`. Its identity-keyed error boundary encloses connected state, resetting that subtree when identity changes. RF-029 applies this React identity pattern to brand sessions; it does not copy organization/billing behavior.

## Regression proof

Existing Vitest suite: `src/providers/brand-switch-boundary.test.tsx` exercises the actual provider, boundary, contact panel, contact composer, scoped store and row-selection hook with deterministic network promises and stubbed visual leaf components. Covers open A contact/draft/sender/selections with failed B fetch; switch-back; stale store callbacks and AI drafts; old-brand send failure with a surviving mutation object; late contact fetch; and delayed route replacement. `workspace-provider.test.tsx` retains membership outage/recovery coverage and verifies only old-brand query removal.

Affected backend tests: contact validation/auth, API-key workspace binding, workspace defaults, contact AI assignment, and conversation contact filtering. No backend files are changed by RF-029.

Runtime results: frontend lint (existing warnings), typecheck, all 741 tests in 89 files, and production build passed via `make ci.frontend -o ci.frontend.deps -o ci.env`. The 50 affected backend tests passed. Full `make ci.frontend` stopped at existing backend environment-template drift: missing `CALLER_MEMORY_MODEL`, `PROMPT_IMPROVEMENT_MODEL`, `REPORTS_MODEL`, `TRANSCRIPT_ANALYSIS_MODEL`, and `TRANSCRIPT_JUDGMENT_MODEL`. The gate and templates were left unchanged. The installed runtime is Node 24, while the project specifies Node 20; npm emitted an engine warning.

Browser screenshots/visual layout proof are not available from this checkout's verified probes. Component fixtures prove behavior, not pixel appearance.
