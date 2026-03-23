import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import { Providers } from "@/providers/providers";
import { Spotlight } from "@/components/effects/spotlight";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI CRM - Unified Customer Communications",
  description:
    "AI-powered CRM for managing customer relationships through voice, SMS, and email",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${manrope.variable} font-sans antialiased relative min-h-screen`}
      >
        <Providers>
          <Spotlight className="fixed" />
          <div className="relative z-10">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
