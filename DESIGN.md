# Inbox follow-up reliability

Scope: the approved Today → waiting inbox → selected conversation → reviewed reply → next conversation flow. This is not a new app-wide visual direction. Base commit: `0ed1293`.

## Design read

- **Surface:** authenticated, data-dense CRM application.
- **Audience:** operators handling live leads, frequently interrupted, on desktop and narrow/touch screens.
- **Single job:** find the next conversation that needs a human reply, understand it, and deliberately send from the correct workspace phone.
- **Risk:** reading is not replying; a missed thread can hide unfinished work. Sending to the wrong thread/number has a higher cost than an extra explicit confirmation.
- **Constraints:** preserve the recent three-column inbox, Today cards, contact detail panel, campaign composer, appointment/approval work, shared tokens and existing outreach gates. No new dependency or visual library.

## Evidence and direction

Three full Refero flows and three images were inspected in planning. References are observations, not conversion benchmarks:

- [Missive 6264](https://refero.design/flows/6264): saved work views. Keep saved views and make the underlying counts/search complete.
- [Missive 6281](https://refero.design/flows/6281): snooze with confirmation and undo. Deferred until daily use shows a real need for snoozing.
- [Linear 6681](https://refero.design/flows/6681): filtered list with persistent detail and an explanation of hidden items. Preserve explicit selection across filtering and paging.
- [Intercom context](https://refero.design/pages/5a1eb15f-2704-4d6e-8779-aecdb079c824): conversation adjacent to customer details. Retain this app's existing layout, not Intercom branding.

Code evidence: the corpus tool supplied DeskcommCRM's server-filtered inbox route and Django-CRM's shared rollup definitions. We adapted principles, not source code, dependencies, admin privileges or cursor casts. No standalone Corpus CLI was installed; the connected tool was used.

**Thesis:** make the current inbox trustworthy rather than visually novel. First glance: waiting count and list. Second glance: exact thread, sender number and contact context. Primary action: review/edit → Send. Secondary action: Next waiting reply. Reading must never pretend to complete the job.

## Reuse and craft

- Existing `Button`, `Input`, `Badge`, `Sheet`, `PageEmptyState`, `PageErrorState`, `Skeleton`, message renderers and `MessageComposer`.
- Existing Manrope typography, Lucide icons, shared padding/breakpoints, monochrome surfaces and purple primary treatment. No palette/font/radius replacement, decorative dashboard, hover lift or generated imagery.
- Shared tokens from `frontend/src/app/globals.css`: foreground/background, muted foreground, primary/primary foreground, border and focus ring. No new hard-coded semantic colors.
- Only an outline `Needs reply` label is added; unread remains a distinct badge. Channel and actual workspace sender line are visible.
- Fake attachment/voice-recording controls are not advertised in text-only inbox mode. Legacy contact-page controls remain unchanged.
- Reuse existing motion, with no new animated decoration. Visual verification waits for settled data rather than capturing skeletons as final output.

## Behavior contract

### List and selection

- Server-side workspace search, counts and views, 50 rows/page with a maximum API page size of 100.
- Waiting means active + latest inbound + AI paused/disabled. It does **not** mean unread, and does not diagnose a broken AI/provider.
- Waiting sorts oldest last-message timestamp first; other views newest first. UUID tie-breaker; null dates last.
- Counts describe the current search across all pages, before the selected built-in view.
- Search covers names, phone and latest preview. A full email uses the existing email hash; partial encrypted-email search and all-history search are not supported.
- UI search uses a read-only POST body so typed terms are absent from browser addresses and ordinary access-log URLs. GET remains available for bounded discovery/API compatibility. No new analytics or tracking.
- URL state contains built-in view + selected conversation UUID. Browser Back/Forward restores selection. Initial workspace resolution preserves a deep link; an actual workspace switch clears the old selection.
- Explicit selection resolves independently of list pagination. An unavailable thread never silently becomes a different thread.
- Saved-view format/key remains compatible with the existing feature; saved selections show their active state.

### Read, draft, send

- List/detail/message reads do not synchronize campaign assignment or AI settings.
- A separate acknowledgment compares the displayed timestamp and unread count before clearing unread, preventing a stale read from clearing a newer arrival.
- Both linked contacts and unknown numbers use one exact-thread renderer. Contact profile pages keep their unified timeline.
- Drafts are bounded, in-memory and keyed by workspace + conversation. Switching threads/workspaces in the inbox preserves them. No message bodies are added to local storage. Reload/ordinary links warn before discarding; these are not durable saved drafts.
- Generation is optional, cancellable and never sends. Existing text needs confirmation before replacement. New typing and a newer selection win over late generated output.
- Sending is explicit and single-flight. Failure keeps text and permits a deliberate retry. Accepted queued messages say queued, not delivered.
- Inbox/detail, messages, Today and relevant contact timeline caches refresh after actions. Selection stays put after a reply; moving on is explicit.
- Recent message history is bounded at 100 and labels the limit; call transcript/playback metadata is retained.

## States and responsive behavior

- Initial loading, filtered/workspace-empty, pending search, failed list/detail/messages, retry, missing selection, read failure, drafting, send failure and queued success.
- No empty or zero-success state in place of an error. Error handling is local instead of letting the global server-error boundary remove the working inbox.
- Desktop: list + thread; contact context at the existing wide breakpoint. Narrow: list or thread, Back control, contact context sheet, preserved draft/selection.
- Keyboard-operable native buttons/input, accessible control names, result-count status, predictable selected heading focus and sheet Escape/focus return.
- Shared mobile detection now uses a stable server snapshot; theme icons use CSS rather than conflicting server/client markup. These fixes address hydration failures observed during the browser flow.

## Verification and limits

See [inbox verification](docs/inbox-verification.md) for commands and observed results, and [daily revenue workflow](docs/daily-revenue-workflow.md) for the seven-working-day evaluation.

Screenshots and browser fixtures are synthetic and labelled. They do not establish revenue uplift, delivery to a real recipient, legal compliance, full WCAG conformance, screen-reader support on every platform, or production-scale latency. No live outreach or production-data changes were performed.
