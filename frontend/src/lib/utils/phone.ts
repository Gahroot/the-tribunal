// Phone number formatting helpers. Centralised so display formatting stays
// consistent across the app. Input is assumed to be a US-style number; non-US
// or unrecognised shapes are returned verbatim.

/**
 * Format a US phone number for display.
 *
 * - 10 digits        → "(XXX) XXX-XXXX"
 * - 11 digits, "1…"  → "+1 (XXX) XXX-XXXX"
 * - empty / nullish  → ""
 * - anything else    → returned unchanged
 */
export function formatPhoneNumber(phone?: string | null): string {
  if (!phone) return "";
  const cleaned = phone.replace(/\D/g, "");
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  if (cleaned.length === 11 && cleaned[0] === "1") {
    return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
  }
  return phone;
}

export function normalizePhoneForComparison(phone?: string | null): string {
  if (!phone) return "";
  const cleaned = phone.replace(/\D/g, "");
  if (cleaned.length === 10) return `+1${cleaned}`;
  if (cleaned.length === 11 && cleaned[0] === "1") return `+${cleaned}`;
  return phone.trim().toLowerCase();
}
