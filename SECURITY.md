# Security

## Reporting

Do not open a public issue for a suspected vulnerability. Report it privately
to the repository owner with reproduction steps and impact.

## Implemented controls

- Natural-language questions never execute generated SQL.
- Agents can call only registered, read-only analytical tools.
- Uploads have a configurable size limit and a strict required schema.
- Revenue is derived by the server instead of trusted from uploaded files.
- Database credentials and frontend API URLs are supplied through environment
  variables and are not committed.
- Business API routes can require a deployment-provided API key. Comparisons use
  a constant-time primitive, and the browser stores an optional key only in the
  current browser session.
- A bounded, process-local request limiter protects business API routes in the
  single-instance portfolio deployment. Authentication precedes the limiter,
  so rejected requests cannot consume the authenticated API-key quota.
- Nginx applies a separate source-address limit before authentication so invalid
  keys cannot create an unbounded 401 flood against the internal API.
- FastAPI responses carry request identifiers, access events are emitted as one
  structured JSON line, and a Prometheus-compatible endpoint exposes aggregate
  request metrics.
- The production dashboard sets a restrictive content security policy. A session
  API key remains readable by same-origin JavaScript, so preventing and promptly
  patching any future script-injection vulnerability is still required.
- Production containers run the API as an unprivileged user with a read-only
  root filesystem; PostgreSQL and FastAPI are reachable only on the internal
  Compose network. Only that internal production profile trusts Nginx forwarded
  client headers, and PostgreSQL is isolated on a separate internal network. The
  API uses a dedicated non-superuser database role and never receives bootstrap
  administrator credentials.
- Production startup rejects API keys shorter than 32 characters, wildcard CORS,
  and malformed origin allowlists.
- GitHub dependency updates, container builds, and CodeQL scanning are configured.
- API errors avoid returning stack traces to clients.

## Deployment limitations

The API-key control is appropriate for a single-user portfolio deployment; it
is not user identity, authorization, or tenant isolation. The in-memory limiter
is local to one process and must be replaced by a gateway or shared store when
running multiple replicas. Metrics do not expose business values, but their
route should still be restricted to an operations network in a public deployment.

Before an internet-facing deployment, inject secrets through the hosting
platform, use an exact CORS allowlist, terminate TLS, restrict metrics, schedule
encrypted backups, and test restoration. A multi-user deployment also requires
identity-provider integration, role-based authorization, tenant isolation, and
a shared rate limiter. Because the origin rejects caller-supplied forwarding
chains, the trusted TLS edge must provide authoritative per-client rate limiting
and access logs.
