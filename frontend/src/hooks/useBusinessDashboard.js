import { useCallback, useEffect, useRef, useState } from "react";
import {
  EMPTY_FILTERS,
  fetchDashboard,
  fetchFilterOptions,
  loadDemoData,
  normalizeFilters,
  queryInsight,
  uploadSalesCsv,
} from "../api/dashboard";
import { getApiKey, storeApiKey } from "../api/client";

const CURRENCY_STORAGE_KEY = "enterprise-ai-bi.currency";

function initialCurrency() {
  try {
    return window.sessionStorage.getItem(CURRENCY_STORAGE_KEY) === "GBP" ? "GBP" : "USD";
  } catch {
    return "USD";
  }
}

export function useBusinessDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [insight, setInsight] = useState(null);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const [filterOptions, setFilterOptions] = useState(null);
  const [currency, setCurrencyState] = useState(initialCurrency);
  const [apiKey, setApiKeyState] = useState(getApiKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const filtersRef = useRef(filters);
  const committedFiltersRef = useRef(filters);
  const filterOptionsRef = useRef(null);
  const pendingOperationsRef = useRef(0);
  const operationGenerationRef = useRef(0);
  const dashboardGenerationRef = useRef(0);
  const insightGenerationRef = useRef(0);

  const run = useCallback(async (operation, clearDashboardOnError = false) => {
    const operationGeneration = operationGenerationRef.current + 1;
    operationGenerationRef.current = operationGeneration;
    pendingOperationsRef.current += 1;
    setBusy(true);
    setError("");
    try {
      return await operation();
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : String(requestError);
      if (operationGenerationRef.current === operationGeneration) {
        setError(message);
        if (clearDashboardOnError) setDashboard(null);
      }
      return null;
    } finally {
      pendingOperationsRef.current -= 1;
      if (pendingOperationsRef.current === 0) setBusy(false);
    }
  }, []);

  const invalidateInsight = useCallback(() => {
    insightGenerationRef.current += 1;
    setInsight(null);
  }, []);

  const hydrate = useCallback(
    async (selectedFilters, reloadOptions = false) => {
      const dashboardGeneration = dashboardGenerationRef.current + 1;
      dashboardGenerationRef.current = dashboardGeneration;
      const nextDashboard = await run(async () => {
        const dashboardRequest = fetchDashboard(selectedFilters);
        const optionsRequest = reloadOptions || !filterOptionsRef.current
          ? fetchFilterOptions()
          : Promise.resolve(filterOptionsRef.current);
        const [dashboardResult, nextOptions] = await Promise.all([
          dashboardRequest,
          optionsRequest,
        ]);
        if (dashboardGenerationRef.current === dashboardGeneration) {
          setDashboard(dashboardResult);
          committedFiltersRef.current = selectedFilters;
          filterOptionsRef.current = nextOptions;
          setFilterOptions(nextOptions);
        }
        return dashboardResult;
      });
      return {
        dashboard: nextDashboard,
        current: dashboardGenerationRef.current === dashboardGeneration,
      };
    },
    [run],
  );

  const refresh = useCallback(
    async () => (await hydrate(filtersRef.current)).dashboard,
    [hydrate],
  );

  const applyFilters = useCallback(
    (nextFilters) => {
      const previousFilters = committedFiltersRef.current;
      const normalized = normalizeFilters(nextFilters);
      filtersRef.current = normalized;
      setFilters(normalized);
      invalidateInsight();
      return hydrate(normalized).then((outcome) => {
        if (outcome.current && !outcome.dashboard) {
          filtersRef.current = previousFilters;
          setFilters(previousFilters);
        }
        return outcome.dashboard;
      });
    },
    [hydrate, invalidateInsight],
  );

  const resetFilters = useCallback(
    () => applyFilters(EMPTY_FILTERS),
    [applyFilters],
  );

  const replaceData = useCallback(
    (replaceOperation) => {
      dashboardGenerationRef.current += 1;
      invalidateInsight();
      return run(async () => {
        await replaceOperation();
        const dashboardGeneration = dashboardGenerationRef.current + 1;
        dashboardGenerationRef.current = dashboardGeneration;
        setDashboard(null);

        try {
          const nextFilters = { ...EMPTY_FILTERS };
          filtersRef.current = nextFilters;
          setFilters(nextFilters);
          const [nextDashboard, nextOptions] = await Promise.all([
            fetchDashboard(nextFilters),
            fetchFilterOptions(),
          ]);
          if (dashboardGenerationRef.current === dashboardGeneration) {
            setDashboard(nextDashboard);
            committedFiltersRef.current = nextFilters;
            filterOptionsRef.current = nextOptions;
            setFilterOptions(nextOptions);
          }
          return nextDashboard;
        } catch (refreshError) {
          const message = refreshError instanceof Error
            ? refreshError.message
            : String(refreshError);
          throw new Error(`Data was replaced, but dashboard refresh failed: ${message}`);
        }
      });
    },
    [invalidateInsight, run],
  );

  const loadDemo = useCallback(
    () => replaceData(loadDemoData),
    [replaceData],
  );

  const upload = useCallback(
    (file) => replaceData(() => uploadSalesCsv(file)),
    [replaceData],
  );

  const ask = useCallback(
    (question) => {
      const insightGeneration = insightGenerationRef.current + 1;
      insightGenerationRef.current = insightGeneration;
      setInsight(null);
      const selectedFilters = filtersRef.current;
      const selectedCurrency = currency;
      return run(async () => {
        const result = await queryInsight(question, selectedFilters, selectedCurrency);
        if (insightGenerationRef.current === insightGeneration) setInsight(result);
        return result;
      });
    },
    [currency, run],
  );

  const setCurrency = useCallback((nextCurrency) => {
    const normalized = nextCurrency === "GBP" ? "GBP" : "USD";
    setCurrencyState(normalized);
    invalidateInsight();
    try {
      window.sessionStorage.setItem(CURRENCY_STORAGE_KEY, normalized);
    } catch {
      // Continue with the in-memory preference when storage is unavailable.
    }
  }, [invalidateInsight]);

  const saveApiKey = useCallback((value) => {
    const normalized = storeApiKey(value);
    setApiKeyState(normalized);
    invalidateInsight();
    dashboardGenerationRef.current += 1;
    setDashboard(null);
    return refresh();
  }, [invalidateInsight, refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
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
  };
}
