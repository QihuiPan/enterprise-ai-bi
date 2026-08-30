# Operations Guide

## Health, metrics, and first data load

- `GET /health/live` verifies that the API process is responding.
- `GET /health/ready` and the backwards-compatible `GET /health` verify database
  connectivity and return HTTP 503 when the service is not ready for traffic.
- `GET /metrics` exports aggregate HTTP counters, duration sums, and the current
  in-flight request count in Prometheus text format.
- `POST /api/data/demo` replaces existing rows with a deterministic dataset.
- `POST /api/data/preview` inspects a CSV, TSV, or XLSX input without changing
  the active dataset.
- `POST /api/data/import` receives the file again with an explicit mapping,
  verifies its preview SHA-256, revalidates the full input, and atomically
  replaces both sales rows and their dataset profile.
- `GET /api/data/profile` reports the active source and selected worksheet,
  mapping, generated/default fields, warnings, and analytical semantics.
- `POST /api/data/upload?replace=true` remains a compatibility route for the
  canonical nine-column CSV contract.
- Prepared public artifacts require an explicit profile: `m5` with USD, `uci`
  with GBP, or `iowa` with USD. The dashboard exposes these choices; API clients
  send multipart `source_profile` and `source_currency` fields. The server checks
  the exact canonical mapping, complete row/date coverage, generated-ID contract,
  and source dimensions before applying aggregate semantics. Subsets and modified
  derivatives use `source_profile=order_level`.
- Append imports are deliberately disabled so validation always covers the full
  analytical snapshot. Preview and every failed import leave the existing data
  and profile unchanged.

Every request that enters FastAPI's request-context middleware produces one JSON
access event and a response carrying `X-Request-ID`. Nginx-served static content
and proxy failures occur outside that middleware. Preserve the API fields when
shipping container logs to a central log service.

The dashboard uses one filtered database snapshot per refresh. The database
applies date and dimensional predicates before pandas conversion, and optional
ML cards report their own minimum-data errors without hiding core analytics.
The complete Iowa dataset still requires memory for one filtered snapshot and
on-demand model fitting; size the single-host demo accordingly and use a
warehouse or pre-aggregated serving layer for sustained multi-user workloads.
PostgreSQL read sessions use `REPEATABLE READ` so rows and profile metadata come
from one transaction snapshot. Dashboard, filter-option, and profile responses
are also fingerprint-bound across parallel HTTP requests and retried once when
an import races a refresh. Concurrent PostgreSQL writers can receive a
serialization conflict under this isolation level and should retry the complete
replacement transaction rather than individual statements.
SQLite uses WAL plus an explicit read transaction for the same one-snapshot
contract. Startup serializes the one-time legacy-profile backfill so concurrent
application processes cannot both insert it. PostgreSQL uses a transaction-level
advisory lock on a `READ COMMITTED` migration connection for the same reason.

## Backups

For Docker deployments, back up PostgreSQL with `pg_dump` from a controlled
operator environment. Test restoration to a separate database before relying on
the backup. SQLite development databases are disposable and are ignored by Git.

## Model operations

Model outputs are trained on demand from the current analytical dataset. Record
the data window, evaluation metrics, application commit, and configuration when
promoting an output to a business process. Do not interpret anomaly flags as
confirmed fraud and do not present forecast intervals as guaranteed bounds.
The general monthly forecaster treats month-start-only inputs such as the Iowa
application export as complete monthly aggregates. For transaction or daily
inputs, it excludes incomplete first and last observation months and returns
those periods in `excluded_periods` for auditability.

### Walmart M5

- Keep raw M5 files and generated artifacts outside the repository.
- Run `scripts/run_m5_pipeline.py --stage all` to verify, prepare, train, and
  evaluate the store-category model.
- Archive `m5_preparation_summary.json`, `m5_training_metrics.json`, the Git
  commit, and the source DOI together for reproducibility.
- Review `application_rows`, `application_revenue`, and
  `revenue_reconciliation_delta` in the preparation summary before loading the
  application CSV. These values are calculated with the production upload
  validator and expose the two-decimal unit-price precision effect.
- Keep candidate selection and blend calibration on the tuning horizon that
  precedes the final holdout; do not use final-holdout metrics for tuning.
- Do not label the project holdout metrics as official M5 WRMSSE results.
- The source has store and product hierarchies but no customer identities;
  customer segmentation therefore treats each store as a proxy entity.

### UCI Online Retail II and Iowa Liquor Sales 2024

- Run `python -m scripts.run_public_sales_pipeline --source uci --stage all`
  or use `--source iowa`; both commands also require raw-data and artifact
  directories.
