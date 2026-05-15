// Avatar initials helpers. Centralised so avatars across contacts, calls, and
// team surfaces all derive initials the same way.

interface NameParts {
  first_name?: string | null;
  last_name?: string | null;
}

/**
 * Initials from a contact-shaped object with `first_name` / `last_name`.
 * Falls back to "?" when both are blank.
 */
export function getContactInitials(contact: NameParts): string {
  const first = contact.first_name?.[0] ?? "";
  const last = contact.last_name?.[0] ?? "";
  return (first + last).toUpperCase() || "?";
}

/**
 * Initials from a free-form display name (e.g. "Jane Doe" → "JD").
 *
 * - Two or more words → first letter of the first two words.
 * - Single word       → first two characters of that word.
 * - Empty / nullish   → `fallback` (default `"??"`); if `fallback` looks like
 *                       an email or arbitrary string, its first two chars are
 *                       used so callers can pass an email as the fallback.
 */
export function getInitialsFromName(
  name?: string | null,
  fallback: string = "??",
): string {
  const trimmed = name?.trim();
  if (trimmed) {
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return trimmed.slice(0, 2).toUpperCase();
  }
  return fallback.slice(0, 2).toUpperCase() || "??";
}
