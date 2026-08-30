import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  FileSpreadsheet,
  FileUp,
  Info,
  LoaderCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import { previewSalesFile } from "../api/dashboard";
import { SUPPORTED_CURRENCIES } from "../utils/format";

const ACCEPTED_FILE_TYPES = ".csv,.tsv,.xlsx,text/csv,text/tab-separated-values,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const SOURCE_PROFILES = [
  {
    value: "order_level",
    label: "Automatic / standard sales rows",
    description: "Use column names to determine whether rows are orders, transactions, or sales records.",
  },
  {
    value: "m5",
    label: "Prepared Walmart M5",
    description: "Rows are store-category-day aggregates and entity IDs are stores.",
    currency: "USD",
    datasetName: "Walmart M5",
    expectedRows: 58105,
  },
  {
    value: "uci",
    label: "Prepared UCI Online Retail II",
    description: "Rows are customer-country-day aggregates in GBP.",
    currency: "GBP",
    datasetName: "UCI Online Retail II",
    expectedRows: 33112,
  },
  {
    value: "iowa",
    label: "Prepared Iowa Liquor Sales 2024",
    description: "Rows are store-county-category-month aggregates in USD.",
    currency: "USD",
    datasetName: "Iowa Liquor Sales 2024",
    expectedRows: 438528,
  },
];
const PREPARED_REQUIRED_FIELDS = [
  "order_id",
  "order_date",
  "customer_id",
  "region",
  "category",
  "product",
  "quantity",
  "unit_price",
  "discount",
];
const PREPARED_REQUIRED_FIELD_SET = new Set(PREPARED_REQUIRED_FIELDS);
const TARGET_ORDER = [
  "order_date",
  "currency",
  "revenue",
  "quantity",
  "unit_price",
  "discount",
  "order_id",
  "customer_id",
  "region",
  "category",
  "product",
];
const FALLBACK_FIELDS = {
  order_date: {
    label: "Sale date",
    required: true,
    description: "When the sale or reporting period occurred.",
  },
  currency: {
    label: "Currency code",
    description: "Optional ISO code such as USD or GBP. Every row must match the selected value currency.",
    default: "Selected source currency",
  },
  revenue: {
    label: "Sales amount / revenue",
    description: "Use this when the file already contains the total sales value.",
  },
  quantity: {
    label: "Quantity",
    description: "Number of units. Required with unit price when no sales amount is mapped.",
    default: 1,
  },
  unit_price: {
    label: "Unit price",
    description: "Price for one unit. Required with quantity when no sales amount is mapped.",
  },
  discount: {
    label: "Discount",
    description: "A decimal from 0 to 1. Leave blank when the source has no discount.",
    default: 0,
  },
  order_id: {
    label: "Order or record ID",
    description: "Blank or repeated IDs will be replaced with stable sales-record IDs.",
    default: "Generated automatically",
  },
  customer_id: {
    label: "Customer or account",
    description: "Used for customer grouping. Missing values become Unspecified.",
    default: "Unspecified",
  },
  region: {
    label: "Region",
    description: "A country, state, territory, branch, or other sales area.",
    default: "Unspecified",
  },
  category: {
    label: "Category",
    description: "The product or service family.",
    default: "Unspecified",
  },
  product: {
    label: "Product",
    description: "The sold product, service, or item.",
    default: "Unspecified",
  },
};

