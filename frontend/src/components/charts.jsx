import { useMemo } from "react";
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
import { compactCurrency, money } from "../utils/format";

const tooltipStyle = { borderRadius: 12, border: "1px solid #dfe8e4" };

export function RevenueForecastChart({ forecast }) {
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
          <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={48} />
          <Tooltip formatter={(value) => money.format(value)} contentStyle={tooltipStyle} />
          <Legend iconType="circle" />
          <Area type="monotone" dataKey="actual" stroke="#199b72" fill="url(#actualFill)" strokeWidth={2.5} name="Actual" connectNulls={false} />
          <Line type="monotone" dataKey="predicted" stroke="#7d63df" strokeWidth={2.5} strokeDasharray="5 4" name="Forecast" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RegionRevenueChart({ regions }) {
  return (
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
  );
}

export function RevenueCadenceChart({ trends }) {
  return (
    <div className="chart-wrap compact-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={trends}>
          <CartesianGrid stroke="#e5ece9" vertical={false} />
          <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickFormatter={compactCurrency} tickLine={false} axisLine={false} width={48} />
          <Tooltip formatter={(value) => money.format(value)} />
          <Bar dataKey="revenue" fill="#75cdb2" radius={[5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
