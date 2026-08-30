# Project Completion and Portfolio Guide

## Outcome

This repository implements the supplied Enterprise AI Business Intelligence
project plan as a deployable, evidence-grounded portfolio application. It joins
reproducible data pipelines, validated relational analytics, evaluated machine
learning, deterministic multi-agent orchestration, natural-language business
queries, a responsive dashboard, and production-oriented operations in one
system.

The target user is a manager or analyst who needs to load sales data, explore
performance, ask bounded business questions, inspect supporting evidence, and
generate or retrieve an executive summary through the API without trusting
unverified model claims.

## Roadmap acceptance matrix

| Plan phase | Implemented acceptance evidence | Repository status |
| --- | --- | --- |
| 0 — Planning and design | Problem statement, entities, API boundaries, architecture diagram, and technical decisions | Complete |
| 1 — Data engineering | Guided CSV/TSV/XLSX preview and mapping, canonical CSV and demo ingestion, full-file quality validation, atomic data/profile activation, PostgreSQL loading, batching, errors, and structured request logging | Complete |
| 2 — Analytics and SQL | Tested KPIs, trends, reusable dimensional analytics, filter options, and FastAPI endpoints | Complete |
| 3 — Dashboard | KPI cards, date/region/category/product filters, region drill-down, customer and product views, source-currency formatting, guided import review, and responsive React UI | Complete |
| 4 — Machine learning | Chronologically evaluated forecast candidates, M5 optimized model, RFM/K-Means segmentation, Isolation Forest anomalies, metrics, intervals, and APIs | Complete |
| 5 — Agent system | Five named roles, approved tools, orchestration, structured outputs, evidence provenance, and no-generated-SQL guardrails | Complete |
| 6 — Natural-language BI | Bounded English/Chinese query grammar, approved metrics/dimensions/periods, read-only query plans, chart-ready results, explanations, and policy rejection | Complete |
| 7 — Production engineering | Docker profiles, tests, CI, dependency automation, CodeQL, API key, rate limiting, health/readiness, metrics, deployment and portfolio documentation | Complete in repository |

Repository implementation and static configuration are complete. Runtime release
acceptance remains environment-owned: the first green container workflow after a
push, the selected cloud account and public URL, DNS/TLS, secret injection,
backup restoration, and monitoring integration. The production Compose profile
and `docs/deployment.md` define that handoff; a green GitHub Actions run and the
target-host checks are the runtime evidence rather than a source-code claim.

## Demonstration path

1. Start the local or production Docker profile and open the dashboard.
2. Load the deterministic demo data to establish a known baseline.
3. Apply a date, region, category, or product filter and verify every KPI, chart,
   segment, anomaly, and forecast refreshes from the same filtered snapshot.
4. Select a regional bar to demonstrate drill-down, then reset the filters.
5. Ask a bounded question such as `Top 5 products by revenue in the latest 3
   months` and inspect its read-only plan, explanation, chart, and evidence.
6. Ask for a forecast, customer segmentation, anomaly review, and executive
   summary to show specialist routing and grounded multi-agent synthesis.
7. Import a differently shaped CSV, TSV, or XLSX sales file by reviewing the
   suggested mapping, correcting one field, and activating it. Show that preview
   does not replace the active data and that the dataset profile records its
   source, mapping, generated/default fields, warnings, and SHA-256.
8. Upload a prepared M5, UCI, or Iowa artifact, choose its named prepared profile,
   and explain the validated currency, entity/record grain, source hash, cleaning
   contract, reconciliation, and model evaluation.
9. Show readiness, request metrics, structured logs, and the GitHub Actions
   checks as production-engineering evidence.

## Engineering decisions worth discussing

- A request-scoped business facade materializes one validated sales snapshot so
  multiple specialists do not repeat relational reads.
- Revenue is derived from quantity, unit price, and discount when those facts
  are mapped. Flexible direct-revenue imports preserve the explicitly mapped
  line total through the same canonical validation and report that choice in the
  dataset profile.
- Flexible preview is stateless, bounded, and non-mutating. Activation performs
  full mapped validation and commits data and semantics together so a failed input
  cannot partially replace the analytical snapshot.
- Natural-language requests compile to an enumerated in-memory analytics plan;
  arbitrary SQL and database mutations never reach the execution layer.
- Forecast candidates are selected on chronological holdouts and keep the
  explainable linear trend as an explicit benchmark.
- M5 model selection and blend calibration use a tuning horizon before the final
  holdout, which keeps the reported evaluation isolated from model selection.
- Public-source pipelines record official URLs, cryptographic hashes, cleaning
  counts, output grain, and revenue reconciliation so results can be reproduced.
- Local defaults remain frictionless, while the production profile adds a
  same-origin reverse proxy, secret-driven authentication, bounded rate limits,
  non-root containers, readiness probes, request tracing, and metrics.

## Known boundaries

- The dashboard currency selector labels values in the loaded dataset's source
  currency; it does not perform foreign-exchange conversion or combine monetary
  sources.
- The API key and process-local limiter suit a single-instance portfolio demo,
  not multi-user authorization or multi-replica enforcement.
- Forecast intervals describe observed holdout residual spread and are neither
  causal guarantees nor business commitments.
- Anomaly scores rank records for investigation; they are not fraud labels.
- Raw public datasets and trained artifacts remain outside Git because of size,
  redistribution, and reproducibility concerns.
- Flexible import supports tabular positive-sales facts, not arbitrary business
  domains. Returns or negative sales, non-UTF-8 text files, legacy or
  macro-enabled Excel files, encrypted workbooks, currencies other than USD/GBP,
  and implicit foreign-exchange conversion require an upstream preparation step.

## Resume-ready description

**Enterprise AI Business Intelligence Platform — Python, FastAPI, PostgreSQL,
scikit-learn, React, and Docker**

- Designed and built an end-to-end business intelligence platform integrating
  reproducible data pipelines, relational analytics, evaluated machine learning,
  and evidence-grounded multi-agent workflows.
- Developed leakage-aware forecasting, RFM customer segmentation, anomaly
  ranking, interactive analytics, and bounded natural-language BI with auditable
  query plans and chart-ready evidence.
- Productionized the application with container health checks, API-key controls,
  rate limiting, structured logs, Prometheus metrics, automated tests, container
  builds, dependency updates, and static security analysis.
