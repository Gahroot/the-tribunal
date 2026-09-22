# @tribunal/widget

The embeddable AI agent **chat & voice widget** — a standalone, framework-free
vanilla-TS bundle extracted from the Tribunal dashboard app. It renders a
floating `<ai-agent>` launcher that opens a cross-origin iframe pointing at the
public embed routes (`/embed/<publicId>/…`) and coordinates with them over a
typed `postMessage` protocol.

Mirrors the `public_api` surface of [`docs/blocks/widget/BLOCK.md`](../../../docs/blocks/widget/BLOCK.md).

This package has **zero dependencies on the host app** (`src/components`,
`src/lib`, or app code). The two helpers it needs from the app's shared embed
contract — the `postMessage` protocol and the orb colour math — are vendored in
as `src/messaging.ts` and `src/theme.ts`, so the bundle is genuinely
standalone-embeddable.

## Install

```bash
npm install @tribunal/widget
```

## Usage

The simplest install registers the custom element as an import side effect:

```ts
import "@tribunal/widget";
```

```html
<ai-agent agent-id="ag_xK9mN2pQ" mode="voice"></ai-agent>
```

Supported attributes: `agent-id` (required), `mode` (`voice` | `chat`),
`position` (`bottom-right` | `bottom-left` | `top-right` | `top-left`), `theme`
(`auto` | `light` | `dark`), `button-text`, `base-url`, `primary-color`.

## Public API

| Export                                                                                                                                                                                                                          | Purpose                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `AIAgentElement`                                                                                                                                                                                                                | the `<ai-agent>` custom element class (registered on import) |
| `buildWidgetMarkup`, `buildEmbedIframeSrc`, `WIDGET_ELEMENT_IDS`, `WidgetMode`, `WidgetMarkupConfig`                                                                                                                            | render layer — shadow-DOM markup + iframe-src builders       |
| `WidgetView`, `WidgetViewState`                                                                                                                                                                                                 | imperative open/state/audio-level DOM controller             |
| `WIDGET_CSS`, `themeWidgetCss`                                                                                                                                                                                                  | widget stylesheet + primary-colour baking                    |
| `derivePrimaryShades`, `hexToHsl`, `DEFAULT_PRIMARY_COLOR`, `PrimaryShades`, `Hsl`                                                                                                                                              | orb colour math                                              |
| `subscribeToEmbedMessages`, `postToFrame`, `postToParent`, `parseEmbedMessage`, `isEmbedAgentState`, `EMBED_AGENT_STATES`, `EMBED_MESSAGE_NAMESPACE`, `EmbedMessage`, `EmbedAgentState`, `EmbedMessageType`, `SubscribeOptions` | typed `postMessage` protocol                                 |

The widget talks to the backend embed block (`tribunal-widget`, mounted at
`/api/v1/p/embed`) only indirectly: the iframe it renders loads the app's
`/embed/<publicId>` routes, which call those endpoints.

## Build & test

```bash
npm run build      # tsup -> dist/ (esm + d.ts)
npm run typecheck  # tsc --noEmit
npm run test       # vitest run (jsdom)
```

These also run as part of the host app's `npm ci && npm run build && npm run
typecheck && npm run test` from `frontend/` (the root vitest config includes
`packages/*/src/**` tests).
