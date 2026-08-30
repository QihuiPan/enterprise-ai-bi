# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows semantic versioning after its first release.

Every meaningful code, configuration, documentation, or infrastructure update
must include an English entry under `Unreleased` before it is committed.

## [Unreleased]

### Added

- Added a stateless, bounded CSV, TSV, and XLSX sales-data import workflow with
  conservative column suggestions, explicit manual mapping, full-file
  validation, preview fingerprint enforcement, atomic data/profile activation,
  selected-sheet provenance, source-semantic warnings,
  dashboard guidance, and regression coverage while preserving the canonical
  CSV compatibility endpoint.
- Added reviewed prepared-profile choices for Walmart M5, UCI Online Retail II,
  and Iowa Liquor Sales 2024, with required mapping, entity, currency, and ID
  contract validation instead of implicit provenance detection.
- Added dataset-version binding across dashboard, filter-option, and profile
  responses so a concurrent replacement is retried instead of mixing snapshots.
- Added persisted source-currency, observed-unit, entity-grain, selected-sheet,
  anomaly-feature, and import-warning metadata so every dashboard reload keeps
  the activated dataset's analytical meaning and provenance.
- Added cross-dashboard date, region, category, and product filters, regional
  chart drill-down, source-currency formatting, and optional session-scoped API
  key controls backed by one reusable filter contract across analytics, ML,
  natural-language insights, and executive reports.
- Added an accessible top-product revenue chart and ranked evidence table to the
  dashboard so product analysis is visible without relying on API or NL BI use.
- Added a bounded English and Chinese natural-language BI planner for approved
  metrics, dimensions, periods, rankings, and trends, with read-only query
  plans, chart-ready evidence, explanations, policy rejection, and tests.
- Added calendar-quarter parsing for explicit, latest, and latest-complete
  business questions, including resolved calendar and observed data boundaries.
- Added a production Compose profile with a same-origin Nginx proxy, non-root
  and read-only API container, secret-driven API-key authentication, bounded
  rate limiting, liveness/readiness probes, request IDs, structured JSON access
  logs, Prometheus-compatible metrics, and deployment and recovery guidance.
- Added container-build and CodeQL workflows, Dependabot configuration, a
  roadmap acceptance matrix, portfolio demonstration guide, and resume-ready
  project description.
- Added PostgreSQL integration and production Compose smoke jobs, plus a tested
  changelog gate that requires a new English bullet under `Unreleased`.
- Updated CI and security scanning to current Node 24-based action releases and
  the verified pnpm 11 setup action.
- Granted CodeQL read-only access to private repository workflow metadata so
  analysis can report status without failing GitHub's integration permission check.
- Made the changelog gate decode Git output explicitly as UTF-8 so it runs
  reliably on Windows hosts with non-UTF-8 default subprocess encodings.
- Preserved CodeQL SARIF reports as Actions artifacts when the private repository
  plan does not expose Code Scanning, keeping analysis evidence without a false
  workflow failure from an unavailable Security-tab upload.
- Added reproducible UCI Online Retail II and Iowa Liquor Sales 2024 pipelines
  with atomic official-source downloads, SHA-256 provenance, schema adapters,
  source-aware cleaning, scalable aggregation, application CSVs, revenue
  reconciliation summaries, forecast analysis, tests, and an audited run report.
- Added a Walmart M5 pipeline that verifies the University of Nicosia archive,
  aggregates all 59 million item-day values to store-category daily records,
  exports an application-compatible CSV, and trains a global gradient-boosted
  holdout model with seasonal-naive benchmark metrics.
- Recorded the first verified M5 training run, temporal split, benchmark
  comparison, and canonical application-data validation results.
- Initial enterprise AI business intelligence MVP repository structure.
- CSV ingestion with schema validation, transformation, and relational storage.
- KPI, trend, dimensional breakdown, and revenue change analytics services.
- Revenue forecasting, RFM customer segmentation, and anomaly detection models.
- Grounded specialist-agent orchestration and executive report generation.
- FastAPI endpoints, React dashboard, Docker Compose, automated tests, and CI.
- Architecture, security, contribution, and operating documentation.

### Changed

