import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Market Screener",
  description: "Personal dashboard for market screening and alerting",
};

type RootLayoutProps = {
  children: React.ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <header className="top-nav">
          <div className="top-nav-inner">
            <Link href="/" className="top-nav-brand">
              Market Screener
            </Link>
            <nav className="top-nav-links" aria-label="Primary navigation">
              <Link href="/" className="top-nav-link">
                Screener
              </Link>
              <Link href="/alerts" className="top-nav-link">
                Alerts
              </Link>
            </nav>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
