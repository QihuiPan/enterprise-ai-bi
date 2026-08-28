import { useRef } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  FileUp,
  LayoutDashboard,
  RefreshCw,
  Users,
  WalletCards,
} from "lucide-react";
import { RevenueCadenceChart, RegionRevenueChart, RevenueForecastChart } from "./components/charts";
import { EmptyState, MetricCard, Panel } from "./components/common";
import { IntelligenceSection } from "./components/IntelligenceSection";
import { AnomalyList, CustomerSegments } from "./components/lists";
import { useBusinessDashboard } from "./hooks/useBusinessDashboard";
import { money, number } from "./utils/format";

function Brand() {
  return <nav className="brand"><BrainCircuit size={23} /><span>northstar<span>.ai</span></span></nav>;
}

export default function App() {
  const { dashboard, insight, busy, error, refresh, loadDemo, upload, ask } = useBusinessDashboard();
  const fileRef = useRef(null);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (file) await upload(file);
    event.target.value = "";
  }

  if (!dashboard) {
    return (
      <div className="app-shell empty-shell">
        <Brand />
        {error && <div className="error-banner">{error}</div>}
        <EmptyState onDemo={loadDemo} busy={busy} />
      </div>
    );
  }

  const { kpis, trends, regions, forecast, segments, anomalies } = dashboard;
  const changePositive = kpis.month_over_month_change_pct >= 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
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
            <input ref={fileRef} type="file" accept=".csv" hidden onChange={handleUpload} />
            <button className="secondary-button" onClick={() => fileRef.current?.click()}>
              <FileUp size={17} />Upload CSV
            </button>
            <button className="icon-button" aria-label="Refresh dashboard" onClick={refresh} disabled={busy}>
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
            <RevenueForecastChart forecast={forecast} />
            <div className="model-note">
              <span>MODEL QUALITY</span>
              Holdout MAE {money.format(forecast.evaluation.mae)} · RMSE {money.format(forecast.evaluation.rmse)}
            </div>
          </Panel>

          <Panel eyebrow="MARKET MIX" title="Revenue by region">
            <RegionRevenueChart regions={regions} />
          </Panel>

          <Panel eyebrow="CUSTOMER INTELLIGENCE" title="RFM value segments" id="customers">
            <CustomerSegments segments={segments.segments} />
          </Panel>

          <Panel eyebrow="RISK RADAR" title="Transactions to review">
            <AnomalyList anomalies={anomalies.anomalies} />
            <p className="subtle-note">Flags show statistical unusualness, not confirmed errors.</p>
          </Panel>

          <Panel eyebrow="TWENTY-FOUR MONTH VIEW" title="Revenue cadence" className="wide-panel full-panel">
            <RevenueCadenceChart trends={trends} />
          </Panel>
        </section>

        <IntelligenceSection insight={insight} busy={busy} onAsk={ask} />
      </main>
    </div>
  );
}
