import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { MobileNav } from "@/components/layout/MobileNav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PermitSignal — Commercial Intelligence Platform",
  description:
    "Government-project intelligence from planning packets: applicant/owner/company identification, friction history, upcoming events, opportunity scoring, and verified public contact intelligence.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-background text-foreground lg:flex-row">
        <Suspense fallback={<div className="hidden w-[236px] shrink-0 border-r border-border-subtle bg-background-elevated lg:block" />}>
          <Sidebar />
        </Suspense>
        <div className="flex min-h-full flex-1 flex-col">
          <MobileNav />
          <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10">
            <div className="mx-auto w-full max-w-[1400px]">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
