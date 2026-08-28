import { useCallback, useEffect, useState } from "react";
import {
  fetchDashboard,
  loadDemoData,
  queryInsight,
  uploadSalesCsv,
} from "../api/dashboard";

export function useBusinessDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [insight, setInsight] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (operation, clearDashboardOnError = false) => {
    setBusy(true);
    setError("");
    try {
      return await operation();
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : String(requestError);
      if (!message.includes("No sales data")) setError(message);
      if (clearDashboardOnError) setDashboard(null);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(
    () => run(async () => setDashboard(await fetchDashboard()), true),
    [run],
  );

  const loadDemo = useCallback(
    () => run(async () => {
      await loadDemoData();
      setDashboard(await fetchDashboard());
    }),
    [run],
  );

  const upload = useCallback(
    (file) => run(async () => {
      await uploadSalesCsv(file);
      setDashboard(await fetchDashboard());
    }),
    [run],
  );

  const ask = useCallback(
    (question) => run(async () => setInsight(await queryInsight(question))),
    [run],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { dashboard, insight, busy, error, refresh, loadDemo, upload, ask };
}
