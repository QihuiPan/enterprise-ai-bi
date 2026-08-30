import { useCallback, useEffect, useRef, useState } from "react";
import {
  EMPTY_FILTERS,
  fetchDatasetProfile,
  fetchDashboard,
  fetchFilterOptions,
  importSalesFile,
  loadDemoData,
  normalizeFilters,
  queryInsight,
  uploadSalesCsv,
} from "../api/dashboard";
import { getApiKey, storeApiKey } from "../api/client";

const CURRENCY_STORAGE_KEY = "enterprise-ai-bi.currency";

function storeCurrencyPreference(currency) {
  try {
    window.sessionStorage.setItem(CURRENCY_STORAGE_KEY, currency);
  } catch {
    // Continue with the in-memory value when storage is unavailable.
  }
}

function initialCurrency() {
  try {
    return window.sessionStorage.getItem(CURRENCY_STORAGE_KEY) === "GBP" ? "GBP" : "USD";
  } catch {
    return "USD";
  }
}

function responseMatchesProfile(response, profile) {
  const version = response?.dataset_version;
  return Boolean(
    version
    && profile?.dataset_version?.profile_sha256
    && version.content_sha256 === profile.content_sha256
    && version.currency === profile.currency
    && version.profile_sha256 === profile.dataset_version.profile_sha256
  );
}

function profileVersionsMatch(first, second) {
  const firstVersion = first?.dataset_version?.profile_sha256;
  const secondVersion = second?.dataset_version?.profile_sha256;
  return Boolean(firstVersion && secondVersion && firstVersion === secondVersion);
}

