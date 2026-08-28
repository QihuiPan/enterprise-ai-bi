# Enterprise AI Business Intelligence Agent

A portfolio-level, end-to-end business intelligence platform that turns sales
data into validated analytics, evaluated machine-learning outputs, and grounded
executive insights.

The project implements the supplied enterprise AI BI plan as a working MVP. It
is intentionally usable without an LLM key: specialist agents call approved
analytics and ML tools and expose the evidence behind every conclusion.

## What is included

- CSV ingestion, normalization, data-quality checks, and database loading
- KPI cards, trends, and region/category/product breakdowns
- Revenue forecasting with holdout MAE and RMSE
- RFM customer segmentation with K-Means
- Transaction anomaly detection with Isolation Forest
- Grounded Data Analyst, Forecasting, Customer Intelligence, Anomaly Detection,
  and Executive agents
- Natural-language business questions with evidence and tool provenance
- FastAPI backend and responsive React dashboard
- SQLite for zero-configuration local use and PostgreSQL in Docker Compose
- Pytest, Ruff, GitHub Actions, health checks, and an English changelog gate

## Quick start with Docker

```bash
docker compose up --build
```

Open the dashboard at <http://localhost:5173> and API documentation at
<http://localhost:8000/docs>. Select **Load demo data** to seed a deterministic
portfolio dataset.

## Local development

Backend:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

The default database is `sqlite:///./enterprise_ai_bi.db`. Copy `.env.example`
to `.env` to override settings.

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
M5 stores act as customer proxies because the source contains no shoppers.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /api/data/demo` | Replace current data with deterministic demo records |
| `POST /api/data/upload` | Validate and ingest a CSV file |
| `GET /api/analytics/kpis` | Core portfolio KPIs |
| `GET /api/analytics/trends` | Monthly or daily revenue trend |
| `GET /api/analytics/breakdown/{dimension}` | Region/category/product analysis |
| `GET /api/ml/forecast` | Forecast plus evaluation metrics |
| `GET /api/ml/segments` | RFM customer segments |
| `GET /api/ml/anomalies` | Ranked anomalous transactions |
| `POST /api/insights/query` | Grounded natural-language analysis |
| `GET /api/reports/executive` | Evidence-backed executive report |

## Quality and update policy

Run all checks before committing:

```bash
ruff check .
pytest --cov=backend --cov=data_pipeline --cov=ml
```

Every meaningful update must add an English entry to `CHANGELOG.md`. Pull
requests are blocked by CI when implementation files change without a changelog
update. See `CONTRIBUTING.md` for the exact workflow.

## Architecture and security

- [Architecture](docs/architecture.md)
- [Security model](SECURITY.md)
- [Contribution workflow](CONTRIBUTING.md)
