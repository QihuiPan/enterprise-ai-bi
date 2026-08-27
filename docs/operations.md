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

## Production checklist

- Replace local database credentials with a managed secret.
- Configure authentication and tenant isolation.
- Restrict CORS to the deployed dashboard origin.
- Add TLS, request rate limits, audit logging, and upload malware scanning.
- Schedule database backups and restoration drills.
- Add observability for latency, errors, data quality, and model drift.
