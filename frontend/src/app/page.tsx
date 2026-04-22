import type { CSSProperties } from "react";

const cardStyle: CSSProperties = {
  maxWidth: 900,
  margin: "64px auto",
  padding: "24px",
  borderRadius: 16,
  background: "#ffffff",
  boxShadow: "0 10px 30px rgba(15, 23, 42, 0.08)",
};

const headingStyle: CSSProperties = {
  margin: 0,
  fontSize: "2rem",
  letterSpacing: "-0.02em",
};

const subtitleStyle: CSSProperties = {
  marginTop: 10,
  color: "#475467",
  lineHeight: 1.5,
};

const listStyle: CSSProperties = {
  marginTop: 24,
  paddingLeft: 20,
  lineHeight: 1.8,
};

export default function HomePage() {
  return (
    <main style={{ padding: "0 16px" }}>
      <section style={cardStyle}>
        <h1 style={headingStyle}>Market Screener Frontend</h1>
        <p style={subtitleStyle}>
          Day 12 scaffold is ready. Next step is wiring screener APIs and rendering the first ranked
          symbols table.
        </p>
        <ul style={listStyle}>
          <li>Stack: Next.js App Router + TypeScript strict mode</li>
          <li>Ready scripts: dev, build, start, lint, typecheck</li>
          <li>Target: personal dashboard for swing decisions and alert review</li>
        </ul>
      </section>
    </main>
  );
}
