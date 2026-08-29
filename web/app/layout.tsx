import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GridPulse AI — Grid Resilience for Extreme Heat",
  description:
    "GridPulse AI models heat-driven grid failure risk zone-by-zone and recommends budget-optimal resilience actions, with guardrailed AI explanations for every decision.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
