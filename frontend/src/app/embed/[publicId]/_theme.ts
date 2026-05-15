/**
 * Theme tokens for embed pages. Keeps the dense palette of inline hex values
 * out of the page components.
 */

export interface EmbedTheme {
  isDark: boolean;
  // Surface backgrounds
  pageBg: string;
  panelBg: string;
  panelOverlayBg: string;
  messagesBg: string;
  inputBg: string;
  inputBorder: string;
  bubbleAssistantBg: string;
  bubbleAssistantText: string;
  // Borders
  panelBorder: string;
  // Text
  text: string;
  textMuted: string;
  textOnPrimary: string;
  // Voice-state pill / icons
  iconBg: string;
  iconColor: string;
  // Shadows
  bubbleShadow: string;
}

const LIGHT: EmbedTheme = {
  isDark: false,
  pageBg: "#f9fafb",
  panelBg: "#ffffff",
  panelOverlayBg: "rgba(255, 255, 255, 0.95)",
  messagesBg: "#f9fafb",
  inputBg: "#f3f4f6",
  inputBorder: "#e5e7eb",
  bubbleAssistantBg: "#ffffff",
  bubbleAssistantText: "#1f2937",
  panelBorder: "#e5e7eb",
  text: "#1f2937",
  textMuted: "#6b7280",
  textOnPrimary: "#ffffff",
  iconBg: "#e5e7eb",
  iconColor: "#4b5563",
  bubbleShadow: "0 1px 2px rgba(0,0,0,0.1)",
};

const DARK: EmbedTheme = {
  isDark: true,
  pageBg: "#111827",
  panelBg: "#1f2937",
  panelOverlayBg: "rgba(17, 24, 39, 0.95)",
  messagesBg: "#111827",
  inputBg: "#374151",
  inputBorder: "#4b5563",
  bubbleAssistantBg: "#374151",
  bubbleAssistantText: "#f3f4f6",
  panelBorder: "#374151",
  text: "#f3f4f6",
  textMuted: "#9ca3af",
  textOnPrimary: "#ffffff",
  iconBg: "#374151",
  iconColor: "#d1d5db",
  bubbleShadow: "0 1px 2px rgba(0,0,0,0.3)",
};

export function getEmbedTheme(isDark: boolean): EmbedTheme {
  return isDark ? DARK : LIGHT;
}

/**
 * Agent state colors (status pill / center orb).
 * Used by the visualizer in the root embed page and the header pill in others.
 */
export interface AgentStateInfo {
  color: string;
  label: string;
}

export function getAgentStateInfo(
  agentState: "idle" | "listening" | "thinking" | "speaking",
  primaryColor: string,
  idleLabel: string = "Ready"
): AgentStateInfo {
  switch (agentState) {
    case "listening":
      return { color: "#22c55e", label: "Listening" };
    case "thinking":
      return { color: "#f59e0b", label: "Thinking" };
    case "speaking":
      return { color: "#3b82f6", label: "Speaking" };
    default:
      return { color: primaryColor, label: idleLabel };
  }
}

export const DEFAULT_PRIMARY_COLOR = "#6366f1";
