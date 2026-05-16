import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Importing the module registers the custom element as a side effect.
import { AIAgentElement } from "@/widget/widget";

const TAG = "ai-agent";

function mountElement(attrs: Record<string, string> = {}): AIAgentElement {
  const el = document.createElement(TAG) as AIAgentElement;
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, v);
  }
  document.body.appendChild(el);
  return el;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("AIAgentElement custom element registration", () => {
  it("registers the <ai-agent> custom element on import", () => {
    expect(customElements.get(TAG)).toBe(AIAgentElement);
  });

  it("constructs with a shadow root attached", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    expect(el.shadowRoot).not.toBeNull();
  });
});

describe("AIAgentElement rendering", () => {
  it("renders the toggle button, orb, and iframe when agent-id is provided", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const shadow = el.shadowRoot!;

    expect(shadow.getElementById("toggle")).not.toBeNull();
    expect(shadow.getElementById("orb")).not.toBeNull();
    expect(shadow.getElementById("orb-gradient")).not.toBeNull();
    expect(shadow.getElementById("orb-dot")).not.toBeNull();

    const iframe = shadow.querySelector("iframe");
    expect(iframe).not.toBeNull();
    expect(iframe!.getAttribute("src")).toContain("/embed/ag_test");
  });

  it("skips rendering and logs when agent-id is missing", () => {
    const el = mountElement();
    expect(el.shadowRoot!.innerHTML).toBe("");
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("agent-id"),
    );
  });

  it("uses the chat embed path when mode='chat'", () => {
    const el = mountElement({ "agent-id": "ag_test", mode: "chat" });
    const iframe = el.shadowRoot!.querySelector("iframe");
    expect(iframe!.getAttribute("src")).toContain(`/embed/ag_test/chat`);
  });

  it("applies the requested position class to the container", () => {
    const el = mountElement({ "agent-id": "ag_test", position: "top-left" });
    expect(el.shadowRoot!.querySelector(".ai-widget-container.top-left")).not.toBeNull();
  });

  it("uses the supplied button-text", () => {
    const el = mountElement({ "agent-id": "ag_test", "button-text": "Chat now" });
    expect(el.shadowRoot!.getElementById("button-text")?.textContent).toBe("Chat now");
  });

  it("threads primary-color into the host CSS variables", () => {
    const el = mountElement({ "agent-id": "ag_test", "primary-color": "#ff00aa" });
    const styleEl = el.shadowRoot!.querySelector("style")!;
    expect(styleEl.textContent).toContain("#ff00aa");
  });
});

describe("AIAgentElement interaction", () => {
  it("toggles the popup open class when the button is clicked", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const shadow = el.shadowRoot!;
    const button = shadow.getElementById("toggle") as HTMLButtonElement;
    const popup = shadow.getElementById("popup")!;
    const buttonText = shadow.getElementById("button-text")!;

    expect(popup.classList.contains("open")).toBe(false);

    button.click();
    expect(popup.classList.contains("open")).toBe(true);
    expect(buttonText.textContent).toBe("Close");

    button.click();
    expect(popup.classList.contains("open")).toBe(false);
    expect(buttonText.textContent).toBe("Talk to AI");
  });

  it("responds to ai-agent:state messages by applying the matching class", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const button = el.shadowRoot!.getElementById("toggle")!;

    window.dispatchEvent(
      new MessageEvent("message", { data: { type: "ai-agent:state", state: "listening" } }),
    );
    expect(button.classList.contains("state-listening")).toBe(true);

    window.dispatchEvent(
      new MessageEvent("message", { data: { type: "ai-agent:state", state: "speaking" } }),
    );
    expect(button.classList.contains("state-listening")).toBe(false);
    expect(button.classList.contains("state-speaking")).toBe(true);
  });

  it("ignores unknown state values from postMessage", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const button = el.shadowRoot!.getElementById("toggle")!;

    window.dispatchEvent(
      new MessageEvent("message", { data: { type: "ai-agent:state", state: "bogus" } }),
    );

    for (const cls of ["state-idle", "state-listening", "state-thinking", "state-speaking"]) {
      expect(button.classList.contains(cls)).toBe(false);
    }
  });

  it("closes the popup when an ai-agent:close message arrives", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const shadow = el.shadowRoot!;
    const button = shadow.getElementById("toggle") as HTMLButtonElement;
    const popup = shadow.getElementById("popup")!;

    button.click();
    expect(popup.classList.contains("open")).toBe(true);

    window.dispatchEvent(
      new MessageEvent("message", { data: { type: "ai-agent:close" } }),
    );
    expect(popup.classList.contains("open")).toBe(false);
  });

  it("removes its message listener on disconnect", () => {
    const el = mountElement({ "agent-id": "ag_test" });
    const button = el.shadowRoot!.getElementById("toggle")!;

    el.remove();

    // After disconnect, state messages should no longer mutate the element.
    window.dispatchEvent(
      new MessageEvent("message", { data: { type: "ai-agent:state", state: "listening" } }),
    );
    expect(button.classList.contains("state-listening")).toBe(false);
  });
});
