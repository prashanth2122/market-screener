import Link from "next/link";

import AlertPreferencesClient from "@/app/alerts/AlertPreferencesClient";

export const dynamic = "force-dynamic";

export default function AlertsPage() {
  return (
    <main className="screener-shell">
      <section className="hero-panel">
        <p className="eyebrow">Day 80 Frontend Delivery</p>
        <h1 className="hero-title">Alert Preferences</h1>
        <p className="hero-subtitle">
          Tune alert rules (signals, thresholds, cooldown, daily cap) and generate `.env` overrides
          for dispatch jobs.
        </p>
        <div style={{ marginTop: "0.9rem" }}>
          <Link href="/" className="asset-back">
            ← Back to Screener
          </Link>
        </div>
      </section>

      <section className="table-panel">
        <div className="table-header">
          <div>
            <h2>Preferences</h2>
            <p>Stored locally in your browser. Backend reads from `.env`.</p>
          </div>
          <span className="status-pill">Local Settings</span>
        </div>

        <AlertPreferencesClient />
      </section>
    </main>
  );
}
