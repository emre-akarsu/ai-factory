import type { Metadata } from "next";
import { Fraunces, Inter } from "next/font/google";
import Link from "next/link";
import { brand } from "@/lib/brand";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const fraunces = Fraunces({ variable: "--font-fraunces", subsets: ["latin"], axes: ["opsz"] });

export const metadata: Metadata = {
  title: { default: `${brand.name}: ${brand.tagline}`, template: `%s | ${brand.name}` },
  description: "Hire AI employees that do real work for your business, with approvals and an audit trail.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable} antialiased`}>
      <body className="min-h-screen flex flex-col font-sans">
        <header className="sticky top-0 z-40 border-b border-line/70 bg-background/85 backdrop-blur">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
            <Link href="/" className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
              <span className="grid size-8 place-items-center rounded-lg bg-brand text-sm text-brand-ink">AI</span>
              {brand.name}
            </Link>
            <nav className="flex items-center gap-6 text-sm text-muted">
              <Link href="/" className="hover:text-foreground">Marketplace</Link>
              <Link href="/employees/restaurant-purchasing#pricing" className="hidden hover:text-foreground sm:block">Pricing</Link>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line py-10 text-sm text-muted">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 sm:flex-row sm:justify-between">
            <span>© {new Date().getFullYear()} {brand.name}</span>
            <span>{brand.tagline}</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
