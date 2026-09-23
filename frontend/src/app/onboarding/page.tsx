import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { SetupChecklist } from "@/components/onboarding/setup-checklist";

/**
 * Persistent "Finish setup" checklist — the first-run onboarding experience.
 *
 * This route used to be a force-redirected wizard; it is now the checklist
 * (what the sidebar's `setupNavItem` points at). Every step checks live
 * workspace state and links straight to its own screen, with visible progress
 * and a completion celebration. The step-by-step wizard remains available at
 * /onboarding/wizard as a guided alternative.
 */
export default function OnboardingPage() {
  return (
    <AppSidebar>
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <h1 className="sr-only">Finish setup</h1>
        <SetupChecklist />
        <p className="mt-5 text-center text-sm text-muted-foreground">
          Prefer a guided walkthrough?{" "}
          <Link
            href="/onboarding/wizard"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Start the setup wizard
            <ArrowRight className="ml-1 inline size-3.5" aria-hidden="true" />
          </Link>
        </p>
      </div>
    </AppSidebar>
  );
}