- Made active dataset currency authoritative across the dashboard, grounded
  insights, and executive reports; importers can choose USD or GBP and map an
  optional per-row currency-code column, but cannot relabel or combine sources.
- Preserved source precision for flexibly mapped unit prices and discounts while
  keeping the established rounded canonical/public-pipeline output contract.
- Consolidated dashboard refreshes into one request-scoped sales snapshot,
  pushed date and dimensional predicates into SQL, selected only analytical
  columns, and replaced full-table filter-option loading with database-side
  distinct and date queries for large public datasets.
- Set PostgreSQL analytical sessions to repeatable-read isolation and documented
  complete-transaction retry behavior for concurrent writer conflicts.
- Preserved pre-profile databases under a conservative, currency-unverified
  legacy profile instead of inferring trusted public-dataset provenance from row
  shapes or IDs; SQLite and PostgreSQL startup now serialize that backfill.
- Made natural-language and executive-agent monetary text honor the selected
  USD or GBP source currency without implying exchange-rate conversion.
- Propagated a customized API-key header into the production dashboard build
  and documented the matching local frontend setting.
- Ordered API-key authentication before rate limiting, keyed protected traffic
  to the validated credential, trusted proxy headers only on the internal
  production API, preserved caller request IDs through Nginx, and enabled an
  explicit raw-JSON stdout access logger.
- Constructed the production database URL from separate credential fields so
  random passwords containing URL-reserved characters remain valid, and made
  Nginx overwrite untrusted forwarded-address chains before proxying internally.
- Split the production proxy/API and API/database networks, added a direct-peer
  pre-authentication origin cap, defaulted the origin port to loopback, and made
  example secrets empty so Compose fails closed until the operator supplies them.
- Upgraded general monthly forecasting from a linear-only implementation to
  chronological candidate selection across linear trend, recursive trailing
  mean, and seasonal-naive models, including per-candidate metrics and explicit
  improvement against the linear baseline.
- Excluded incomplete first and last observation months from the general
  dashboard forecaster, preserved explicit month-start aggregate inputs such as
  Iowa across KPI and model semantics, and returned the input grain and exclusions
  as model evidence.
- Re-ran the public-sales analysis artifacts with the upgraded forecaster. UCI
  selected the 12-month seasonal-naive candidate and reduced holdout RMSE by
  79.52% versus linear trend; Iowa retained linear trend on its 12-month history.
- Expanded the README and architecture, security, operations, deployment, and
  public-dataset documentation so implemented controls, evidence, limitations,
  and external hosting responsibilities are explicit.
- Clarified Compose password interpolation, FastAPI-only request tracing, and the
  browser session-key residual risk in the production handoff documentation.
- Batched relational sales ingestion in 5,000-row transactions and raised the
  Docker upload limit to 64 MiB so the prepared Iowa annual dataset can be
  loaded without materializing hundreds of thousands of ORM objects at once.
- Reconciled Walmart M5 application revenue through the canonical upload
  validator and recorded application rows, revenue, and precision delta in every
  preparation summary.
- Separated PostgreSQL bootstrap administration from a dedicated non-superuser
  API role, with an idempotent least-privilege initializer and CI assertion.
- Made each FastAPI application factory instance own its configured upload limit,
  database engine, session dependency, table lifecycle, and readiness probe.
- Excluded UCI's partial December 2011 period from forecast fitting and holdout
  evaluation while preserving it in descriptive dataset totals.
- Refactored and encapsulated the full application without changing public API
  behavior: split FastAPI routes by domain, introduced a request-scoped
  business facade that reuses one sales snapshot across analytics and agents,
  wrapped validation, ingestion, and ML algorithms in configurable services,
  typed M5 model candidates, and separated the React API, state, chart, list,
  formatting, and intelligence layers.
- Optimized Walmart M5 forecasting with a leakage-safe tuning window, 28
  seasonal and lagged-price features, candidate model selection, calibrated
  seasonal blending, a selected 300-tree Extra Trees model, and compressed
  model serialization. Final holdout WMAPE improved from 7.8140% to 7.5819%.
- Updated the dashboard to supported React, Recharts, Vite, and icon-library
  releases and explicitly allowed the required esbuild installation step.
- Refined FastAPI dependency annotations and code formatting to satisfy the
  repository's strict lint configuration.
