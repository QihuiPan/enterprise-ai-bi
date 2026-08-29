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
import {
  ProductRevenueChart,
  RevenueCadenceChart,
  RegionRevenueChart,
  RevenueForecastChart,
} from "./components/charts";
import { EmptyState, MetricCard, Panel } from "./components/common";
import { DashboardControls, RuntimePreferences } from "./components/DashboardControls";
import { IntelligenceSection } from "./components/IntelligenceSection";
import { AnomalyList, CustomerSegments } from "./components/lists";
import { useBusinessDashboard } from "./hooks/useBusinessDashboard";
import { formatCurrency, number } from "./utils/format";

function Brand() {
  return <nav className="brand"><BrainCircuit size={23} /><span>northstar<span>.ai</span></span></nav>;
}

function ModelUnavailable({ message }) {
  return (
    <div className="model-unavailable" role="status">
      <BrainCircuit size={24} />
      <strong>Model unavailable for this selection</strong>
      <span>{message || "Expand the filter window and try again."}</span>
    </div>
  );
}

export default function App() {
  const {
    dashboard,
    insight,
    filters,
    filterOptions,
    currency,
    apiKey,
    busy,
    error,
    refresh,
    loadDemo,
    upload,
    ask,
    applyFilters,
    resetFilters,
    setCurrency,
    saveApiKey,
  } = useBusinessDashboard();
  const fileRef = useRef(null);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (file) await upload(file);
    event.target.value = "";
  }

  if (!dashboard) {
    return (
      <div className="app-shell empty-shell">
        <header className="empty-header">
          <Brand />
          <RuntimePreferences
            currency={currency}
            apiKey={apiKey}
            busy={busy}
            onCurrencyChange={setCurrency}
            onSaveApiKey={saveApiKey}
            compact
          />
        </header>
        {error && <div className="error-banner">{error}</div>}
        <input ref={fileRef} type="file" accept=".csv" hidden onChange={handleUpload} />
        <EmptyState
          onDemo={loadDemo}
          onUpload={() => fileRef.current?.click()}
          busy={busy}
        />
      </div>
    );
  }

  const {
    kpis,
    trends,
    regions,
    products = [],
    forecast,
    segments,
    anomalies,
    model_errors: modelErrors = {},
  } = dashboard;
  const recordSemantics = kpis.record_semantics ?? {
    record_count_label: "Orders",
    entity_count_label: "Customers",
    average_value_label: "Average order value",
    average_frequency_label: "Average orders",
  };
  const changeAvailable = kpis.month_over_month_available
    && kpis.month_over_month_change_pct !== null;
  const changePositive = changeAvailable && kpis.month_over_month_change_pct >= 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="nav-group">
          <a className="nav-item active" href="#overview"><LayoutDashboard size={18} />Overview</a>
          <a className="nav-item" href="#intelligence"><Bot size={18} />AI intelligence</a>
          <a className="nav-item" href="#customers"><Users size={18} />{recordSemantics.entity_count_label}</a>
        </div>
        <div className="sidebar-note">
          <span><span className="status-dot" />Evidence connected</span>
          <p>{number.format(kpis.order_count)} validated {recordSemantics.record_count_label.toLowerCase()}</p>
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
            <button
              className="secondary-button"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
            >
              <FileUp size={17} />Upload CSV
            </button>
            <button className="icon-button" aria-label="Refresh dashboard" onClick={refresh} disabled={busy}>
              <RefreshCw className={busy ? "spin" : ""} size={18} />
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <DashboardControls
          filters={filters}
          options={filterOptions}
          currency={currency}
          apiKey={apiKey}
          busy={busy}
          onApply={applyFilters}
          onReset={resetFilters}
          onCurrencyChange={setCurrency}
          onSaveApiKey={saveApiKey}
        />

        <section className="metric-grid">
          <MetricCard label="Revenue" value={formatCurrency(kpis.total_revenue, currency)} detail="Validated net sales" icon={WalletCards} />
          <MetricCard label={recordSemantics.record_count_label} value={number.format(kpis.order_count)} detail={`${number.format(kpis.units_sold)} units sold`} icon={Activity} tone="blue" />
          <MetricCard label={recordSemantics.entity_count_label} value={number.format(kpis.customer_count)} detail={`${formatCurrency(kpis.average_order_value, currency)} ${recordSemantics.average_value_label.toLowerCase()}`} icon={Users} tone="violet" />
          <MetricCard
            label="Latest month"
            value={changeAvailable ? `${Math.abs(kpis.month_over_month_change_pct).toFixed(1)}%` : "—"}
            detail={changeAvailable
              ? `${changePositive ? "Up" : "Down"} month over month`
              : kpis.month_over_month_status === "zero_baseline"
                ? "Previous month was zero"
                : kpis.month_over_month_status === "non_consecutive_periods"
                  ? "Months are not consecutive"
                  : kpis.month_over_month_status === "partial_periods"
                    ? "Observed months are incomplete"
                    : "Not enough history"}
            icon={changeAvailable ? (changePositive ? ArrowUpRight : ArrowDownRight) : Activity}
            tone={changeAvailable ? (changePositive ? "mint" : "coral") : "blue"}
          />
        </section>

        <section className="dashboard-grid">
          <Panel eyebrow="REVENUE SIGNAL" title="Actuals and baseline forecast" className="wide-panel">
            {forecast ? (
              <>
                <RevenueForecastChart forecast={forecast} currency={currency} />
                <div className="model-note">
                  <span>MODEL QUALITY</span>
                  Holdout MAE {formatCurrency(forecast.evaluation.mae, currency)} · RMSE {formatCurrency(forecast.evaluation.rmse, currency)}
                  {forecast.excluded_periods?.length > 0
                    && ` · Excluded incomplete ${forecast.excluded_periods.map((item) => item.period).join(", ")}`}
                </div>
              </>
            ) : <ModelUnavailable message={modelErrors.forecast} />}
          </Panel>

          <Panel eyebrow="MARKET MIX" title="Revenue by region">
            <RegionRevenueChart
              regions={regions}
              currency={currency}
              selectedRegion={filters.region}
              disabled={busy}
              onSelectRegion={(region) => applyFilters({
                ...filters,
                region: filters.region === region ? "" : region,
              })}
            />
          </Panel>

          <Panel eyebrow="PRODUCT PERFORMANCE" title="Top products by revenue" className="full-panel">
            <ProductRevenueChart
              products={products}
              currency={currency}
              recordCountLabel={recordSemantics.record_count_label}
            />
          </Panel>

          <Panel eyebrow={`${recordSemantics.entity_count_label.toUpperCase()} INTELLIGENCE`} title="RFM value segments" id="customers">
            {segments
              ? (
                <CustomerSegments
                  segments={segments.segments}
                  currency={currency}
                  entityLabel={recordSemantics.entity_count_label}
                  frequencyLabel={recordSemantics.average_frequency_label}
                />
              )
              : <ModelUnavailable message={modelErrors.segments} />}
          </Panel>

          <Panel eyebrow="RISK RADAR" title="Records to review">
            {anomalies ? (
              <>
                <AnomalyList anomalies={anomalies.anomalies} currency={currency} />
                <p className="subtle-note">Flags show statistical unusualness, not confirmed errors.</p>
              </>
            ) : <ModelUnavailable message={modelErrors.anomalies} />}
          </Panel>

          <Panel eyebrow="MONTHLY REVENUE VIEW" title="Revenue cadence" className="wide-panel full-panel">
            <RevenueCadenceChart trends={trends} currency={currency} />
          </Panel>
        </section>

        <IntelligenceSection insight={insight} busy={busy} currency={currency} onAsk={ask} />
      </main>
    </div>
  );
}
