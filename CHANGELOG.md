# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows semantic versioning after its first release.

Every meaningful code, configuration, documentation, or infrastructure update
must include an English entry under `Unreleased` before it is committed.

## [Unreleased]

### Added

- Added reproducible UCI Online Retail II and Iowa Liquor Sales 2024 pipelines
  with atomic official-source downloads, SHA-256 provenance, schema adapters,
  source-aware cleaning, scalable aggregation, application CSVs, revenue
  reconciliation summaries, forecast analysis, tests, and an audited run report.
- Added a Walmart M5 pipeline that verifies the University of Nicosia archive,
  aggregates all 59 million item-day values to store-category daily records,
  exports an application-compatible CSV, and trains a global gradient-boosted
  holdout model with seasonal-naive benchmark metrics.
- Recorded the first verified M5 training run, temporal split, benchmark
  comparison, and end-to-end application validation results.
- Initial enterprise AI business intelligence MVP repository structure.
- CSV ingestion with schema validation, transformation, and relational storage.
- KPI, trend, dimensional breakdown, and revenue change analytics services.
- Revenue forecasting, RFM customer segmentation, and anomaly detection models.
- Grounded specialist-agent orchestration and executive report generation.
- FastAPI endpoints, React dashboard, Docker Compose, automated tests, and CI.
- Architecture, security, contribution, and operating documentation.

### Changed

- Batched relational sales ingestion in 5,000-row transactions and raised the
  Docker upload limit to 64 MiB so the prepared Iowa annual dataset can be
  loaded without materializing hundreds of thousands of ORM objects at once.
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
