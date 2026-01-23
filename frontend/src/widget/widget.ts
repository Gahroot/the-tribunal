/**
 * AI Agent Widget - Standalone Web Component
 *
 * This script creates a floating AI agent widget that can be embedded on any website.
 * Supports both voice and chat modes.
 *
 * Usage:
 *   <script src="https://yourapp.com/widget/v1/widget.js" defer></script>
 *   <ai-agent agent-id="ag_xK9mN2pQ" mode="voice"></ai-agent>
 */

type AgentState = "idle" | "listening" | "thinking" | "speaking";
type WidgetMode = "voice" | "chat";

// Styles for the widget
const styles = `
  .ai-widget-container {
    position: fixed;
    z-index: 9999;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .ai-widget-container.bottom-right {
    bottom: 20px;
    right: 20px;
  }

  .ai-widget-container.bottom-left {
    bottom: 20px;
    left: 20px;
  }

  .ai-widget-container.top-right {
    top: 20px;
    right: 20px;
  }

  .ai-widget-container.top-left {
    top: 20px;
    left: 20px;
  }

  .ai-widget-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    background: var(--ai-primary, #6366f1);
    color: white;
    border: none;
    border-radius: 50px;
    cursor: pointer;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
    transition: all 0.3s ease;
    font-size: 14px;
    font-weight: 500;
  }

  .ai-widget-button:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 32px rgba(0, 0, 0, 0.2);
  }

  .ai-widget-button:active {
    transform: scale(0.98);
  }

  .ai-widget-button svg {
    width: 18px;
    height: 18px;
  }

  .ai-widget-orb {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease;
  }

  .ai-widget-orb-gradient {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(
      from 180deg,
      var(--ai-primary, #6366f1) 0deg,
      var(--ai-primary-60, #6366f188) 90deg,
      var(--ai-primary-30, #6366f144) 180deg,
      var(--ai-primary-60, #6366f188) 270deg,
      var(--ai-primary, #6366f1) 360deg
    );
    transition: opacity 0.3s ease;
  }

  .ai-widget-orb-gradient.animated {
    animation: ai-spin 3s linear infinite;
  }

  .ai-widget-orb-inner {
    position: absolute;
    inset: 3px;
    border-radius: 50%;
    background: white;
    transition: background-color 0.3s ease;
  }

  .ai-widget-orb-dot {
    position: absolute;
    inset: 6px;
    border-radius: 50%;
    background: var(--ai-primary, #6366f1);
    opacity: 0.4;
    transition: all 0.2s ease;
  }

  .ai-widget-orb-dot.active {
    opacity: 0.8;
    transform: scale(1.1);
  }

  /* State-based styling */
  .ai-widget-button.state-listening {
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15), 0 0 12px 4px rgba(34, 197, 94, 0.4);
  }

  .ai-widget-button.state-listening .ai-widget-orb-dot {
    background: #22c55e;
    opacity: 0.9;
    animation: ai-pulse 1.5s ease-in-out infinite;
  }

  .ai-widget-button.state-thinking {
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15), 0 0 12px 4px rgba(251, 191, 36, 0.4);
  }

  .ai-widget-button.state-thinking .ai-widget-orb-dot {
    background: #fbbf24;
    opacity: 0.9;
    animation: ai-think-pulse 0.8s ease-in-out infinite;
  }

  .ai-widget-button.state-speaking {
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15), 0 0 12px 4px rgba(59, 130, 246, 0.4);
  }

  .ai-widget-button.state-speaking .ai-widget-orb-dot {
    background: #3b82f6;
    opacity: 0.9;
    animation: ai-speak-pulse 0.3s ease-in-out infinite;
  }

  .ai-widget-popup {
    position: absolute;
    bottom: 60px;
    right: 0;
    width: 380px;
    height: 520px;
    background: transparent;
    border-radius: 16px;
    overflow: hidden;
    opacity: 0;
    transform: translateY(20px) scale(0.95);
    transition: all 0.3s ease;
    pointer-events: none;
  }

  .ai-widget-popup.open {
    opacity: 1;
    transform: translateY(0) scale(1);
    pointer-events: auto;
  }

  .ai-widget-popup iframe {
    width: 100%;
    height: 100%;
    border: none;
    border-radius: 16px;
  }

  .ai-widget-branding {
    text-align: center;
    font-size: 11px;
    color: #9ca3af;
    margin-top: 8px;
  }

  .ai-widget-branding a {
    color: var(--ai-primary, #6366f1);
    text-decoration: none;
  }

  @keyframes ai-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  @keyframes ai-pulse {
    0%, 100% { transform: scale(1); opacity: 0.9; }
    50% { transform: scale(1.15); opacity: 1; }
  }

  @keyframes ai-think-pulse {
    0%, 100% { transform: scale(1); opacity: 0.7; }
    50% { transform: scale(1.1); opacity: 1; }
  }

  @keyframes ai-speak-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.2); }
  }

  @media (max-width: 480px) {
    .ai-widget-popup {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      border-radius: 0;
      bottom: 0;
      right: 0;
    }
    .ai-widget-popup iframe {
      border-radius: 0;
    }
  }
`;

