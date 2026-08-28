# Walmart M5 Training Results

## Verified data preparation

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

## Optimized model-selection protocol

The optimized run separates model selection from final evaluation. Candidate
models and blend weights are selected on the 28-day tuning window immediately
before the established final holdout. The selected candidate is then refitted
on all eligible observations before the holdout, and the final holdout is
evaluated once. No optimization choice uses final-holdout metrics.

- Feature-history start: 2011-03-26, after the longest 56-day lag
- Candidate-training end: 2016-03-27
- Tuning window: 2016-03-28 through 2016-04-24, 840 rows
- Final training window: 2011-03-26 through 2016-04-24, 55,710 rows
- Final holdout: 2016-04-25 through 2016-05-22, 840 rows
- Evaluation type: store-category one-step daily forecasts

The candidates use log-transformed daily unit sales. Enhanced candidates add
14- and 56-day lags, additional rolling means and standard deviations, cyclic
weekly and annual features, and lagged prices for a total of 28 features.
Blend calibration tests model predictions with 7-, 28-, and 56-day seasonal
lags in 10-percentage-point increments while keeping at least half the weight
on the trained model.

| Tuning candidate | Features | Calibrated blend | Tuning WMAPE |
| --- | ---: | --- | ---: |
| Legacy histogram gradient boosting | 16 | 80% model, 10% lag 7, 10% lag 56 | 7.2616% |
| Enhanced histogram gradient boosting | 28 | 70% model, 10% each seasonal lag | 7.4114% |
| Enhanced Extra Trees | 28 | 100% model | **6.5834%** |

The tuning window selected `ExtraTreesRegressor` with 300 trees, a minimum leaf
size of 2, and 80% feature sampling. Seasonal calibration assigned 100% weight
to the model, so the saved prediction is the unblended model output.

## Final holdout result

The original model and optimized model share the same established holdout so
their results are directly comparable. The optimized candidate was selected
without consulting that holdout.

| Metric | Original model | Optimized model | 28-day seasonal naive |
| --- | ---: | ---: | ---: |
| MAE | 114.5837 | **111.1802** | 157.9000 |
| RMSE | 181.7892 | **178.9442** | 262.8486 |
| RMSLE | **0.1220** | 0.1234 | 0.1575 |
| WMAPE | 7.8140% | **7.5819%** | 10.7680% |

The optimized model reduces WMAPE by 3.0% and RMSE by 1.6% relative to the
original trained model. Against the 28-day seasonal-naive benchmark, it reduces
WMAPE by 29.6% and RMSE by 31.9%. RMSLE is 0.0014 higher than the original, so
the optimization improves the primary WMAPE objective and absolute-error
metrics but not every metric.

These are project-specific one-step store-category temporal holdout metrics.
They use observed lag values as they become available through the holdout. They
are not recursive 28-day forecasts, the official M5 hierarchical WRMSSE, or a
Kaggle leaderboard result.

## Application verification

After loading the generated application CSV into PostgreSQL, the following
checks passed during the first verified run:

- KPI aggregation across all 58,105 positive-sales records
- Existing monthly revenue forecast endpoint
- Four-cluster store-proxy segmentation
- Isolation Forest evaluation of all loaded records
- Dashboard HTTP 200 response

M5 contains no shopper identity, so the application maps each store to a
customer proxy. The dedicated M5 model predicts store-category unit sales;
the existing dashboard forecast endpoint remains the separate monthly revenue
baseline.