export function useBusinessDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [insight, setInsight] = useState(null);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const [filterOptions, setFilterOptions] = useState(null);
  const [datasetProfile, setDatasetProfile] = useState(undefined);
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

  const run = useCallback(async (
    operation,
    clearDashboardOnError = false,
    propagateError = false,
  ) => {
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
      if (propagateError) throw requestError;
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

  const fetchTrackedProfile = useCallback(async (dashboardGeneration) => {
    try {
      const nextProfile = await fetchDatasetProfile();
      return { profile: nextProfile, error: null };
    } catch (profileError) {
      return { profile: undefined, error: profileError };
    }
  }, []);

  const commitDatasetProfile = useCallback((profile, dashboardGeneration) => {
    if (dashboardGenerationRef.current !== dashboardGeneration) return;
    setDatasetProfile(profile);
    if (
      profile?.currency_verified !== false
      && (profile?.currency === "USD" || profile?.currency === "GBP")
    ) {
      setCurrencyState(profile.currency);
      storeCurrencyPreference(profile.currency);
    }
  }, []);

  const fetchConsistentSnapshot = useCallback(async (
    selectedFilters,
    cachedOptions,
    dashboardGeneration,
  ) => {
    let reusableOptions = cachedOptions;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const [dashboardResult, nextOptions, profileOutcome] = await Promise.all([
        fetchDashboard(selectedFilters),
        reusableOptions ? Promise.resolve(reusableOptions) : fetchFilterOptions(),
        fetchTrackedProfile(dashboardGeneration),
      ]);
      if (profileOutcome.error || profileOutcome.profile === null) {
        throw profileOutcome.error
          ?? new Error("Active sales data has no dataset profile. Reload or import the source again.");
      }
      if (
        responseMatchesProfile(dashboardResult, profileOutcome.profile)
        && responseMatchesProfile(nextOptions, profileOutcome.profile)
      ) {
        return {
          dashboard: dashboardResult,
          options: nextOptions,
          profile: profileOutcome.profile,
        };
      }
      reusableOptions = null;
    }
    throw new Error("The active dataset changed while the dashboard was loading. Refresh and try again.");
  }, [fetchTrackedProfile]);

  const hydrate = useCallback(
    async (selectedFilters, reloadOptions = false) => {
      const dashboardGeneration = dashboardGenerationRef.current + 1;
      dashboardGenerationRef.current = dashboardGeneration;
      const nextDashboard = await run(async () => {
        let snapshot;
        try {
          snapshot = await fetchConsistentSnapshot(
            selectedFilters,
            reloadOptions ? null : filterOptionsRef.current,
            dashboardGeneration,
          );
        } catch (snapshotError) {
          if (dashboardGenerationRef.current === dashboardGeneration) {
            setDashboard(null);
            setDatasetProfile(undefined);
          }
          throw snapshotError;
        }
        if (dashboardGenerationRef.current === dashboardGeneration) {
          commitDatasetProfile(snapshot.profile, dashboardGeneration);
          setDashboard(snapshot.dashboard);
          committedFiltersRef.current = selectedFilters;
          filterOptionsRef.current = snapshot.options;
          setFilterOptions(snapshot.options);
        }
        return snapshot.dashboard;
      });
      return {
        dashboard: nextDashboard,
        current: dashboardGenerationRef.current === dashboardGeneration,
      };
    },
    [commitDatasetProfile, fetchConsistentSnapshot, run],
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
    (replaceOperation, propagateError = false, includeOperationResult = false) => {
      dashboardGenerationRef.current += 1;
      invalidateInsight();
      return run(async () => {
        const operationResult = await replaceOperation();
        const operationProfile = operationResult?.dataset_profile ?? undefined;
        setDatasetProfile(operationProfile);
        if (
          operationProfile?.currency_verified !== false
          && (operationProfile?.currency === "USD" || operationProfile?.currency === "GBP")
        ) {
          setCurrencyState(operationProfile.currency);
          storeCurrencyPreference(operationProfile.currency);
        }
        const dashboardGeneration = dashboardGenerationRef.current + 1;
        dashboardGenerationRef.current = dashboardGeneration;
        if (!includeOperationResult) setDashboard(null);

        try {
          const nextFilters = { ...EMPTY_FILTERS };
          filtersRef.current = nextFilters;
          setFilters(nextFilters);
          const snapshot = await fetchConsistentSnapshot(
            nextFilters,
            null,
            dashboardGeneration,
          );
          if (dashboardGenerationRef.current === dashboardGeneration) {
            commitDatasetProfile(snapshot.profile, dashboardGeneration);
            setDashboard(snapshot.dashboard);
            committedFiltersRef.current = nextFilters;
            filterOptionsRef.current = snapshot.options;
            setFilterOptions(snapshot.options);
          }
          const superseded = Boolean(
            includeOperationResult
            && operationProfile
            && !profileVersionsMatch(operationProfile, snapshot.profile)
          );
          return includeOperationResult
            ? {
              dashboard: snapshot.dashboard,
              importSummary: operationResult,
              activeProfile: snapshot.profile,
              superseded,
            }
            : snapshot.dashboard;
        } catch (refreshError) {
          if (dashboardGenerationRef.current === dashboardGeneration) {
            setDashboard(null);
            filterOptionsRef.current = null;
            setFilterOptions(null);
          }
          const message = refreshError instanceof Error
            ? refreshError.message
            : String(refreshError);
          throw new Error(`Data was replaced, but dashboard refresh failed: ${message}`);
        }
      }, false, propagateError);
    },
    [commitDatasetProfile, fetchConsistentSnapshot, invalidateInsight, run],
  );

  const loadDemo = useCallback(
    () => replaceData(loadDemoData),
    [replaceData],
  );

  const upload = useCallback(
    (file) => replaceData(() => uploadSalesCsv(file)),
    [replaceData],
  );

  const importData = useCallback(
    (file, configuration) => replaceData(
      () => importSalesFile(file, configuration),
      true,
      true,
    ),
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
    storeCurrencyPreference(normalized);
  }, [invalidateInsight]);

  const saveApiKey = useCallback((value) => {
    const normalized = storeApiKey(value);
    setApiKeyState(normalized);
    invalidateInsight();
    dashboardGenerationRef.current += 1;
    setDashboard(null);
    setDatasetProfile(undefined);
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
    datasetProfile,
    currency,
    apiKey,
    busy,
    error,
    refresh,
    loadDemo,
    upload,
    importData,
    ask,
    applyFilters,
    resetFilters,
    setCurrency,
    saveApiKey,
  };
}
