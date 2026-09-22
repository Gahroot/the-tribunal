// Public entry for @tribunal/widget — the embeddable AI agent chat/voice widget.
//
// Mirrors the public_api surface of docs/blocks/widget/BLOCK.md. Importing this
// module (or the bundle it builds to) registers the `<ai-agent>` custom element
// as a side effect, so the simplest install is a single `import "@tribunal/widget"`.

// Side-effectful import below registers the <ai-agent> element; this also
// re-exports the element class for programmatic use.
export { AIAgentElement } from "./widget";

// Render layer — markup + iframe-src builders and stable element ids.
export {
  buildEmbedIframeSrc,
  buildWidgetMarkup,
  WIDGET_ELEMENT_IDS,
  type WidgetMarkupConfig,
  type WidgetMode,
} from "./render";

// Imperative view controller for the widget's shadow DOM.
export { WidgetView, type WidgetViewState } from "./view";

// Stylesheet + primary-color baking.
export { WIDGET_CSS, themeWidgetCss } from "./styles";

// Theme helpers used to colour the orb.
export {
  DEFAULT_PRIMARY_COLOR,
  derivePrimaryShades,
  hexToHsl,
  type Hsl,
  type PrimaryShades,
} from "./theme";

// Typed postMessage protocol between the host widget and the embedded agent UI.
export {
  EMBED_AGENT_STATES,
  EMBED_MESSAGE_NAMESPACE,
  isEmbedAgentState,
  parseEmbedMessage,
  postToFrame,
  postToParent,
  subscribeToEmbedMessages,
  type EmbedAgentState,
  type EmbedMessage,
  type EmbedMessageType,
  type SubscribeOptions,
} from "./messaging";
