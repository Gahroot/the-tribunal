/**
 * Widget theming helpers — the colour math the embeddable orb needs to render
 * its conic gradient from a single base primary colour.
 *
 * This is the widget-only slice of the host app's shared embed theme module.
 * It is vendored into the `@tribunal/widget` package so the standalone bundle
 * has no dependency on the dashboard app's `src/lib`. The React embed routes
 * keep their richer palette/theme-resolution helpers in the app; the widget
 * only needs primary-shade derivation.
 */

export const DEFAULT_PRIMARY_COLOR = "#6366f1";

export interface Hsl {
  h: number;
  s: number;
  l: number;
}

/**
 * Convert a 6-digit hex color (with or without leading `#`) to HSL. Falls back
 * to a neutral mid-gray for malformed input so the widget never throws while
 * theming.
 */
export function hexToHsl(hex: string): Hsl {
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

export interface PrimaryShades {
  primary: string;
  /** ~53% alpha variant for the conic gradient mid-stop. */
  primary60: string;
  /** ~27% alpha variant for the conic gradient outer-stop. */
  primary30: string;
}

/**
 * Derive the translucent primary-color shades the widget orb's conic gradient
 * needs from a single base hex color.
 */
export function derivePrimaryShades(primaryColor: string): PrimaryShades {
  const hsl = hexToHsl(primaryColor);
  return {
    primary: primaryColor,
    primary60: `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, 0.53)`,
    primary30: `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, 0.27)`,
  };
}