- Expanded API integration coverage across every specialist agent, the ML
  endpoints, executive reporting, and invalid analytical dimensions.
- Removed test-suite deprecation warnings by adopting Starlette's supported
  `httpx2` client and explicit timedelta units.
- Excluded generated Python package metadata from version control.

### Fixed

- Explicitly excluded the repository-root pytest cache from ordinary Docker
  build contexts so generated test artifacts are not sent to the Docker daemon.
- Rejected ambiguous or timezone-shifting dates, malformed numeric/currency and
  percentage notation, mixed discount scales, mixed or hidden currency-code
  columns, ragged rows, Unicode header collisions, hostile XLSX dimensions, and
  changed-after-preview files before atomic activation.
- Bounded declared and chunked upload request bodies before multipart parsing,
  and bounded logical delimited records before CSV field lists are materialized.
- Aligned the Nginx request cap above the API file limit plus multipart overhead,
  and gated prepared-profile review on the exact canonical nine-column mapping.
- Kept each import response bound to the profile written by its own transaction
  and report a guided import as superseded if a newer activation wins before the
  dashboard refresh completes.
- Required complete prepared M5, UCI, and Iowa artifacts and rejected generic
  fallback dimensions before assigning their reviewed aggregate semantics, while
  documenting that profile selection is an operator assertion rather than digest
  authentication.
- Prevented generated quantity and unspecified entities from appearing as
  observed unit KPIs, anomaly features, customer counts, or RFM inputs, and made
  order/transaction/receipt plus customer/store/account labels source-aware.
- Returned a structured unavailable result for generic entity/entities questions
  when an imported dataset has no usable entity mapping.
- Preserved exact Excel identity values during mapping, sanitized lazy workbook
  parse failures, bounded physical worksheet extents, and returned UTC-qualified
  import timestamps.
- Guarded dashboard and insight updates by request generation, tracked concurrent
  loading correctly, and removed stale evidence immediately after data replacement.
- Rejected fractional, non-finite, derived-overflow, and database-overflow numeric
  values and non-finite dataset totals before ingestion instead of committing
  corrupted business facts.
- Bounded source prices and analytical snapshot revenue at high business-safe
  limits, disabled independently validated append uploads, and kept downstream
  KPI and ML serialization finite at supported extremes.
- Rejected normalized duplicate CSV headers and timezone-aware order dates as
  structured validation errors instead of raising server errors or shifting the
  source calendar day.
- Parsed external CSV fields as strings before canonical validation so leading
  zero identifiers and compact calendar dates cannot be silently coerced.
- Compared the original plan's last-quarter question with the latest two complete
  quarters, kept business uses of “drop” out of the SQL policy, and suppressed
  monthly percentages for incomplete observation windows.
- Resolved previous-month change questions against the two months ending in the
  requested prior month instead of silently comparing the latest month.
- Fixed next-quarter forecast answers to report all three monthly forecasts,
  their total, and explicitly scoped summed monthly residual ranges.
- Added deterministic first- and last-day records to the known complete demo
  window so period coverage, MoM KPIs, and forecast training use honest evidence.
- Kept ordinary sales-update questions in the approved analytics grammar while
  retaining explicit SQL mutation rejection.
- Disclosed ranked natural-language result truncation across answers, plans, charts,
  response schemas, evidence, and frontend visualization labels.
- Grounded executive recommendations only in available specialist evidence and
  exposed CSV upload from the empty dashboard state.
- Labeled natural-language result cards as agent responses instead of falsely
  presenting every approved analyst answer as an executive synthesis.
- Labeled UCI, Iowa, and M5 aggregate-record proxies explicitly in KPIs, the
  dashboard, natural-language answers, and dataset documentation instead of
  presenting generated artifact rows as source orders or average order value.
- Propagated aggregate-record and store semantics through navigation, product
  evidence, segmentation, anomaly agents, executive recommendations, and model
  caveats instead of reverting to customer, order, or transaction labels.
- Returned an explicit clarification for unknown metrics and unsupported change
  metrics instead of silently substituting revenue or a revenue-change analysis.
