import { Database, FileUp, LoaderCircle, Sparkles } from "lucide-react";

export function MetricCard({ label, value, detail, icon: Icon, tone = "mint" }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon size={19} /></div>
      <div><p>{label}</p><strong>{value}</strong><span>{detail}</span></div>
    </article>
  );
}

export function Panel({ eyebrow, title, action, className = "", id, children }) {
  return (
    <section className={`panel ${className}`} id={id}>
      <header className="panel-header">
        <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function EmptyState({ onDemo, onImport, busy }) {
  return (
    <main className="empty-state">
      <div className="empty-orbit"><Database size={38} /></div>
      <span className="eyebrow">DATA WORKSPACE</span>
      <h1>Connect evidence before asking for insight.</h1>
      <p>
        Load the deterministic portfolio dataset or import your own structured
        sales file. You can preview Excel, CSV, and TSV data, review suggested
        column matches, and activate it only after full validation.
      </p>
      <div className="empty-actions">
        <button className="primary-button" onClick={onDemo} disabled={busy}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
          Load demo data
        </button>
        <button className="secondary-button" onClick={onImport} disabled={busy}>
          <FileUp size={17} />Import sales data
        </button>
      </div>
    </main>
  );
}
