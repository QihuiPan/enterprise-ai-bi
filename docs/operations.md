# Operations Guide

## Health, metrics, and first data load

- `GET /health/live` verifies that the API process is responding.
- `GET /health/ready` and the backwards-compatible `GET /health` verify database
  connectivity and return HTTP 503 when the service is not ready for traffic.
- `GET /metrics` exports aggregate HTTP counters, duration sums, and the current
  in-flight request count in Prometheus text format.
- `POST /api/data/demo` replaces existing rows with a deterministic dataset.
- `POST /api/data/upload?replace=true` validates and replaces the current data.
- Append uploads are deliberately disabled so validation always covers the full
  analytical snapshot rather than two independently valid but unsafe totals.

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
  loaded. Large inserts use 5,000-row transactional batches.

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
