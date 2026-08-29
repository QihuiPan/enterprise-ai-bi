import { useEffect, useId, useMemo, useState } from "react";
import { Filter, KeyRound, RotateCcw, SlidersHorizontal } from "lucide-react";
import { API_KEY_HEADER } from "../api/client";
import { EMPTY_FILTERS } from "../api/dashboard";
import { SUPPORTED_CURRENCIES } from "../utils/format";

const PRODUCT_SUGGESTION_LIMIT = 60;

function Field({ label, children }) {
  return <label className="control-field"><span>{label}</span>{children}</label>;
}

export function RuntimePreferences({ currency, apiKey, busy, onCurrencyChange, onSaveApiKey, compact = false }) {
  const [draftApiKey, setDraftApiKey] = useState(apiKey);

  useEffect(() => setDraftApiKey(apiKey), [apiKey]);

  function saveKey(event) {
    event.preventDefault();
    onSaveApiKey(draftApiKey);
  }

  return (
    <div className={`runtime-preferences ${compact ? "compact-preferences" : ""}`}>
      <Field label="Value currency">
        <select
          value={currency}
          onChange={(event) => onCurrencyChange(event.target.value)}
          disabled={busy}
        >
          {SUPPORTED_CURRENCIES.map(({ code, label }) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
      </Field>
      <form className="api-key-form" onSubmit={saveKey}>
        <Field label="API key (this session)">
          <span className="secure-input">
            <KeyRound size={14} aria-hidden="true" />
            <input
              type="password"
              value={draftApiKey}
              onChange={(event) => setDraftApiKey(event.target.value)}
              placeholder={`Optional ${API_KEY_HEADER}`}
              autoComplete="off"
              spellCheck="false"
            />
          </span>
        </Field>
        <button className="control-button" type="submit" disabled={busy || draftApiKey === apiKey}>
          Save
        </button>
      </form>
    </div>
  );
}

export function DashboardControls({
  filters,
  options,
  currency,
  apiKey,
  busy,
  onApply,
  onReset,
  onCurrencyChange,
  onSaveApiKey,
}) {
  const [draft, setDraft] = useState(filters);
  const [validationError, setValidationError] = useState("");
  const productListId = useId();

  useEffect(() => setDraft(filters), [filters]);

  const productSuggestions = useMemo(() => {
    const query = draft.product.trim().toLocaleLowerCase();
    const products = options?.products ?? [];
    return products
      .filter((product) => !query || product.toLocaleLowerCase().includes(query))
      .slice(0, PRODUCT_SUGGESTION_LIMIT);
  }, [draft.product, options]);

  const activeCount = Object.values(filters).filter(Boolean).length;

  function update(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
    setValidationError("");
  }

  function submit(event) {
    event.preventDefault();
    if (draft.start_date && draft.end_date && draft.start_date > draft.end_date) {
      setValidationError("Start date must be on or before end date.");
      return;
    }
    onApply(draft);
  }

  function reset() {
    setDraft({ ...EMPTY_FILTERS });
    setValidationError("");
    onReset();
  }

  return (
    <section className="dashboard-controls" aria-label="Dashboard controls">
      <div className="controls-heading">
        <span><SlidersHorizontal size={17} aria-hidden="true" /></span>
        <div>
          <strong>Explore the evidence</strong>
          <small>
            {activeCount
              ? `${activeCount} active ${activeCount === 1 ? "filter" : "filters"}`
              : "All validated records"}
          </small>
        </div>
      </div>
      <form className="filter-form" onSubmit={submit}>
        <Field label="From">
          <input
            type="date"
            value={draft.start_date}
            min={options?.date_min}
            max={options?.date_max}
            onChange={(event) => update("start_date", event.target.value)}
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={draft.end_date}
            min={options?.date_min}
            max={options?.date_max}
            onChange={(event) => update("end_date", event.target.value)}
          />
        </Field>
        <Field label="Region">
          <select value={draft.region} onChange={(event) => update("region", event.target.value)}>
            <option value="">All regions</option>
            {(options?.regions ?? []).map((region) => <option key={region} value={region}>{region}</option>)}
          </select>
        </Field>
        <Field label="Category">
          <select value={draft.category} onChange={(event) => update("category", event.target.value)}>
            <option value="">All categories</option>
            {(options?.categories ?? []).map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
        </Field>
        <Field label="Product">
          <input
            type="search"
            value={draft.product}
            list={productListId}
            placeholder="All products"
            onChange={(event) => update("product", event.target.value)}
          />
          <datalist id={productListId}>
            {productSuggestions.map((product) => <option key={product} value={product} />)}
          </datalist>
        </Field>
        <div className="filter-actions">
          <button className="control-button apply-button" type="submit" disabled={busy}>
            <Filter size={14} aria-hidden="true" />Apply
          </button>
          <button className="control-button reset-button" type="button" onClick={reset} disabled={busy || !activeCount}>
            <RotateCcw size={14} aria-hidden="true" />Reset
          </button>
        </div>
        {validationError && <p className="filter-error" role="alert">{validationError}</p>}
      </form>
      <RuntimePreferences
        currency={currency}
        apiKey={apiKey}
        busy={busy}
        onCurrencyChange={onCurrencyChange}
        onSaveApiKey={onSaveApiKey}
      />
      <p className="currency-note">Currency changes formatting only; choose the source currency of the loaded dataset.</p>
    </section>
  );
}
