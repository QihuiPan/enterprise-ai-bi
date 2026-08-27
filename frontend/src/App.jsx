import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  Database,
  FileUp,
  LayoutDashboard,
  LoaderCircle,
  RefreshCw,
  Send,
  Sparkles,
  Users,
  WalletCards,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat("en-US");

async function api(path, options) {
  const response = await fetch(`${API_URL}${path}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.join(" ") : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return body;
}

function MetricCard({ label, value, detail, icon: Icon, tone = "mint" }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon size={19} /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </article>
  );
}

function Panel({ eyebrow, title, action, className = "", children }) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function EmptyState({ onDemo, busy }) {
  return (
    <main className="empty-state">
      <div className="empty-orbit"><Database size={38} /></div>
      <span className="eyebrow">DATA WORKSPACE</span>
      <h1>Connect evidence before asking for insight.</h1>
      <p>
        Load the deterministic portfolio dataset or upload a validated CSV. The
        agents will only answer from records and model outputs that exist here.
      </p>
      <button className="primary-button" onClick={onDemo} disabled={busy}>
        {busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
        Load demo data
      </button>
    </main>
  );
}

export default function App() {
  const [dashboard, setDashboard] = useState(null);
  const [insight, setInsight] = useState(null);
  const [question, setQuestion] = useState("Why did revenue change in the latest month?");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const [kpis, trends, regions, forecast, segments, anomalies] = await Promise.all([
        api("/api/analytics/kpis"),
        api("/api/analytics/trends"),
        api("/api/analytics/breakdown/region"),
        api("/api/ml/forecast?horizon=3"),
        api("/api/ml/segments"),
        api("/api/ml/anomalies?limit=6"),
      ]);
      setDashboard({ kpis, trends, regions, forecast, segments, anomalies });
    } catch (requestError) {
      if (!String(requestError.message).includes("No sales data")) setError(requestError.message);
      setDashboard(null);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function loadDemo() {
    setBusy(true);
    setError("");
    try {
      await api("/api/data/demo", { method: "POST" });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    }
  }

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    setError("");
    try {
      await api("/api/data/upload", { method: "POST", body: form });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    } finally {
      event.target.value = "";
    }
  }

  async function ask(event) {
    event.preventDefault();
    if (question.trim().length < 5) return;
    setBusy(true);
    setError("");
    try {
      setInsight(await api("/api/insights/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  const chartData = useMemo(() => {
    if (!dashboard) return [];
    const history = dashboard.forecast.history.map((item) => ({ ...item, actual: item.revenue }));
    const future = dashboard.forecast.forecast.map((item) => ({
      ...item,
      predicted: item.revenue,
    }));
    return [...history, ...future];
  }, [dashboard]);

  if (!dashboard) {
    return (
      <div className="app-shell empty-shell">
        <nav className="brand"><BrainCircuit size={23} /><span>northstar<span>.ai</span></span></nav>
        {error && <div className="error-banner">{error}</div>}
        <EmptyState onDemo={loadDemo} busy={busy} />
      </div>
    );
  }

  const { kpis, trends, regions, segments, anomalies } = dashboard;
  const changePositive = kpis.month_over_month_change_pct >= 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <nav className="brand"><BrainCircuit size={23} /><span>northstar<span>.ai</span></span></nav>
        <div className="nav-group">
          <a className="nav-item active" href="#overview"><LayoutDashboard size={18} />Overview</a>
          <a className="nav-item" href="#intelligence"><Bot size={18} />AI intelligence</a>
          <a className="nav-item" href="#customers"><Users size={18} />Customers</a>
        </div>
        <div className="sidebar-note">
          <span><span className="status-dot" />Evidence connected</span>
          <p>{number.format(kpis.order_count)} validated orders</p>
        </div>
      </aside>

      <main className="workspace" id="overview">
        <header className="topbar">
          <div>
            <span className="eyebrow">COMMAND CENTER</span>
            <h1>Business pulse</h1>
            <p>{kpis.data_start} — {kpis.data_end}</p>
          </div>
          <div className="top-actions">
            <input ref={fileRef} type="file" accept=".csv" hidden onChange={upload} />
            <button className="secondary-button" onClick={() => fileRef.current?.click()}>
              <FileUp size={17} />Upload CSV
            </button>
            <button className="icon-button" aria-label="Refresh dashboard" onClick={refresh}>
              <RefreshCw className={busy ? "spin" : ""} size={18} />
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <section className="metric-grid">
          <MetricCard label="Revenue" value={money.format(kpis.total_revenue)} detail="Validated net sales" icon={WalletCards} />
          <MetricCard label="Orders" value={number.format(kpis.order_count)} detail={`${number.format(kpis.units_sold)} units sold`} icon={Activity} tone="blue" />
          <MetricCard label="Customers" value={number.format(kpis.customer_count)} detail={`${money.format(kpis.average_order_value)} avg. order`} icon={Users} tone="violet" />
          <MetricCard
            label="Latest month"
            value={`${Math.abs(kpis.month_over_month_change_pct).toFixed(1)}%`}
            detail={`${changePositive ? "Up" : "Down"} month over month`}
            icon={changePositive ? ArrowUpRight : ArrowDownRight}
            tone={changePositive ? "mint" : "coral"}
          />
        </section>

        <section className="dashboard-grid">
          <Panel eyebrow="REVENUE SIGNAL" title="Actuals and baseline forecast" className="wide-panel">
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#44d6a5" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#44d6a5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#dfe8e4" vertical={false} />
                  <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={30} />
                  <YAxis tickFormatter={(value) => `$${Math.round(value / 1000)}k`} tickLine={false} axisLine={false} width={48} />
                  <Tooltip formatter={(value) => money.format(value)} contentStyle={{ borderRadius: 12, border: "1px solid #dfe8e4" }} />
                  <Legend iconType="circle" />
                  <Area type="monotone" dataKey="actual" stroke="#199b72" fill="url(#actualFill)" strokeWidth={2.5} name="Actual" connectNulls={false} />
                  <Line type="monotone" dataKey="predicted" stroke="#7d63df" strokeWidth={2.5} strokeDasharray="5 4" name="Forecast" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="model-note">
              <span>MODEL QUALITY</span>
              Holdout MAE {money.format(dashboard.forecast.evaluation.mae)} · RMSE {money.format(dashboard.forecast.evaluation.rmse)}
            </div>
          </Panel>

          <Panel eyebrow="MARKET MIX" title="Revenue by region">
            <div className="chart-wrap compact-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={regions} layout="vertical" margin={{ left: 6, right: 18 }}>
                  <CartesianGrid stroke="#e5ece9" horizontal={false} />
                  <XAxis type="number" hide />
                  <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} width={55} />
                  <Tooltip formatter={(value) => money.format(value)} cursor={{ fill: "#eff5f2" }} />
                  <Bar dataKey="revenue" fill="#286f61" radius={[0, 7, 7, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel eyebrow="CUSTOMER INTELLIGENCE" title="RFM value segments" id="customers">
            <div className="segment-list">
              {segments.segments.map((segment, index) => (
                <div className="segment-row" key={segment.name}>
                  <span className={`segment-rank rank-${index + 1}`}>{index + 1}</span>
                  <div><strong>{segment.name}</strong><small>{segment.customers} customers · {segment.average_orders} avg orders</small></div>
                  <b>{money.format(segment.total_revenue)}</b>
                </div>
              ))}
            </div>
          </Panel>

          <Panel eyebrow="RISK RADAR" title="Transactions to review">
            <div className="anomaly-list">
              {anomalies.anomalies.slice(0, 4).map((item) => (
                <div className="anomaly-row" key={item.order_id}>
                  <span><Activity size={15} /></span>
                  <div><strong>{item.order_id}</strong><small>{item.region} · {item.category}</small></div>
                  <b>{money.format(item.revenue)}</b>
                </div>
              ))}
            </div>
            <p className="subtle-note">Flags show statistical unusualness, not confirmed errors.</p>
          </Panel>

          <Panel
            eyebrow="TWENTY-FOUR MONTH VIEW"
            title="Revenue cadence"
            className="wide-panel full-panel"
          >
            <div className="chart-wrap compact-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trends}>
                  <CartesianGrid stroke="#e5ece9" vertical={false} />
                  <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis tickFormatter={(value) => `$${Math.round(value / 1000)}k`} tickLine={false} axisLine={false} width={48} />
                  <Tooltip formatter={(value) => money.format(value)} />
                  <Bar dataKey="revenue" fill="#75cdb2" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </section>

        <section className="intelligence" id="intelligence">
          <div className="intelligence-copy">
            <span className="eyebrow light">GROUNDED MULTI-AGENT SYSTEM</span>
            <h2>Ask the business.<br />Inspect the evidence.</h2>
            <p>Every answer lists the analytical tools and source metrics used. No generated SQL reaches the database.</p>
            <form onSubmit={ask} className="question-form">
              <input value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Business question" />
              <button disabled={busy} aria-label="Ask agents">{busy ? <LoaderCircle className="spin" /> : <Send />}</button>
            </form>
          </div>
          <div className="insight-card">
            <div className="insight-heading"><span><Bot size={18} /></span><div><strong>Executive Agent</strong><small>{insight ? insight.agents_used.join(" + ") : "Ready for a grounded question"}</small></div></div>
            {insight ? (
              <>
                <p className="insight-answer">{insight.answer}</p>
                <div className="evidence-block">
                  <span>EVIDENCE TRAIL</span>
                  {insight.evidence.slice(0, 3).map((item) => (
                    <div key={`${item.source}-${item.metric}`}><Database size={13} /><b>{item.metric}</b><small>{item.source}</small></div>
                  ))}
                </div>
              </>
            ) : (
              <div className="insight-placeholder"><Sparkles size={24} /><p>Try “Forecast the next quarter” or “Which customers create the most value?”</p></div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
