export default function AssetDetailLoading() {
  return (
    <main className="asset-shell">
      <section className="asset-hero">
        <div className="skeleton-line w-160" />
        <div className="skeleton-line w-260" />
        <div className="skeleton-grid">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      </section>
      <section className="asset-panel">
        <div className="skeleton-line w-220" />
        <div className="skeleton-chart" />
      </section>
    </main>
  );
}
