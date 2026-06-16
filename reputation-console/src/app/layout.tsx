import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Reputation Console",
  description: "See and manage AI reputation: audits, gaps, content, rankings, timeline.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      {/* suppressHydrationWarning: browser extensions (AI agents, etc.) inject attributes on
          <html>/<body> before React hydrates, causing a harmless dev-only mismatch warning. */}
      <body className="flex min-h-full flex-col bg-gray-50 text-gray-900" suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
