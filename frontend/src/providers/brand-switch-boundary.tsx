"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ContactStoreContext, createContactStore } from "@/lib/contact-store";

/** Workspace is the persisted brand container, not an organization (ORG-001). */
export function brandSwitchDestination(pathname: string, search: string): string {
  // RF-027: contact backlog links are brand-owned, like contact detail routes.
  if (pathname === "/nudges" && new URLSearchParams(search).has("contact_id")) return "/nudges";
  if (pathname.startsWith("/contacts/") || pathname === "/contacts") return "/contacts";
  if (pathname === "/conversations" || pathname.startsWith("/conversations/"))
    return "/conversations";
  return search ? `${pathname}?${search}` : pathname;
}

function BrandSession({
  workspaceId,
  children,
}: {
  workspaceId: string | null;
  children: ReactNode;
}) {
  const [store] = useState(() => createContactStore(workspaceId ?? undefined));
  return <ContactStoreContext value={store}>{children}</ContactStoreContext>;
}

/**
 * Remount brand-owned UI state (drafts, senders, forms, row selections). Old
 * requests may finish on the server, but their closures retain detached local
 * state/store instances. A switch-back creates a new session, never revives one.
 * Theme/auth/query providers and user-wide preferences live above this boundary.
 */
export function BrandSwitchBoundary({
  workspaceId,
  switchDestination = null,
  children,
}: {
  workspaceId: string | null;
  switchDestination?: string | null;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const router = useRouter();
  const location = search ? `${pathname}?${search}` : pathname;
  const [previousId, setPreviousId] = useState(workspaceId);
  const [destination, setDestination] = useState<string | null>(null);

  // Adjust during render, not in an effect: no old panel paints or starts a
  // new-brand fetch using the old route while Next's replace is outstanding.
  if (previousId !== workspaceId) {
    setPreviousId(workspaceId);
    setDestination(
      switchDestination ?? (previousId ? brandSwitchDestination(pathname, search) : null),
    );
  }

  if (destination && destination === location) setDestination(null);

  useEffect(() => {
    if (destination && destination !== location) router.replace(destination, { scroll: false });
  }, [destination, location, router]);

  if (destination && destination !== location) return null;
  return (
    <BrandSession key={workspaceId ?? "no-brand"} workspaceId={workspaceId}>
      {children}
    </BrandSession>
  );
}