- Failed closed on compound metrics, unsupported qualifiers, grains and periods,
  unknown dimensions, non-revenue forecast targets, and mismatched segmentation
  or anomaly objects instead of routing them to a materially different analysis.
- Restricted forecast, segmentation, anomaly, executive, and change-explanation
  questions to explicit English and Chinese scope grammars, rejected ignored
  textual filters and unsupported horizons, and accepted concise CJK questions.
- Preserved literal CSV identity values such as `NA`, `N/A`, `NULL`, and `NaN`,
  rejected exact or canonical duplicate headers before pandas can rename them,
  and rejected PostgreSQL-unsafe NUL characters before database insertion.
- Fixed calendar-period completeness for filtered monthly aggregate datasets by
  requiring every expected month label before quarter or year comparisons and
  last-quarter queries can use a period.
- Added fail-closed `Cache-Control: no-store` protection to every business API
  response, including authentication and rate-limit rejections, and documented
  the matching edge and CDN cache-bypass requirement.
- Ran synchronous CSV parsing, validation, and large relational ingestion in
  FastAPI's worker pool so liveness requests remain responsive during Iowa-sized
  uploads.
- Pinned pnpm consistently across local, container, and CI builds; added a strict
  production CSP; routed local containers through the same-origin proxy; and
  removed duplicate plaintext Uvicorn access logs.
- Made the standalone dashboard image use its same-origin API proxy by default,
  matching its CSP and both Compose profiles.
- Required production API keys of at least 32 characters and rejected wildcard
  or malformed CORS origins before application startup.
- Bounded Prometheus HTTP-method labels to the standard method set plus `OTHER`
  so unauthenticated custom methods cannot grow metrics cardinality without limit.
- Added a separate probe-friendly Nginx rate limit for anonymous health and
  metrics routes and documented the required public-edge metrics ACL.
- Corrected the M5 evidence boundary to distinguish full-artifact canonical
  validation from the still environment-owned PostgreSQL artifact load.
- Clarified that Nginx limits the direct origin peer behind TLS termination and
  requires the trusted public edge to own per-client rate limiting and logging.
- Preserved only a sanitized HTTPS forwarding signal from a trusted TLS edge so
  application redirects do not downgrade behind the production proxy.
- Calculated average order value from order-level revenue totals instead of
  averaging line-item revenue, keeping KPI and natural-language results aligned.
- Enforced PostgreSQL text-length limits during CSV validation and returned
  structured HTTP 422 issues before production inserts can fail.
- Cleared stale natural-language evidence whenever demo loading or CSV upload
  replaces the active dataset.
- Returned evidence-backed specialist availability messages for narrow filters
  and let executive reports continue when individual analytical or ML minimum
  data requirements are not met.
- Reported month-over-month change as unavailable when a filter contains fewer
  than two monthly periods, and removed false trend direction and recommendation
  claims from the dashboard and executive report.
- Treated percentage change from a zero-revenue baseline as undefined while
  preserving absolute change evidence and a specific dashboard/report message.
- Required consecutive observed months for month-over-month claims and upgraded
  the dashboard runtime to the current Nginx 1.30.4 stable Alpine image.
- Kept KPI and analytical charts available when narrow filters provide too few
  rows for forecasting, segmentation, or anomaly detection, with an independent
  explanation on each unavailable model card.
- Excluded populated production environment files from Git and Docker build
  contexts, and corrected local startup guidance to load `.env` explicitly.
- Disclosed bounded natural-language trend truncation in answers, query plans,
  charts, and evidence, and prevented revenue-summary questions from being
  misrouted to the full executive-agent sequence.
- Aligned the GitHub Actions pnpm version with the lockfile generator so the
  frozen frontend dependency installation succeeds in CI.
- Included the pnpm workspace build-policy file in the dashboard Docker image so
  esbuild can be installed during container builds.
- Allowed both `localhost` and `127.0.0.1` dashboard origins during local
  development so browser responses are not blocked by CORS.
- Expanded the 24-month revenue chart across the dashboard grid to remove an
  unbalanced empty column on wide screens.
- Prevented long evidence-source labels from overflowing the mobile AI insight
  card and clipping the question form.
- Split charting and React dependencies into dedicated production chunks to
  keep the dashboard entry bundle small and cacheable.
