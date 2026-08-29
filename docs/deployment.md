# Production Deployment Guide

## Deployment boundary

The production profile packages PostgreSQL, the FastAPI service, and the React
dashboard behind one Nginx origin. It is suitable for a single-host portfolio
deployment or as a reference topology for a managed container platform. The
repository does not contain cloud credentials, a domain, or TLS private keys.

## Required configuration

Copy `.env.production.example` to an untracked `.env.production` file and set:

- separate long random `POSTGRES_ADMIN_PASSWORD` and `DATABASE_PASSWORD` values;
- an `API_KEY` of at least 32 random characters for protected business endpoints;
- the exact HTTPS dashboard origin in `CORS_ORIGINS`;
- `APP_PORT` if the host does not use port 8080.
- `BIND_ADDRESS` only when traffic must arrive from another host; the secure
  default binds the dashboard to `127.0.0.1` for a same-host TLS proxy.

If `API_KEY_HEADER` is changed, the production dashboard image is rebuilt with
the same header name automatically through the Compose build argument.

Never commit the populated environment file. A hosted deployment should inject
the same values from its secret manager. The production Compose profile refuses
to resolve when either database password, the API key, or CORS allowlist is
empty. The application also refuses to start in production with an API key under
32 characters, wildcard CORS, or entries that are not exact HTTP(S) origins.
The API receives database credentials as separate fields and constructs the
SQLAlchemy URL safely, so URL-reserved characters do not need URL encoding. A
Compose `.env` file still applies interpolation to unquoted and double-quoted
values: wrap a password containing `$` in single quotes, or inject it directly
from the hosting secret manager, so Compose preserves the literal value.

## Start and verify

```powershell
docker compose --env-file .env.production `
  -f docker-compose.production.yml up -d --build

docker compose --env-file .env.production `
  -f docker-compose.production.yml ps
```

The dashboard is available on `http://localhost:8080` by default. Nginx serves
the static application and proxies `/api`, `/health`, and `/metrics` to the API,
so an internet deployment needs only one public origin.

Verification endpoints:

- `GET /health/live` checks the application process without a database query.
- `GET /health/ready` checks database connectivity and returns HTTP 503 when
  the service should be removed from traffic.
- `GET /metrics` returns Prometheus-compatible request counters, duration sums,
  and an in-flight request gauge.

## Security controls

When `API_KEY` is non-empty, every `/api/*` request requires the configured
header (default `X-API-Key`). Health, documentation, metrics, and CORS preflight
routes remain unauthenticated. The API compares keys in constant time.
Every `/api` response also carries `Cache-Control: no-store`, including rejected
authentication and rate-limit responses. Configure every public edge, reverse
proxy, and CDN to bypass caching for `/api` and to preserve this header; an API
key does not make shared caching of business responses safe.

The process-local rate limiter is intended for a single demo instance. For
multiple replicas, replace it with a shared gateway or Redis-backed limiter.
In the protected production profile, authentication runs before rate limiting,
and valid requests share a quota keyed to the configured API key. Rejected
anonymous requests therefore cannot exhaust the authenticated user's bucket.
Nginx also applies a small direct-peer origin cap before authentication. Behind
a TLS proxy, that peer is the proxy rather than the public client, so this cap is
deliberately not described as a per-client control. The trusted public edge must
apply per-client rate limits and retain authoritative client-address logs; the
origin continues to overwrite untrusted forwarding chains. A multi-replica or
internet-scale deployment requires the edge gateway's shared limiter.
Nginx supplies a strict content security policy plus content-type, framing,
referrer, and browser-permission headers; an external load balancer or reverse
proxy must terminate TLS and may restrict the metrics route to an operations
network. When that trusted proxy sends `X-Forwarded-Proto: https`, Nginx preserves
only that sanitized HTTPS value; all other values fall back to its local scheme.
The bundled origin applies a separate, probe-friendly source limit to health and
metrics routes. At the public edge, allow `/metrics` only from the monitoring
network and expose only the liveness or readiness route the platform actually
uses.

The API image runs as an unprivileged user and the production Compose profile
uses a read-only root filesystem with a temporary `/tmp` mount. Database and API
containers are not published directly to the host. PostgreSQL is isolated on an
internal database-only network; only the API joins both database and application
networks. A one-shot initialization service creates or rotates a dedicated,
non-superuser application role. The API never receives the PostgreSQL bootstrap
administrator credential.

## Logging and request tracing

Every response that enters FastAPI's request-context middleware carries
`X-Request-ID`. A valid caller-supplied request ID is
preserved through Nginx; otherwise Nginx or the API generates one. The internal
API process trusts forwarded client headers only in the production Compose
profile, where it is unreachable from the host network. Nginx overwrites any
caller-supplied forwarded-address chain with its direct peer address before
proxying. With a TLS edge, the API log therefore records the edge peer; use the
edge log as the authoritative public client record. Access events are emitted as
single-line JSON with method, route, status, duration, client address, and
request ID. Container platforms can ship stdout to their log service without a
custom formatter.

## Backup and recovery

Create encrypted, access-controlled PostgreSQL backups from the operator host.
For example, use `pg_dump` through the production Compose project and write its
stdout to a protected backup file. Test every recovery procedure against a
separate database before relying on it. Do not restore over the live database
without a maintenance window and a verified rollback copy.

## Public deployment handoff

Before exposing the stack publicly:

1. Provision a host or container service and a managed DNS name.
2. Store database and API secrets in the platform secret manager.
3. Terminate TLS and redirect HTTP to HTTPS.
4. Keep the origin port on loopback for a same-host proxy. When a cloud load
   balancer requires `BIND_ADDRESS=0.0.0.0`, restrict the host firewall or
   security group so only that load balancer can reach the origin port.
5. Set a production-only CORS allowlist.
6. Connect `/metrics` and JSON logs to monitoring and alerting.
7. Schedule encrypted backups and perform a restoration drill.
8. Run the CI, container build, health, upload, analytics, and agent smoke tests
   against the release candidate.

Publishing the application itself requires access to the selected cloud account
and domain; those credentials are deliberately outside the repository.
