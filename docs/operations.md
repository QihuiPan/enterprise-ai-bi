# Operations Guide

## Health and first data load

- `GET /health` verifies that the API process is responding.
- `POST /api/data/demo` replaces existing rows with a deterministic dataset.
- `POST /api/data/upload?replace=true` validates and replaces the current data.

## Backups

For Docker deployments, back up PostgreSQL with `pg_dump` from a controlled
operator environment. Test restoration to a separate database before relying on
the backup. SQLite development databases are disposable and are ignored by Git.

## Model operations

Model outputs are trained on demand from the current analytical dataset. Record
the data window, evaluation metrics, application commit, and configuration when
promoting an output to a business process. Do not interpret anomaly flags as
confirmed fraud and do not present forecast intervals as guaranteed bounds.

### Walmart M5

- Keep raw M5 files and generated artifacts outside the repository.
- Run `scripts/run_m5_pipeline.py --stage all` to verify, prepare, train, and
  evaluate the store-category model.
- Archive `m5_preparation_summary.json`, `m5_training_metrics.json`, the Git
  commit, and the source DOI together for reproducibility.
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
- Configure authentication and tenant isolation.
- Restrict CORS to the deployed dashboard origin.
- Add TLS, request rate limits, audit logging, and upload malware scanning.
- Schedule database backups and restoration drills.
- Add observability for latency, errors, data quality, and model drift.
