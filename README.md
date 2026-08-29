# Enterprise AI Business Intelligence Agent

A portfolio-level, end-to-end business intelligence platform that turns sales
data into validated analytics, evaluated machine-learning outputs, and grounded
executive insights.

The project implements the supplied enterprise AI BI plan as a working MVP. It
is intentionally usable without an LLM key: specialist agents call approved
analytics and ML tools and expose the evidence behind every conclusion.

## What is included

- CSV ingestion, normalization, data-quality checks, and database loading
- KPI cards, trends, ranked product analysis, date/region/category/product
  filters, and regional drill-down
- Source-currency display for USD and GBP datasets without implicit FX conversion
- Revenue forecast candidate selection with chronological holdout MAE and RMSE
- RFM customer segmentation with K-Means
- Sales-record anomaly detection with Isolation Forest
- Grounded Data Analyst, Forecasting, Customer Intelligence, Anomaly Detection,
  and Executive agents
- Bounded English/Chinese business questions with read-only query plans,
  chart-ready evidence, explanations, and tool provenance
- FastAPI backend and responsive React dashboard
- SQLite for zero-configuration local use and PostgreSQL in Docker Compose
- Optional API-key protection, bounded rate limiting, request tracing, JSON access
  logs, readiness checks, and Prometheus-compatible metrics
- Pytest, Ruff, GitHub Actions, CodeQL, container builds, dependency updates, and
  an English changelog gate

![Enterprise AI BI dashboard overview](docs/assets/dashboard-overview.png)

## Architecture at a glance

```mermaid
flowchart LR
    S[CSV / public datasets / demo] --> V[Validation and transformation]
    V --> D[(PostgreSQL / SQLite)]
    D --> B[Shared business snapshot]
    B --> A[Analytics and filters]
    B --> M[Forecasting / RFM / anomalies]
    A --> Q[Approved NL query planner]
    A --> G[Grounded specialist agents]
    M --> G
    Q --> API[FastAPI]
    G --> API
    API --> UI[Interactive React dashboard]
```

## Quick start with Docker

```bash
docker compose up --build
```

Open the dashboard at <http://localhost:5173> and API documentation at
<http://localhost:8000/docs>. Select **Load demo data** to seed a deterministic
portfolio dataset.

For a same-origin, hardened single-host profile, follow the
[production deployment guide](docs/deployment.md). The profile exposes only the
Nginx dashboard and keeps PostgreSQL and FastAPI on an internal network.

## Local development

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn backend.app.main:app --reload --env-file .env
```

Frontend, in a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

The default database is `sqlite:///./enterprise_ai_bi.db`. Copy `.env.example`
to `.env` to override backend settings. When changing `API_KEY_HEADER`, keep
`frontend/.env.local`'s `VITE_API_KEY_HEADER` identical; the production Compose
build passes the same value automatically.

## Code organization

- `backend/app/api/` contains small domain routers; `main.py` only builds and
  configures the FastAPI application.
- `BusinessIntelligence` is a request-scoped facade. It materializes one sales
  snapshot and shares it across analytics, ML specialists, and executive
  reporting instead of repeating the database-to-DataFrame conversion.
- Validation, ingestion, forecasting, segmentation, and anomaly detection use
  configurable service classes. The original functions remain as stable
  compatibility wrappers.
- `frontend/src/api/`, `hooks/`, `components/`, and `utils/` separate transport,
  state orchestration, presentation, and formatting from the page layout.
- M5 candidate and selection records use explicit dataclasses while generated
  training artifacts remain outside version control.

## Upload schema

CSV files must contain:

| Column | Meaning |
| --- | --- |
| `order_id` | Unique order identifier |
| `order_date` | ISO date or another pandas-readable date |
| `customer_id` | Customer identifier |
| `region` | Sales region |
| `category` | Product category |
| `product` | Product name |
| `quantity` | Positive integer |
| `unit_price` | Non-negative amount |
| `discount` | Decimal between 0 and 1 |

Revenue is derived server-side as
`quantity * unit_price * (1 - discount)` so uploaded totals cannot override the
calculation.

## Walmart M5 workflow

The M5 pipeline consumes the official `calendar.csv`, `sell_prices.csv`, and
`sales_train_evaluation.csv` files. It verifies the University of Nicosia
Zenodo v1 sizes and MD5 checksums before processing. Obtain and use the files
only after reviewing the original Kaggle competition rules.

```powershell
python scripts/run_m5_pipeline.py `
  --data-dir C:\path\to\m5\raw `
  --output-dir C:\path\to\m5\artifacts `
  --stage all