class AIAgentElement extends HTMLElement {
  private shadow: ShadowRoot;
  private isOpen = false;
  private agentId: string | null = null;
  private position = "bottom-right";
  private theme = "auto";
  private buttonText = "Talk to AI";
  private baseUrl = "";
  private primaryColor = "#6366f1";
  private mode: WidgetMode = "voice";
  private currentState: AgentState = "idle";
  private messageHandler: ((event: MessageEvent) => void) | null = null;

  constructor() {
    super();
    this.shadow = this.attachShadow({ mode: "open" });
  }

  static get observedAttributes() {
    return [
      "agent-id",
      "position",
      "theme",
      "button-text",
      "base-url",
      "primary-color",
      "mode",
    ];
  }

  attributeChangedCallback(name: string, _oldValue: string, newValue: string) {
    switch (name) {
      case "agent-id":
        this.agentId = newValue;
        break;
      case "position":
        this.position = newValue || "bottom-right";
        break;
      case "theme":
        this.theme = newValue || "auto";
        break;
      case "button-text":
        this.buttonText = newValue || "Talk to AI";
        break;
      case "base-url":
        this.baseUrl = newValue || "";
        break;
      case "primary-color":
        this.primaryColor = newValue || "#6366f1";
        break;
      case "mode":
        this.mode = (newValue as WidgetMode) || "voice";
        break;
    }
    if (this.isConnected) {
      this.render();
    }
  }

  connectedCallback() {
    this.agentId = this.getAttribute("agent-id");
    this.position = this.getAttribute("position") ?? "bottom-right";
    this.theme = this.getAttribute("theme") ?? "auto";
    this.buttonText = this.getAttribute("button-text") ?? "Talk to AI";
    this.baseUrl = this.getAttribute("base-url") ?? this.detectBaseUrl();
    this.primaryColor = this.getAttribute("primary-color") ?? "#6366f1";
    this.mode = (this.getAttribute("mode") as WidgetMode) ?? "voice";

    this.render();

    this.messageHandler = (event: MessageEvent) => this.handleMessage(event);
    window.addEventListener("message", this.messageHandler);
  }

  disconnectedCallback() {
    if (this.messageHandler) {
      window.removeEventListener("message", this.messageHandler);
      this.messageHandler = null;
    }
  }

  private detectBaseUrl(): string {
    const scripts = document.getElementsByTagName("script");
    for (const script of scripts) {
      if (script.src?.includes("widget")) {
        try {
          const url = new URL(script.src);
          return `${url.protocol}//${url.host}`;
        } catch {
          // Ignore parse errors
        }
      }
    }
    return window.location.origin;
  }

  private hexToHSL(hex: string): { h: number; s: number; l: number } {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!result?.[1] || !result[2] || !result[3]) return { h: 0, s: 0, l: 50 };