function defaultDatasetName(filename = "") {
  return filename
    .replace(/\.(csv|tsv|xlsx)$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function displayMessage(issue) {
  if (typeof issue === "string") return issue;
  if (issue?.msg) return issue.msg;
  if (issue?.message) return issue.message;
  try {
    return JSON.stringify(issue);
  } catch {
    return String(issue);
  }
}

function errorMessages(error) {
  const detail = error?.payload?.detail;
  if (Array.isArray(detail)) return detail.map(displayMessage);
  if (detail) return [displayMessage(detail)];
  return [error instanceof Error ? error.message : String(error)];
}

function sheetName(sheet) {
  return typeof sheet === "string" ? sheet : sheet?.name ?? "";
}

function suggestionColumn(suggestion) {
  if (typeof suggestion === "string") return suggestion;
  return suggestion?.column ?? "";
}

function buildSuggestedMapping(preview) {
  const columns = new Set((preview?.columns ?? []).map((column) => column.name));
  const mapping = Object.fromEntries(
    Object.entries(preview?.suggestions ?? {})
      .map(([field, suggestion]) => [field, suggestionColumn(suggestion)])
      .filter(([, column]) => column && columns.has(column)),
  );
  if (mapping.revenue) {
    delete mapping.unit_price;
    delete mapping.discount;
  }
  return mapping;
}

function fieldDefinitions(preview) {
  const supplied = new Map(
    (preview?.field_definitions ?? []).map((field) => [field.name, field]),
  );
  return TARGET_ORDER.map((name) => ({
    name,
    ...FALLBACK_FIELDS[name],
    ...(supplied.get(name) ?? {}),
  }));
}

function mappingReadiness(mapping, sourceProfile, previewRowCount) {
  const prepared = sourceProfile !== "order_level";
  const selectedProfile = SOURCE_PROFILES.find(
    (profile) => profile.value === sourceProfile,
  );
  const expectedRows = selectedProfile?.expectedRows ?? null;
  const preparedRowCountMatches = !prepared
    || (expectedRows !== null && Number(previewRowCount) === expectedRows);
  const hasDate = Boolean(mapping.order_date);
  const hasRevenue = Boolean(mapping.revenue);
  const hasComponents = Boolean(mapping.quantity && mapping.unit_price);
  const metricConflict = hasRevenue && Boolean(mapping.unit_price || mapping.discount);
  const usedColumns = Object.values(mapping).filter(Boolean);
  const duplicateColumns = [...new Set(
    usedColumns.filter((column, index) => usedColumns.indexOf(column) !== index),
  )];
  const preparedMissing = prepared
    ? PREPARED_REQUIRED_FIELDS.filter((field) => mapping[field] !== field)
    : [];
  const preparedUnexpected = prepared
    ? Object.entries(mapping)
      .filter(([target, source]) => source && (
        !PREPARED_REQUIRED_FIELD_SET.has(target) || target !== source
      ))
      .map(([target]) => target)
    : [];
  return {
    ready: prepared
      ? preparedMissing.length === 0
        && preparedUnexpected.length === 0
        && preparedRowCountMatches
      : hasDate
        && (hasRevenue || hasComponents)
        && !metricConflict
        && duplicateColumns.length === 0,
    prepared,
    preparedMissing,
    preparedUnexpected,
    expectedRows,
    preparedRowCountMatches,
    hasDate,
    hasMeasure: hasRevenue || hasComponents,
    metricConflict,
    duplicateColumns,
  };
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "—";
  const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
  return rendered.length > 80 ? `${rendered.slice(0, 77)}…` : rendered;
}

function Stepper({ step }) {
  const steps = ["Choose file", "Match columns", "Review", "Active"];
  return (
    <ol className="import-steps" aria-label="Import progress">
      {steps.map((label, index) => {
        const number = index + 1;
        const complete = number < step;
        return (
          <li
            key={label}
            className={complete ? "complete" : number === step ? "current" : ""}
            aria-current={number === step ? "step" : undefined}
          >
            <span>{complete ? <CheckCircle2 size={15} /> : number}</span>
            <small>{label}</small>
          </li>
        );
      })}
    </ol>
  );
}

function MessageList({ title, messages, tone = "warning" }) {
  if (!messages?.length) return null;
  const Icon = tone === "error" ? AlertCircle : Info;
  return (
    <div className={`import-message ${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <ul>{messages.map((message, index) => <li key={`${message}-${index}`}>{message}</li>)}</ul>
      </div>
    </div>
  );
}

function PreviewTable({ preview }) {
  const columns = preview?.columns ?? [];
  const rows = (preview?.sample_rows ?? []).slice(0, 8);
  if (!columns.length || !rows.length) return null;
  return (
    <div className="import-preview-table">
      <table>
        <caption>Preview of the first {rows.length} data rows</caption>
        <thead>
          <tr>{columns.map((column) => <th key={column.name}>{column.name}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => {
                const value = formatCell(row[column.name]);
                return <td key={column.name} title={value}>{value}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FileChoice({ busy, onChoose, onDrop }) {
  const inputRef = useRef(null);
  return (
    <div className="import-file-step">
      <div
        className="import-dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
      >
        <span><FileSpreadsheet size={30} aria-hidden="true" /></span>
        <h3>Choose a structured sales file</h3>
        <p>Use a CSV, TSV, or Excel (.xlsx) file with one row per sale or sales record.</p>
        <button
          className="primary-button"
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
        >
          {busy ? <LoaderCircle className="spin" size={17} /> : <FileUp size={17} />}
          {busy ? "Reading file…" : "Choose file"}
        </button>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept={ACCEPTED_FILE_TYPES}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            event.target.value = "";
            if (selected) onChoose(selected);
          }}
          disabled={busy}
        />
        <small>Minimum data: a date and sales amount, or a date, quantity, and unit price.</small>
      </div>
      <div className="import-safety-note">
        <ShieldCheck size={18} aria-hidden="true" />
        <p><strong>Your current dashboard stays unchanged.</strong> This file is only previewed until you explicitly activate it.</p>
      </div>
    </div>
  );
}

export function DataImportDialog({
  open,
  busy,
  currency,
  hasActiveData,
  onClose,
  onImport,
}) {
  const dialogRef = useRef(null);
  const previewGenerationRef = useRef(0);
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [datasetName, setDatasetName] = useState("");
  const [automaticDatasetName, setAutomaticDatasetName] = useState("");
  const [sourceCurrency, setSourceCurrency] = useState(currency);
  const [automaticCurrency, setAutomaticCurrency] = useState(currency);
  const [sourceProfile, setSourceProfile] = useState("order_level");
  const [localBusy, setLocalBusy] = useState(false);
  const [errors, setErrors] = useState([]);
  const [importSummary, setImportSummary] = useState(null);
  const isBusy = busy || localBusy;

  const fields = useMemo(() => fieldDefinitions(preview), [preview]);
  const readiness = useMemo(
    () => mappingReadiness(mapping, sourceProfile, preview?.row_count),
    [mapping, preview?.row_count, sourceProfile],
  );
  const selectedSheet = preview?.selected_sheet ?? "";
  const sheets = (preview?.sheets ?? []).map(sheetName).filter(Boolean);
  const importWarnings = importSummary?.warnings ?? [];
  const activeDatasetName = importSummary?.dataset_profile?.dataset_name
    ?? datasetName.trim();

  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => dialogRef.current?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (open) return;
    previewGenerationRef.current += 1;
    setStep(1);
    setFile(null);
    setPreview(null);
    setMapping({});
    setDatasetName("");
    setAutomaticDatasetName("");
    setSourceCurrency(currency);
    setAutomaticCurrency(currency);
    setSourceProfile("order_level");
    setLocalBusy(false);
    setErrors([]);
    setImportSummary(null);
  }, [currency, open]);

  async function inspect(selectedFile, sheet = "", replaceName = false) {
    if (!/\.(csv|tsv|xlsx)$/i.test(selectedFile.name)) {
      setErrors(["Choose a CSV, TSV, or Excel (.xlsx) file."]);
      return;
    }
    const generation = previewGenerationRef.current + 1;
    previewGenerationRef.current = generation;
    setLocalBusy(true);
    setErrors([]);
    setFile(selectedFile);
    try {
      const result = await previewSalesFile(selectedFile, sheet);
      if (previewGenerationRef.current !== generation) return;
      setPreview(result);
      setMapping(buildSuggestedMapping(result));
      if (replaceName || !datasetName) {
        const nextName = defaultDatasetName(result.filename || selectedFile.name);
        setDatasetName(nextName);
        setAutomaticDatasetName(nextName);
      }
      if (replaceName) {
        setSourceProfile("order_level");
        setSourceCurrency(currency);
        setAutomaticCurrency(currency);
      }
      setStep(2);
    } catch (error) {
      if (previewGenerationRef.current === generation) setErrors(errorMessages(error));
    } finally {
      if (previewGenerationRef.current === generation) setLocalBusy(false);
    }
  }

  function close() {
    if (!isBusy) onClose();
  }

  function handleDialogKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll(
      "button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex='0']",
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function activate() {
    setLocalBusy(true);
    setErrors([]);
    try {
      const result = await onImport(file, {
        currency: sourceCurrency,
        datasetName: datasetName.trim(),
        mapping: Object.fromEntries(Object.entries(mapping).filter(([, value]) => value)),
        expectedSha256: preview.file_sha256,
        sheetName: selectedSheet,
        sourceProfile,
      });
      if (result?.superseded) {
        const importedName = result?.importSummary?.dataset_profile?.dataset_name
          ?? datasetName.trim();
        const activeName = result?.activeProfile?.dataset_name ?? "another dataset";
        setImportSummary(null);
        setErrors([
          `“${importedName}” passed validation, but “${activeName}” replaced it before `
          + "the dashboard refresh completed. The dashboard now shows the newer active dataset.",
        ]);
        setStep(3);
        return;
      }
      const summary = result?.importSummary ?? result?.operationResult ?? result ?? {};
      setImportSummary(summary);
      setStep(4);
    } catch (error) {
      setErrors(errorMessages(error));
    } finally {
      setLocalBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="import-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        ref={dialogRef}
        className="import-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
      >
        <header className="import-dialog-header">
          <div>
            <span className="eyebrow">DATA IMPORT</span>
            <h2 id="import-title">Bring your sales data into Northstar</h2>
            <p>Review every match before anything changes.</p>
          </div>
          <button className="icon-button" type="button" aria-label="Close import dialog" onClick={close} disabled={isBusy}>
            <X size={18} />
          </button>
        </header>

        <Stepper step={step} />

        <div className="import-dialog-body">
          <MessageList title="We could not continue" messages={errors} tone="error" />

          {step === 1 && (
            <FileChoice
              busy={isBusy}
              onChoose={(selected) => inspect(selected, "", true)}
              onDrop={(event) => {
                event.preventDefault();
                const selected = event.dataTransfer.files?.[0];
                if (selected && !isBusy) inspect(selected, "", true);
              }}
            />
          )}

          {step === 2 && preview && (
            <>
              <div className="import-file-summary">
                <span><FileSpreadsheet size={20} aria-hidden="true" /></span>
                <div>
                  <strong>{preview.filename || file?.name}</strong>
                  <small>{String(preview.file_format || file?.name.split(".").pop()).toUpperCase()} · {Number(preview.row_count || 0).toLocaleString()} rows</small>
                </div>
                <button className="control-button" type="button" onClick={() => setStep(1)} disabled={isBusy}>Choose another</button>
              </div>

              <div className="import-section-heading">
                <div><span className="eyebrow">STEP 2</span><h3>Match your columns</h3></div>
                <p>We suggested matches from column names and values. Please check them.</p>
              </div>

              <div className="import-settings-grid">
                <label className="import-field">
                  <span>Dataset name</span>
                  <input
                    value={datasetName}
                    maxLength={120}
                    onChange={(event) => {
                      setDatasetName(event.target.value);
                      setAutomaticDatasetName(event.target.value);
                    }}
                    placeholder="For example, 2026 retail sales"
                    disabled={sourceProfile !== "order_level"}
                  />
                </label>
                <label className="import-field">
                  <span>Source currency</span>
                  <select
                    value={sourceCurrency}
                    onChange={(event) => {
                      setSourceCurrency(event.target.value);
                      setAutomaticCurrency(event.target.value);
                    }}
                    disabled={sourceProfile !== "order_level"}
                    title={sourceProfile !== "order_level" ? "Prepared profiles use their documented source currency." : undefined}
                  >
                    {SUPPORTED_CURRENCIES.map(({ code, label }) => (
                      <option key={code} value={code}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="import-field">
                  <span>Dataset meaning</span>
                  <select
                    value={sourceProfile}
                    onChange={(event) => {
                      const nextProfile = SOURCE_PROFILES.find(
                        (profile) => profile.value === event.target.value,
                      );
                      setSourceProfile(event.target.value);
                      if (event.target.value === "order_level") {
                        setSourceCurrency(automaticCurrency);
                        setDatasetName(automaticDatasetName);
                      } else {
                        if (nextProfile?.currency) setSourceCurrency(nextProfile.currency);
                        if (nextProfile?.datasetName) setDatasetName(nextProfile.datasetName);
                      }
                    }}
                  >
                    {SOURCE_PROFILES.map((profile) => (
                      <option key={profile.value} value={profile.value}>{profile.label}</option>
                    ))}
                  </select>
                  <small>{SOURCE_PROFILES.find((profile) => profile.value === sourceProfile)?.description}</small>
                </label>
                {sheets.length > 1 && (
                  <label className="import-field">
                    <span>Excel sheet</span>
                    <select
                      value={selectedSheet}
                      onChange={(event) => inspect(file, event.target.value)}
                      disabled={isBusy}
                    >
                      {sheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}
                    </select>
                  </label>
                )}
              </div>

              <div className="mapping-requirement" role="note">
                <Info size={17} aria-hidden="true" />
                {readiness.prepared ? (
                  <p>
                    <strong>What is required?</strong> A prepared profile accepts only its complete
                    prepared-output contract ({Number(readiness.expectedRows).toLocaleString()} rows).
                    Every target below must match the source column with the same canonical name.
                  </p>
                ) : (
                  <p>
                    <strong>What is required?</strong> Match a sale date and either a sales amount,
                    or both quantity and unit price. Unmatched business dimensions use safe
                    “Unspecified” labels.
                  </p>
                )}
              </div>

              <div className="mapping-list">
                {fields.map((field) => {
                  const suggestion = preview.suggestions?.[field.name];
                  const selected = mapping[field.name] ?? "";
                  const suggested = suggestionColumn(suggestion);
                  const isRequired = field.required || (
                    readiness.prepared && PREPARED_REQUIRED_FIELD_SET.has(field.name)
                  );
                  return (
                    <label className="mapping-row" key={field.name}>
                      <span className="mapping-copy">
                        <strong>{field.label}{isRequired ? " *" : ""}</strong>
                        <small>{field.description}</small>
                      </span>
                      <select
                        value={selected}
                        onChange={(event) => {
                          setMapping((current) => ({ ...current, [field.name]: event.target.value }));
                          setErrors([]);
                        }}
                        aria-label={`Source column for ${field.label}`}
                      >
                        <option value="">{isRequired ? "Choose a column" : "Use automatic/default"}</option>
                        {preview.columns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
                      </select>
                      <span className="mapping-example">
                        {selected
                          ? `Example: ${formatCell(preview.columns.find((column) => column.name === selected)?.samples?.[0])}`
                          : `Default: ${field.default ?? "Not used"}`}
                        {selected && selected === suggested && suggestion?.confidence !== undefined && (
                          <em>{suggestion.confidence >= 0.8 ? "Strong match" : "Suggested — check"}</em>
                        )}
                      </span>
                    </label>
                  );
                })}
              </div>

              {!readiness.prepared && !readiness.hasDate && <p className="mapping-status error"><AlertCircle size={15} />Choose the column containing the sale date.</p>}
              {!readiness.prepared && !readiness.hasMeasure && <p className="mapping-status error"><AlertCircle size={15} />Choose a sales amount, or choose both quantity and unit price.</p>}
              {readiness.prepared && readiness.preparedMissing.length > 0 && (
                <p className="mapping-status error"><AlertCircle size={15} />Prepared artifacts still need exact canonical matches for: {readiness.preparedMissing.join(", ")}.</p>
              )}
              {readiness.prepared && readiness.preparedUnexpected.length > 0 && (
                <p className="mapping-status error"><AlertCircle size={15} />Prepared artifacts cannot use renamed or extra mappings: {readiness.preparedUnexpected.join(", ")}.</p>
              )}
              {readiness.prepared && !readiness.preparedRowCountMatches && (
                <p className="mapping-status error"><AlertCircle size={15} />This prepared profile requires {Number(readiness.expectedRows).toLocaleString()} rows; the preview has {Number(preview.row_count || 0).toLocaleString()}. Use Automatic for a subset or derivative.</p>
              )}
              {!readiness.prepared && readiness.duplicateColumns.length > 0 && (
                <p className="mapping-status error"><AlertCircle size={15} />Each source column can be used once. Check: {readiness.duplicateColumns.join(", ")}.</p>
              )}
              {!readiness.prepared && readiness.metricConflict && (
                <p className="mapping-status error"><AlertCircle size={15} />When sales amount is mapped, leave unit price and discount on automatic/default. Quantity may still be mapped for unit totals.</p>
              )}
              <MessageList title="Things to review" messages={preview.warnings} />

              <div className="import-preview-heading">
                <div><strong>Source preview</strong><small>Values shown here are not imported yet.</small></div>
                <span>{preview.columns.length} columns</span>
              </div>
              <PreviewTable preview={preview} />
            </>
          )}

          {step === 3 && preview && (
            <div className="import-review">
              <div className="import-review-hero">
                <span><ShieldCheck size={28} aria-hidden="true" /></span>
                <div>
                  <span className="eyebrow">FINAL CHECK</span>
                  <h3>Review and activate “{datasetName.trim()}”</h3>
                  <p>The server will validate every row before replacing any active data.</p>
                </div>
              </div>

              <dl className="import-review-facts">
                <div><dt>File</dt><dd>{preview.filename || file?.name}</dd></div>
                {selectedSheet && <div><dt>Sheet</dt><dd>{selectedSheet}</dd></div>}
                <div><dt>Rows to validate</dt><dd>{Number(preview.row_count || 0).toLocaleString()}</dd></div>
                <div><dt>Source currency</dt><dd>{sourceCurrency} (no conversion)</dd></div>
                <div><dt>Dataset meaning</dt><dd>{SOURCE_PROFILES.find((profile) => profile.value === sourceProfile)?.label}</dd></div>
              </dl>

              <div className="import-review-mapping">
                <strong>Column matches</strong>
                <dl>
                  {fields.filter((field) => mapping[field.name]).map((field) => (
                    <div key={field.name}><dt>{field.label}</dt><dd>{mapping[field.name]}</dd></div>
                  ))}
                </dl>
              </div>
              <MessageList title="Things to review" messages={preview.warnings} />
              <div className="replacement-warning">
                <AlertCircle size={19} aria-hidden="true" />
                <p>
                  <strong>{hasActiveData ? "This will replace the active dataset." : "This will become the active dataset."}</strong>
                  {" "}If validation finds a problem, nothing will be changed.
                </p>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="import-complete" role="status" aria-live="polite">
              <span><CheckCircle2 size={38} aria-hidden="true" /></span>
              <span className="eyebrow">IMPORT COMPLETE</span>
              <h3>“{activeDatasetName}” is now active</h3>
              <p>
                {importSummary?.rows_loaded
                  ? `${Number(importSummary.rows_loaded).toLocaleString()} validated sales records are ready to explore.`
                  : "Your validated sales records are ready to explore."}
              </p>
              {importSummary?.date_min && importSummary?.date_max && (
                <small>{importSummary.date_min} — {importSummary.date_max}</small>
              )}
              <MessageList title="Import notes" messages={importWarnings} />
            </div>
          )}
        </div>

        <footer className="import-dialog-footer">
          {step === 1 && <button className="secondary-button" type="button" onClick={close} disabled={isBusy}>Cancel</button>}
          {step === 2 && (
            <>
              <button className="secondary-button" type="button" onClick={() => setStep(1)} disabled={isBusy}><ArrowLeft size={16} />Back</button>
              <button className="primary-button" type="button" onClick={() => { setErrors([]); setStep(3); }} disabled={isBusy || !readiness.ready || !datasetName.trim()}>
                Review import <ChevronRight size={16} />
              </button>
            </>
          )}
          {step === 3 && (
            <>
              <button className="secondary-button" type="button" onClick={() => { setErrors([]); setStep(2); }} disabled={isBusy}><ArrowLeft size={16} />Back to matches</button>
              <button className="primary-button" type="button" onClick={activate} disabled={isBusy}>
                {isBusy ? <LoaderCircle className="spin" size={17} /> : <ShieldCheck size={17} />}
                {isBusy ? "Validating every row…" : hasActiveData ? "Validate and replace active data" : "Validate and use this dataset"}
              </button>
            </>
          )}
          {step === 4 && <button className="primary-button" type="button" onClick={onClose}>View dashboard</button>}
        </footer>
      </section>
    </div>
  );
}
