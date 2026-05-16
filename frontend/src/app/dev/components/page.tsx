import { notFound } from "next/navigation";

import { ComponentsGallery } from "./components-gallery";

/**
 * Dev-only living style guide for shared UI primitives.
 *
 * Visit http://localhost:3000/dev/components in development to see every
 * `@/components/ui/*` primitive — including `PageLoadingState`,
 * `PageErrorState`, and `PageEmptyState` — rendered side-by-side with the
 * canonical usage. Use this as a discovery surface before reinventing a
 * loading/error/empty UI by hand.
 *
 * Hidden in production by returning a 404 from this server component, so the
 * route is unreachable on deployed builds even though the file is in `app/`.
 */
export default function DevComponentsPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <ComponentsGallery />;
}

export const metadata = {
  title: "Components — Dev Style Guide",
  robots: { index: false, follow: false },
};
