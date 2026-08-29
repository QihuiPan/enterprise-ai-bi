import { request } from "./client";

export const EMPTY_FILTERS = Object.freeze({
  start_date: "",
  end_date: "",
  region: "",
  category: "",
  product: "",
});

export function normalizeFilters(filters = EMPTY_FILTERS) {
  return Object.fromEntries(
    Object.keys(EMPTY_FILTERS).map((key) => [key, String(filters[key] ?? "").trim()]),
  );
}

export function withFilterQuery(path, filters = EMPTY_FILTERS) {
  const [pathname, existingQuery = ""] = path.split("?");
  const query = new URLSearchParams(existingQuery);
  Object.entries(normalizeFilters(filters)).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  const serialized = query.toString();
  return serialized ? `${pathname}?${serialized}` : pathname;
}

export async function fetchDashboard(filters = EMPTY_FILTERS) {
  return request(withFilterQuery("/api/dashboard", filters));
}

export function fetchFilterOptions() {
  return request("/api/analytics/filter-options");
}

export function loadDemoData() {
  return request("/api/data/demo", { method: "POST" });
}

export function uploadSalesCsv(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/data/upload", { method: "POST", body });
}

export function queryInsight(question, filters = EMPTY_FILTERS, currency = "USD") {
  return request(withFilterQuery("/api/insights/query", filters), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, currency }),
  });
}