    const r = parseInt(result[1], 16) / 255;
    const g = parseInt(result[2], 16) / 255;
    const b = parseInt(result[3], 16) / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h = 0;
    let s = 0;
    const l = (max + min) / 2;

    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r:
          h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
          break;
        case g:
          h = ((b - r) / d + 2) / 6;
          break;
        case b:
          h = ((r - g) / d + 4) / 6;
          break;
      }
    }

    return {
      h: Math.round(h * 360),
      s: Math.round(s * 100),
      l: Math.round(l * 100),
    };
  }

  private render() {
    if (!this.agentId) {
      console.error("AIAgent: agent-id attribute is required");
      return;
    }

    const hsl = this.hexToHSL(this.primaryColor);
    const primary60 = `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, 0.53)`;
    const primary30 = `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, 0.27)`;

    const customStyles = styles
      .replace(/var\(--ai-primary, #6366f1\)/g, this.primaryColor)
      .replace(/var\(--ai-primary-60, #6366f188\)/g, primary60)
      .replace(/var\(--ai-primary-30, #6366f144\)/g, primary30);

    const embedPath =
      this.mode === "chat"
        ? `/embed/${this.agentId}/chat`
        : `/embed/${this.agentId}`;

    this.shadow.innerHTML = `
      <style>
        :host {
          --ai-primary: ${this.primaryColor};
          --ai-primary-60: ${primary60};
          --ai-primary-30: ${primary30};
        }
        ${customStyles}
      </style>
      <div class="ai-widget-container ${this.position}">
        <div class="ai-widget-popup" id="popup">
          <iframe
            src="${this.baseUrl}${embedPath}?theme=${this.theme}&autostart=true"
            allow="microphone"
            title="AI Agent"
          ></iframe>
        </div>
        <div class="ai-widget-button-wrapper">
          <button class="ai-widget-button" id="toggle">
            <div class="ai-widget-orb" id="orb">
              <div class="ai-widget-orb-gradient" id="orb-gradient"></div>
              <div class="ai-widget-orb-inner"></div>
              <div class="ai-widget-orb-dot" id="orb-dot"></div>
            </div>
            <span id="button-text">${this.buttonText}</span>
          </button>
        </div>
      </div>
    `;

    this.shadow.getElementById("toggle")?.addEventListener("click", () => this.toggle());
  }

  private toggle() {
    this.isOpen = !this.isOpen;
    const popup = this.shadow.getElementById("popup");
    const buttonText = this.shadow.getElementById("button-text");
    const orbGradient = this.shadow.getElementById("orb-gradient");
    const orbDot = this.shadow.getElementById("orb-dot");
    const iframe = popup?.querySelector("iframe");

    if (popup) {
      popup.classList.toggle("open", this.isOpen);
    }

    if (buttonText) {
      buttonText.textContent = this.isOpen ? "Close" : this.buttonText;
    }

    if (orbGradient) {
      orbGradient.classList.toggle("animated", this.isOpen);
    }

    if (orbDot) {
      orbDot.classList.toggle("active", this.isOpen);
    }

    if (this.isOpen && iframe?.contentWindow) {
      iframe.contentWindow.postMessage({ type: "ai-agent:start" }, "*");
    }

    if (!this.isOpen) {
      this.updateState("idle");
    }
  }

  private updateState(state: AgentState) {
    this.currentState = state;
    const button = this.shadow.getElementById("toggle");

    if (button) {
      button.classList.remove(
        "state-idle",
        "state-listening",
        "state-thinking",
        "state-speaking"
      );
      if (state !== "idle") {
        button.classList.add(`state-${state}`);
      }
    }
  }

  private handleMessage(event: MessageEvent) {
    const data = event.data;
    if (!data || typeof data !== "object") return;

    if (data.type === "ai-agent:close") {
      if (this.isOpen) {
        this.toggle();
      }
      return;
    }

    if (data.type === "ai-agent:state") {
      const state = data.state as AgentState;
      if (["idle", "listening", "thinking", "speaking"].includes(state)) {
        this.updateState(state);
      }
      return;
    }

    if (data.type === "ai-agent:audio-level") {
      const level = data.level as number;
      this.updateAudioLevel(level);
    }
  }

  private updateAudioLevel(level: number) {
    const orb = this.shadow.getElementById("orb");
    const button = this.shadow.getElementById("toggle");

    if (orb && this.isOpen) {
      const scale = 1 + level * 0.2;
      orb.style.transform = `scale(${scale})`;
    }

    if (button && this.isOpen && this.currentState === "speaking") {
      const glowSize = 12 + level * 12;
      const glowOpacity = 0.4 + level * 0.4;
      button.style.boxShadow = `0 4px 24px rgba(0, 0, 0, 0.15), 0 0 ${glowSize}px ${glowSize / 2}px rgba(59, 130, 246, ${glowOpacity})`;
    }
  }
}

// Register the custom element
if (!customElements.get("ai-agent")) {
  customElements.define("ai-agent", AIAgentElement);
}

// Export for module usage
export { AIAgentElement };
