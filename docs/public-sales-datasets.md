# Public Sales Dataset Pipelines

## Sources and usage

The UCI adapter uses the official Online Retail II archive and DOI. The source
contains 1,067,371 transactions from December 1, 2009 through December 9, 2011
and is licensed under CC BY 4.0.

- Dataset: <https://archive.ics.uci.edu/dataset/502/online+retail+ii>
- DOI: <https://doi.org/10.24432/C5CG6D>

The Iowa adapter uses the official calendar-year 2024 export published by the
Iowa Alcohol Operations Bureau. Its five CSV parts cover January 1 through
December 31, 2024 and are licensed under CC BY 4.0.

- Dataset: <https://data.iowa.gov/catalog/dataset/1261>
- Download API: <https://idh-be.iowa.gov/api/v1/datasets/1261/rows.csv>

Attribution and license review remain required before redistributing derived
data. This repository commits the preparation code and run report, not the raw
or generated datasets.

## Preparation contracts

`UCIOnlineRetailPreparer` accepts both historical workbook column conventions.
It removes cancellation invoices, non-positive or fractional quantities,
negative or invalid prices, invalid dates, missing customers, and missing
countries. Valid lines are aggregated to customer-country-day records for the
application. This retains customer and geographic analysis while reducing the
file from more than one million source rows to a dashboard-sized artifact.

`IowaLiquorSalesPreparer` streams every CSV member in the official archive. It
keeps valid 2024 rows with a store, a positive integer bottle count, and
non-negative sales dollars. Valid lines are aggregated to
store-county-category-month records. Missing county or category labels receive
explicit fallback values.

Both adapters derive an application unit price as aggregate revenue divided by
aggregate quantity. The application schema stores prices to two decimals, so a
small, explicitly reported reconciliation delta is expected. Order identifiers
are deterministic within each generated artifact.

## Verified run on August 28, 2026

| Measure | UCI Online Retail II | Iowa Liquor Sales 2024 |
| --- | ---: | ---: |
| Download bytes | 45,622,418 | 551,568,920 |
| Source rows | 1,067,371 | 2,590,975 |
| Valid rows | 805,620 | 2,587,992 |
| Prepared rows | 33,112 | 438,528 |
| Customer entities | 5,881 customers | 2,161 stores |
| Regions | 41 countries/regions | 100 counties |
| Categories | 1 | 44 |
| Units | 10,720,921 | 31,422,333 bottles |
| Source revenue | GBP 17,743,429.18 | USD 447,680,781.92 |
| Application revenue | GBP 17,743,736.81 | USD 447,680,161.85 |
| Rounding delta | GBP +307.63 | USD -620.07 |

Verified source hashes:

- UCI: `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`
- Iowa: `b750f8bb1d9f629c738427f24ea2c7b6629842f9102ac9a88f0226ebf82549f5`

The analysis stage uses the existing linear monthly revenue baseline. UCI
excludes partial December 2011 from model fitting and reports a five-month
holdout MAE of GBP 238,289.51 and RMSE of GBP 280,314.31. Iowa uses all twelve
months and reports a three-month holdout MAE of USD 3,703,899.62 and RMSE of
USD 3,898,586.44. These are project holdout diagnostics, not causal forecasts
or guaranteed future performance.

## Artifacts

Each source produces three ignored artifacts:

- `<source>_application_sales.csv`: validated nine-column application input.
- `<source>_preparation_summary.json`: provenance, quality, and reconciliation.
- `<source>_analysis.json`: KPI totals, forecast inputs, evaluation, and output.

The verified UCI application CSV is approximately 3.4 MB. The verified Iowa
application CSV is approximately 45.6 MB and fits under the Docker profile's
64 MiB upload limit. Loading either file replaces the current dataset when the
upload endpoint uses its default `replace=true` setting.
