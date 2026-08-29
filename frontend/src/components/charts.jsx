import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCompactCurrency, formatCurrency, number } from "../utils/format";

const tooltipStyle = { borderRadius: 12, border: "1px solid #dfe8e4" };
const MAX_INSIGHT_LINE_POINTS = 24;
const MAX_INSIGHT_BAR_POINTS = 12;

function isCurrencyMetric(metric) {
  return metric === "revenue" || metric === "average_order_value";
}

function insightValue(value, metric, currency) {
  return isCurrencyMetric(metric)
    ? formatCurrency(value, currency)
    : number.format(Number(value) || 0);
}

function compactInsightValue(value, metric, currency) {
  return isCurrencyMetric(metric)
    ? formatCompactCurrency(value, currency)
    : number.format(Number(value) || 0);
}

export function InsightVisualization({ chart, currency }) {
  if (!chart?.data?.length) return null;

  const limit = chart.type === "line" ? MAX_INSIGHT_LINE_POINTS : MAX_INSIGHT_BAR_POINTS;
  const data = chart.type === "line" ? chart.data.slice(-limit) : chart.data.slice(0, limit);
  const sourceCount = chart.total_results ?? chart.total_points ?? chart.data.length;
  const hiddenCount = Math.max(0, sourceCount - data.length);
  const valueFormatter = (value) => insightValue(value, chart.y_key, currency);

  return (
    <section className="insight-visualization" aria-label={chart.title}>
      <div className="insight-chart-heading">
        <strong>{chart.title}</strong>
        {hiddenCount > 0 && <small>Showing {data.length} of {sourceCount} results</small>}
      </div>
      {chart.type === "line" && (
        <div className="insight-chart-wrap" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#dfe8e4" vertical={false} />
              <XAxis dataKey={chart.x_key} tickLine={false} axisLine={false} minTickGap={22} />
              <YAxis
                tickFormatter={(value) => compactInsightValue(value, chart.y_key, currency)}
                tickLine={false}
                axisLine={false}
                width={54}
              />
              <Tooltip formatter={valueFormatter} contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey={chart.y_key} stroke="#199b72" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {chart.type === "bar" && (
        <div className="insight-chart-wrap insight-bar-chart" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 5, right: 12, bottom: 0, left: 10 }}>
              <CartesianGrid stroke="#dfe8e4" horizontal={false} />
              <XAxis type="number" hide />
              <YAxis dataKey={chart.x_key} type="category" tickLine={false} axisLine={false} width={86} />
              <Tooltip formatter={valueFormatter} contentStyle={tooltipStyle} />
              <Bar dataKey={chart.y_key} fill="#286f61" radius={[0, 6, 6, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {chart.type === "metric" && (
        <strong className="insight-metric">{valueFormatter(data[0][chart.y_key])}</strong>
      )}
      <details className="accessible-chart-data">
        <summary>View chart data</summary>
        <div className="insight-table-scroll">
          <table>
            <thead><tr><th scope="col">{chart.x_key.replaceAll("_", " ")}</th><th scope="col">{chart.y_key.replaceAll("_", " ")}</th></tr></thead>
            <tbody>
              {data.map((item, index) => (
                <tr key={`${item[chart.x_key]}-${index}`}>
                  <th scope="row">{item[chart.x_key]}</th>
                  <td>{valueFormatter(item[chart.y_key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export function RevenueForecastChart({ forecast, currency }) {
  const chartData = useMemo(() => [
    ...forecast.history.map((item) => ({ ...item, actual: item.revenue })),
    ...forecast.forecast.map((item) => ({ ...item, predicted: item.revenue })),
  ], [forecast]);

  return (
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
          <YAxis tickFormatter={(value) => formatCompactCurrency(value, currency)} tickLine={false} axisLine={false} width={54} />
          <Tooltip formatter={(value) => formatCurrency(value, currency)} contentStyle={tooltipStyle} />
          <Legend iconType="circle" />
          <Area type="monotone" dataKey="actual" stroke="#199b72" fill="url(#actualFill)" strokeWidth={2.5} name="Actual" connectNulls={false} />
          <Line type="monotone" dataKey="predicted" stroke="#7d63df" strokeWidth={2.5} strokeDasharray="5 4" name="Forecast" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RegionRevenueChart({ regions, currency, selectedRegion, onSelectRegion, disabled = false }) {
  function selectRegion(entry) {
    const name = entry?.name ?? entry?.payload?.name;
    if (name && !disabled) onSelectRegion(name);
  }

  return (
    <div className="chart-stack">
      <div className="chart-wrap compact-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={regions} layout="vertical" margin={{ left: 6, right: 18 }}>
            <CartesianGrid stroke="#e5ece9" horizontal={false} />
            <XAxis type="number" hide />
            <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} width={55} />
            <Tooltip formatter={(value) => formatCurrency(value, currency)} cursor={{ fill: "#eff5f2" }} />
            <Bar
              dataKey="revenue"
              fill="#286f61"
              radius={[0, 7, 7, 0]}
              barSize={16}
              cursor={disabled ? "default" : "pointer"}
              onClick={disabled ? undefined : selectRegion}
            >
              {regions.map((region) => (
                <Cell
                  key={region.name}
                  fill={!selectedRegion || selectedRegion === region.name ? "#286f61" : "#aac5bd"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-hint">Select a bar to {selectedRegion ? "change or clear" : "drill into"} a region. The region menu provides the keyboard-accessible equivalent.</p>
    </div>
  );
}

export function ProductRevenueChart({ products, currency, recordCountLabel }) {
  const data = products.slice(0, 10);
  return (
    <div className="chart-stack">
      <div className="chart-wrap product-chart" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 12, right: 22 }}>
            <CartesianGrid stroke="#e5ece9" horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCompactCurrency(value, currency)} tickLine={false} axisLine={false} />
            <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} width={105} />
            <Tooltip formatter={(value) => formatCurrency(value, currency)} cursor={{ fill: "#eff5f2" }} />
            <Bar dataKey="revenue" fill="#7d63df" radius={[0, 7, 7, 0]} barSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="accessible-chart-data">
        <summary>View ranked product data</summary>
        <div className="insight-table-scroll">
          <table>
            <thead><tr><th scope="col">Product</th><th scope="col">Revenue</th><th scope="col">Share</th><th scope="col">{recordCountLabel}</th></tr></thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.name}>
                  <th scope="row">{item.name}</th>
                  <td>{formatCurrency(item.revenue, currency)}</td>
                  <td>{item.revenue_share_pct.toFixed(1)}%</td>
                  <td>{number.format(item.orders)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function RevenueCadenceChart({ trends, currency }) {
  return (
    <div className="chart-wrap compact-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={trends}>
          <CartesianGrid stroke="#e5ece9" vertical={false} />
          <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickFormatter={(value) => formatCompactCurrency(value, currency)} tickLine={false} axisLine={false} width={54} />
          <Tooltip formatter={(value) => formatCurrency(value, currency)} />
          <Bar dataKey="revenue" fill="#75cdb2" radius={[5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
