import { request } from "./client";

const DASHBOARD_REQUESTS = {
  kpis: "/api/analytics/kpis",
  trends: "/api/analytics/trends",
  regions: "/api/analytics/breakdown/region",
  forecast: "/api/ml/forecast?horizon=3",
  segments: "/api/ml/segments",
  anomalies: "/api/ml/anomalies?limit=6",
};

export async function fetchDashboard() {
  const entries = await Promise.all(
    Object.entries(DASHBOARD_REQUESTS).map(async ([key, path]) => [key, await request(path)]),
  );
  return Object.fromEntries(entries);
}

export function loadDemoData() {
  return request("/api/data/demo", { method: "POST" });
}

export function uploadSalesCsv(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/data/upload", { method: "POST", body });
}

export function queryInsight(question) {
  return request("/api/insights/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}
