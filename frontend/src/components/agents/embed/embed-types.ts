/**
 * Shared types for the embed-agent dialog and its extracted sub-components.
 */

export interface EmbedFormValues {
  embedEnabled: boolean;
  allowedDomains: string[];
  buttonText: string;
  theme: string;
  position: string;
  primaryColor: string;
  mode: string;
  display: string;
}

export const POSITION_OPTIONS = [
  { value: "bottom-right", label: "Bottom Right" },
  { value: "bottom-left", label: "Bottom Left" },
  { value: "top-right", label: "Top Right" },
  { value: "top-left", label: "Top Left" },
] as const;

export const THEME_OPTIONS = [
  { value: "auto", label: "Auto (System)" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

export const MODE_OPTIONS = [
  { value: "voice", label: "Voice Only" },
  { value: "chat", label: "Chat Only" },
  { value: "both", label: "Both" },
] as const;

export const DISPLAY_OPTIONS = [
  { value: "floating", label: "Floating Widget" },
  { value: "inline", label: "Inline Embed" },
  { value: "fullpage", label: "Full Page" },
] as const;

/**
 * Compute the iframe path segment that corresponds to the current mode/display
 * selection. Returns `""` for the default (voice + floating).
 */
export function getModePath(display: string, mode: string): string {
  if (display === "fullpage") return "fullpage";
  if (mode === "chat") return "chat";
  if (mode === "both") return "both";
  return "";
}