- Archive the generated preparation summary with the application commit. It
  records the exact download SHA-256 and the revenue reconciliation.
- The Iowa archive contains five CSV parts. Treat an output that does not span
  January 1 through December 31, 2024 as incomplete.
- UCI December 2011 contains only nine observed days, so the analysis stage
  excludes that partial month from forecast fitting and evaluation.
- UCI monetary values are GBP and Iowa monetary values are USD. Load one source
  at a time unless a documented currency conversion is applied first.
- The Docker API accepts up to 64 MiB so the 45.6 MB prepared Iowa CSV can be
  loaded. The ASGI layer bounds declared and chunked request bodies before
  multipart parsing, with a small allowance for multipart metadata; the endpoint
  then enforces the exact file-byte limit. Nginx permits 65 MiB so its request
  cap remains above the API file cap plus that metadata allowance. Large inserts
  use 5,000-row transactional batches.

## Flexible-import operations

- Treat mapping suggestions as assistance, not proof of business meaning.
  Ambiguous dates, totals, unit prices, discounts, customers, and order IDs must
  be confirmed by a person who understands the source.
- Ambiguous slash dates such as `01/02/2026` fail closed. Convert them upstream
  to ISO `YYYY-MM-DD` so the intended calendar date is auditable.
- Local ISO timestamps are reduced to their calendar date. Time-only,
  timezone-aware, localized, and bare-year values fail closed rather than being
  shifted or guessed.
- Use direct-revenue mode for an already calculated line total. Use
  quantity-and-unit-price mode only when those columns have their literal
  meanings. Never map a line total to unit price merely because its header says
  `sales` or `amount`.
- CSV and TSV inputs are UTF-8. `.xlsx` is the supported Excel format; legacy
  `.xls`, encrypted workbooks, macro-enabled workbooks, and unsafe or malformed
  ZIP packages are rejected. Workbook sheet, row, column, cell, and expanded-size
  limits supplement the compressed upload-byte limit.
- Formula cells are not evaluated by the service. Export calculated values or
  save cached results before import, and inspect the previewed values.
- Repeated, blank, or missing order IDs become deterministic unique row IDs and
  are reported as sales records rather than orders. A missing customer field
  becomes one `UNSPECIFIED-ENTITY`. Generated identifiers and default dimensions
  keep basic revenue and trend analysis available but make some order, customer,
  segmentation, or dimensional results unavailable or semantically weaker.
- Map any source currency-code column and ensure every row contains the selected
  `USD` or `GBP` code. Currency-like columns, inline currency markers, malformed
  numeric grouping, mixed currencies, and unsupported codes are rejected.
- Direct-revenue data without source quantity has no unit metric. The stored
  schema placeholder is excluded from KPIs, natural-language unit analysis, and
  anomaly features. `UNSPECIFIED-ENTITY` is likewise excluded from entity counts
  and RFM segmentation.
- One dataset is active at a time. Record the source file SHA-256, mapping,
  import summary, source currency, and Git commit when the dataset supports a
  business decision. Only USD and GBP source labels are supported, the active
  verified profile is authoritative for all rendered/API monetary labels, and
  the service never performs an exchange-rate conversion. Rows from a database
  created before profile metadata existed are preserved under a conservative
  unverified legacy profile. Their USD label is only a storage fallback; choose
  the display currency as needed and re-import the source before relying on
  currency or entity-sensitive results. Startup never infers that provenance
  from prepared-looking IDs or row shapes.
- Returns and negative sales are outside the canonical positive-sales contract
  and require an upstream preparation policy before import.

## Production checklist

- Replace local database credentials with a managed secret.
- Keep the PostgreSQL bootstrap administrator and API application credentials
  separate; verify the application role remains non-superuser after changes.
- Set a long random API key for a single-user deployment. Add identity-provider
  authentication, authorization, and tenant isolation before supporting users.
- Restrict CORS to the deployed dashboard origin.
- Terminate TLS at the hosting load balancer or reverse proxy.
- Replace the process-local limiter with a shared gateway limiter for replicas.
- Configure the trusted TLS edge to rate-limit and log by public client address;
  the origin intentionally treats that edge as one direct peer.
- Restrict the metrics endpoint and retain structured access logs.
- At the public edge, allow only the health probe path required by the platform;
  keep `/metrics` on the monitoring network even though the origin rate-limits it.
- Add upload malware scanning when accepting files from untrusted users.
- Schedule database backups and restoration drills.
- Alert on latency and error metrics, then extend monitoring to data quality and
  model drift once predictions are used in a business workflow.
- Follow the release and verification procedure in `docs/deployment.md`.
