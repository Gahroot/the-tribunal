import type { Metadata } from "next";
import { HeroSection } from "@/components/landing/hero-section";
import { PainSection } from "@/components/landing/pain-section";
import { StatsSection } from "@/components/landing/stats-section";
import { SolutionSection } from "@/components/landing/solution-section";
import { HowItWorksSection } from "@/components/landing/how-it-works-section";
import { ResultsSection } from "@/components/landing/results-section";
import { UseCasesSection } from "@/components/landing/use-cases-section";
import { FinalCtaSection } from "@/components/landing/final-cta-section";

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
