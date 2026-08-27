# Walmart M5 Training Results

## First verified run

- Run date: 2026-08-28
- Source: University of Nicosia M5 dataset v1, DOI
  [10.5281/zenodo.10203108](https://doi.org/10.5281/zenodo.10203108)
- Source coverage: 30,490 item-store series and 1,941 observed days
- Item-day values processed: 59,181,090
- Prepared grain: state, store, category, and day
- Prepared rows: 58,230 across 30 series
- Application rows loaded: 58,105 positive-sales records
- Source date range: 2011-01-29 through 2016-05-22
- Units represented: 66,927,173
- Source-price revenue: USD 191,577,546.04

All three source files passed the published byte-size and MD5 checks before
preparation. The source files, prepared CSV files, predictions, and serialized
model are operational artifacts and are not committed to Git.

## Model and split

The first run trained a global `HistGradientBoostingRegressor` on log-transformed
daily unit sales at the store-category level. It used calendar, hierarchy, SNAP,
event, lag, and rolling-window features.

- Training window: 2011-02-26 through 2016-04-24
- Training rows: 56,550
- Holdout window: 2016-04-25 through 2016-05-22
- Holdout rows: 840
- Holdout horizon: 28 days

| Metric | Trained model | 28-day seasonal naive |
| --- | ---: | ---: |
| MAE | 114.5837 | 157.9000 |
| RMSE | 181.7892 | 262.8486 |
| RMSLE | 0.1220 | 0.1575 |
| WMAPE | 7.8140% | 10.7680% |

The trained model reduced WMAPE by approximately 27.4% and RMSE by 30.8%
relative to the seasonal-naive benchmark on this holdout.

These are project-specific store-category temporal holdout metrics. They are
not the official M5 hierarchical WRMSSE and must not be presented as a Kaggle
leaderboard result.

## Application verification

After loading the generated application CSV into PostgreSQL, the following
checks passed:

- KPI aggregation across all 58,105 positive-sales records
- Existing monthly revenue forecast endpoint
- Four-cluster store-proxy segmentation
- Isolation Forest evaluation of all loaded records
- Dashboard HTTP 200 response

M5 contains no shopper identity, so the application maps each store to a
customer proxy. The dedicated M5 model predicts store-category unit sales;
the existing dashboard forecast endpoint remains the separate monthly revenue
baseline.
