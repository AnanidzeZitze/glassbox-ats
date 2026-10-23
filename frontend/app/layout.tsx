import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Glass-Box ATS Simulator & Optimization Studio",
  description:
    "100% deterministic clean-room ATS parser X-Ray, Stage 5 platform schema emulators, 5-component scoring engine, and zero-hallucination tailoring studio.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
