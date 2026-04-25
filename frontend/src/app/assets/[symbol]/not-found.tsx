import Link from "next/link";

export default function AssetNotFound() {
  return (
    <main className="asset-shell">
      <section className="asset-hero">
        <p className="eyebrow">Not Found</p>
        <h1 className="asset-title">Unknown Symbol</h1>
        <p className="hero-subtitle">This symbol does not exist in the current asset universe.</p>
        <div style={{ marginTop: "1rem" }}>
          <Link href="/" className="asset-back">
            ← Back to Screener
          </Link>
        </div>
      </section>
    </main>
  );
}