```

All 30,490 item-store series and 1,941 observed days participate in revenue and
unit aggregation. The prepared store-category grain contains 30 series and is
small enough for this portfolio API. The training stage uses the 28 days before
the final holdout to select a global model and calibrate a seasonal blend. It
then refits the selected model and evaluates it once on the final 28 observed
days. The current selected model is a 300-tree Extra Trees regressor with 28
calendar, hierarchy, lag, rolling, event, SNAP, and lagged-price features.
Reported metrics are a one-step project holdout evaluation, not the
competition's official WRMSSE.

Generated data and model files are intentionally excluded from Git. The
`m5_application_sales.csv` output can be uploaded through the standard API;
M5 stores act as customer proxies because the source contains no shoppers. Its
generated IDs are store-category-day records, not orders, so record count and
average record value are not order count or average order value. The dashboard
detects the M5, UCI, and Iowa generated-ID prefixes and changes these labels and
natural-language caveats accordingly. The application export is passed through
the same canonical upload validator used by the API, including its two-decimal
unit-price precision. `m5_preparation_summary.json` records `application_rows`,
`application_revenue`, and `revenue_reconciliation_delta` so the effect of that
precision is explicit and auditable.

## UCI and Iowa public-sales workflows

The public-sales pipeline downloads, verifies, cleans, aggregates, and analyzes
two additional official datasets:

- UCI Online Retail II, a 2009-2011 UK online retailer transaction workbook.
- Iowa Liquor Sales, 2024, the complete five-part calendar-year export.

```powershell
python -m scripts.run_public_sales_pipeline `
  --source uci `
  --data-dir C:\path\to\public-sales\raw\uci `
  --output-dir C:\path\to\public-sales\artifacts\uci `
  --stage all

python -m scripts.run_public_sales_pipeline `
  --source iowa `
  --data-dir C:\path\to\public-sales\raw\iowa `
  --output-dir C:\path\to\public-sales\artifacts\iowa `
  --stage all
```

Downloads are atomic and every preparation summary records the source URL,
byte size, SHA-256, cleaning counts, output grain, source revenue, application
revenue, and rounding reconciliation. The UCI output is denominated in GBP;
the Iowa output is denominated in USD. Do not combine the two monetary series
without an explicit exchange-rate policy. Raw and generated files remain
outside version control. See the [verified run report](docs/public-sales-datasets.md)
for exact results, licenses, caveats, and artifact contracts.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /api/data/demo` | Replace current data with deterministic demo records |
| `POST /api/data/upload` | Validate and ingest a CSV file |
| `GET /api/analytics/filter-options` | Available dates and business dimensions |
| `GET /api/dashboard` | One-snapshot dashboard analytics and optional ML results |
| `GET /api/analytics/kpis` | Core portfolio KPIs |
| `GET /api/analytics/trends` | Monthly or daily revenue trend |
| `GET /api/analytics/breakdown/{dimension}` | Region/category/product analysis |
| `GET /api/ml/forecast` | Forecast plus evaluation metrics |
| `GET /api/ml/segments` | RFM customer segments |
| `GET /api/ml/anomalies` | Ranked anomalous sales records |
| `POST /api/insights/query` | Grounded natural-language analysis |
| `GET /api/reports/executive` | Evidence-backed executive report |

Analytics and ML endpoints accept optional `start_date`, `end_date`, `region`,
`category`, and `product` query parameters. The dashboard applies one filter
contract to its KPIs, charts, ML outputs, and natural-language evidence.
The same query parameters can scope the executive report endpoint.
The bundled dashboard route reads one filtered snapshot instead of loading the
sales table once per card. Date and dimensional filters are applied by the
database before rows are converted for analytics. If a narrow selection is too
small for forecasting, segmentation, or anomaly detection, core KPIs and charts
still return with a model-specific explanation.

Example bounded questions include:

- `Top 5 products by revenue in the latest 3 months`
- `Monthly orders for 2024`
- `2024 年前 10 個地區的銷售額`
- `Why did revenue change in the latest month?`

The first three compile to an enumerated, read-only analytical plan and return
chart data. Change explanations, forecasts, customer intelligence, anomalies,
and executive summaries route to grounded specialist tools. SQL text and data
mutation requests are rejected before execution.

Set `currency` to `USD` or `GBP` in the insight request body, or use the same
query parameter on the executive report. This changes source-currency labels
only and never performs an implicit exchange-rate conversion.

![Natural-language BI query plan and chart evidence](docs/assets/natural-language-insight.png)

## Quality and update policy

Run all checks before committing:

```bash
ruff check .
pytest --cov=backend --cov=data_pipeline --cov=ml
cd frontend && pnpm build
```

Every meaningful update must add an English entry to `CHANGELOG.md`. Pull
requests are blocked by CI when implementation files change without a changelog
update. See `CONTRIBUTING.md` for the exact workflow.

## Architecture and security

- [Architecture](docs/architecture.md)
- [Project completion and portfolio guide](docs/project-completion.md)
- [Production deployment](docs/deployment.md)
- [Public sales datasets](docs/public-sales-datasets.md)
- [Security model](SECURITY.md)
- [Contribution workflow](CONTRIBUTING.md)
