# Embed Experience Overhaul — Make Agent Embedding Dead Simple

## Current State

You already have a working foundation:
- **Backend**: `backend/app/api/v1/embed.py` — public endpoints for config, token (WebRTC voice), chat, tool calls, transcripts, phone calls, SMS
- **Frontend embed pages**: Voice (`/embed/[publicId]`) and Chat (`/embed/[publicId]/chat`) — full working implementations with WebRTC voice + text chat
- **Widget**: `frontend/public/widget/v1/widget.js` — Web Component (`<ai-agent>`) that loads embed pages in an iframe
- **Settings dialog**: `frontend/src/components/agents/embed-agent-dialog.tsx` — configure mode, theme, position, color, domains
- **Agent service**: `backend/app/services/agents/agent_service.py` — generates `public_id`, manages embed settings

### What's Missing / Friction Points

1. **No "both" mode in the widget** — `widget.js` only loads voice OR chat path, not a combined experience
2. **No live preview** in the embed dialog — you configure settings blind
3. **No platform-specific snippets** — WordPress, Shopify, Webflow, React, HTML all need slightly different instructions
4. **No inline/fullpage embed option** — only floating widget or manual iframe
5. **No quick one-liner** — the embed code is verbose; should have a single `<script>` tag option
6. **No "both" mode embed page** — missing a combined voice+chat embed page
7. **Embed dialog UX** — buried inside agent detail page, should be more prominent and streamlined

---

## Plan

### Phase 1: Combined Voice+Chat Embed Page (Backend + Frontend)

**Goal**: Create a `/embed/[publicId]/both` page that shows chat by default with a mic button to switch to voice.

#### 1a. New embed page: `frontend/src/app/embed/[publicId]/both/page.tsx`
- Chat interface as the primary UI (messages list + input)
- Mic/voice button in the input bar that starts a WebRTC voice session
- When voice is active, show the voice visualizer overlaid on the chat
- Voice transcripts stream into the chat messages in real-time
- Reuse the WebRTC logic from the voice page and chat logic from the chat page
- ~300 lines, combining patterns from both existing pages

#### 1b. Update widget.js to handle `mode="both"`
- File: `frontend/public/widget/v1/widget.js`
- When `mode="both"`, load `/embed/{id}/both` path
- Already handles voice and chat paths; just need to add the third case

### Phase 2: One-Line Embed Script

**Goal**: A single script tag that auto-configures everything — no web component tag needed.

#### 2a. New auto-init widget: `frontend/public/widget/v1/loader.js`
- Tiny (~2KB) script that:
  1. Reads `data-agent-id` from its own `<script>` tag
  2. Fetches agent config from `/api/v1/p/embed/{id}/config` 
  3. Creates the `<ai-agent>` web component with all settings pre-filled
- Usage becomes: `<script src="https://app.com/widget/v1/loader.js" data-agent-id="ag_xK9mN2pQ" defer></script>`
- One line. That's it. Auto-detects mode, theme, position, color from saved settings.

#### 2b. Update embed dialog to show the one-liner as the default/first option
- File: `frontend/src/components/agents/embed-agent-dialog.tsx`
- Add a third tab: "One-Line" (shown first, before Script Tag and Iframe)
- The one-liner code snippet

### Phase 3: Live Preview in Embed Dialog

**Goal**: See what the widget looks like as you configure it.

#### 3a. Add preview panel to embed dialog
- File: `frontend/src/components/agents/embed-agent-dialog.tsx`
- Widen dialog to `sm:max-w-[900px]` with a two-column layout
- Left: settings (existing form)
- Right: live preview iframe showing the embed page with current settings as query params
- Preview updates live as you change mode, theme, color, position, button text
- Use `?preview=true` query param to show the widget in a non-interactive demo state

### Phase 4: Platform-Specific Install Guides

**Goal**: Copy-paste instructions for every major platform.

#### 4a. Add platform tabs to embed dialog
- File: `frontend/src/components/agents/embed-agent-dialog.tsx`
- Replace the current Script/Iframe tabs with a richer set:
  - **Quick Start** (one-liner) — default
  - **HTML/JS** (web component + script)
  - **React/Next.js** — npm package-style (just the iframe approach with a React component wrapper snippet)
  - **WordPress** — instructions to paste in theme footer or use Custom HTML widget
  - **Shopify** — paste in theme.liquid before `</body>`
  - **Webflow** — Custom Code in project settings
  - **iframe** — for any platform, direct iframe embed
- Each tab shows the exact code + 1-2 sentence instruction

### Phase 5: Fullpage Embed Mode

**Goal**: Allow agents to be embedded as full-page experiences (for landing pages, dedicated chat pages).

#### 5a. Add `display` option to embed settings
- Possible values: `floating` (current default), `inline`, `fullpage`
- `floating` = current bubble widget behavior
- `inline` = embeds directly into a container div (no floating button)
- `fullpage` = takes over the entire iframe/page

#### 5b. New fullpage embed page: `frontend/src/app/embed/[publicId]/fullpage/page.tsx`
- Full-screen chat+voice experience
- No floating button — the whole page IS the agent
- Great for dedicated "Talk to our AI" pages
- iframe code with `width="100%" height="100%"` or a direct link

#### 5c. Update widget.js for inline mode
- New attribute: `display="inline"` 
- Instead of fixed positioning, render directly in the page flow
- Takes the size of its container element

### Phase 6: Shareable Direct Link

**Goal**: Not everyone needs an embed. Sometimes you just want a link.

#### 6a. Add "Share Link" option to embed dialog
- Direct link: `https://app.com/embed/{publicId}/fullpage?theme=dark`
- QR code generation (use a simple QR library or canvas-based generation)
- Copy button for the link

---

## Implementation Order & Files

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 1 | One-line loader script | `frontend/public/widget/v1/loader.js` | — |
| 2 | Combined voice+chat embed page | `frontend/src/app/embed/[publicId]/both/page.tsx` | — |
| 3 | Update widget.js for both + inline modes | `frontend/public/widget/v1/widget.js` | #2 |
| 4 | Fullpage embed page | `frontend/src/app/embed/[publicId]/fullpage/page.tsx` | — |
| 5 | Revamp embed dialog: live preview + platform tabs + one-liner | `frontend/src/components/agents/embed-agent-dialog.tsx` | #1, #4 |
| 6 | Add `display` field to embed settings | `backend/app/services/agents/agent_service.py`, `backend/app/schemas/agent.py`, `frontend/src/lib/api/agents.ts` | — |
| 7 | Shareable link + QR code in embed dialog | `frontend/src/components/agents/embed-agent-dialog.tsx` | #4, #5 |

## Verification

After each task:
```bash
cd frontend && npm run lint && npm run build
cd backend && uv run ruff check app && uv run mypy app
```

Test the widget manually:
1. Enable embedding for an agent in the dashboard
2. Open the embed dialog — verify live preview works
3. Copy the one-liner script — paste it in a test HTML file — verify it loads
4. Test all modes: voice, chat, both
5. Test fullpage link in a new tab
6. Test on mobile viewport (the widget should go fullscreen on <480px — already handled)
