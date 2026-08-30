# Security

## Reporting

Do not open a public issue for a suspected vulnerability. Report it privately
to the repository owner with reproduction steps and impact.

## Implemented controls

- Natural-language questions never execute generated SQL.
- Agents can call only registered, read-only analytical tools.
- Uploads have configurable byte and tabular-complexity limits. CSV/TSV inputs
  use a bounded UTF-8 parser; XLSX packages are screened for unsafe expansion,
  unsupported encryption/macros, workbook complexity, and malformed content.
  Declared and chunked request bodies are bounded before multipart parsing can
  spool an oversized upload, and the endpoint separately enforces exact file size.
- Flexible imports expose conservative mapping suggestions but require an
  explicit mapping and full-file validation before activation. Preview never
  mutates active data.
- Quantity-and-unit-price revenue is derived by the server. Direct-revenue mode
  is accepted only when explicitly selected and is normalized through the same
  canonical validation and safety limits.
- Monetary fields use anchored numeric parsing and source-currency enforcement.
  Obvious currency-code columns must be mapped, every row must agree on USD or
  GBP, and verified active-profile currency cannot be overridden by
  insight/report calls. Pre-profile database rows are backfilled as explicitly
  unverified and remain operator-selectable until their source is re-imported.
- Prepared public-dataset profiles are explicit, validate required mappings,
  complete artifact coverage, entity/dimension presence, currency, and
  generated-ID contracts. New imports are never inferred from attacker-controlled
  IDs, and legacy rows are never granted trusted currency provenance from shape
  or IDs. Parallel dashboard responses are accepted only when their stored
  dataset hashes, profile hashes, and currencies match.
- Prepared profiles are an authenticated operator assertion plus strict structural
  validation; they are not cryptographic authentication of a known artifact.
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
  Because this private repository's current account plan does not expose GitHub
  Code Scanning, each CodeQL matrix job retains its SARIF report as a 14-day
  Actions artifact instead of attempting an unavailable Security-tab upload.
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
