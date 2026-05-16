import type { Metadata } from "next";

import { FinalCtaSection } from "@/components/landing/final-cta-section";
import { HeroSection } from "@/components/landing/hero-section";
import { HowItWorksSection } from "@/components/landing/how-it-works-section";
import { PainSection } from "@/components/landing/pain-section";
import { ResultsSection } from "@/components/landing/results-section";
import { SolutionSection } from "@/components/landing/solution-section";
import { StatsSection } from "@/components/landing/stats-section";
import { UseCasesSection } from "@/components/landing/use-cases-section";

export const metadata: Metadata = {
  title: "AI Database Reactivation | PRESTYJ",
  description:
    "Recover lost revenue from your existing database. AI-powered calls and texts that turn dormant leads into closed deals.",
  openGraph: {
    title: "AI Database Reactivation | PRESTYJ",
    description:
      "Recover lost revenue from your existing database. AI-powered calls and texts that turn dormant leads into closed deals.",
    type: "website",
  },
};

export default function LandingPage() {
  return (
    <main>
      <HeroSection />
      <PainSection />
      <StatsSection />
      <SolutionSection />
      <HowItWorksSection />
      <ResultsSection />
      <UseCasesSection />
      <FinalCtaSection />
    </main>
  );
}
