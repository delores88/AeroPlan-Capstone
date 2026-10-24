# AeroPlan methodology

The application evaluates simulated inventory decisions conditional on the public synthetic aerospace dataset. It does not estimate real-company savings or execute purchasing. Version 2.2 defaults to cost-and-service selection. The original forecast-accuracy mode exactly reproduces the Module 6 protocol and keeps the original frozen research artifacts unchanged. The original selection procedure below applies to that preserved mode. The revised selection, validation safeguards, measured tradeoffs, and sensitivity results are documented in [OPTIMIZATION_HISTORY.md](OPTIMIZATION_HISTORY.md); future uncertainty bands are documented in [FORECAST_INTERVALS.md](FORECAST_INTERVALS.md). Inventory flow, chronology, baseline, and cost definitions are shared.

## Data and chronology

All 1,800 site-part series use 156 common weekly observations. The first 78 weeks train; the next 52 select policies; the last 26 evaluate them. The fixed dates are January 3, 2022 through December 23, 2024. Series with missing, duplicate, misaligned or insufficient weeks fail the evaluation, rather than silently disappearing from the population. Raw imports and mappings are versioned.

The four actual CSVs are bundled in data/aerospace-v1.zip. Publisher forecasts and maintenance indicators are not predictive inputs because their advance availability is not established. Missing optional starting blocked/backlog values in other user imports are explicitly recorded as zero assumptions; missing on-hand fails evaluation. No values are missing from the required starting snapshot in the bundled dataset.

## Forecast and policy selection

The fixed candidate order is eight-week moving average, last-observation naive, 52-week seasonal naive, simple exponential smoothing, Syntetos-Boylan approximation, and Teunter-Syntetos-Babai. Parameters are SES alpha=.20, SBA alpha=.10, and TSB alpha=beta=.10. Forecasts at t use only observations before t. The selected model minimizes validation MAE, with ties resolved by candidate order. Residual uncertainty is the population standard deviation of causal training residuals at indices 26 through 77.

Training receipts dated on or before the training cutoff establish the empirical lead distribution. At least three own-site/part receipts are preferred, then at least three receipts pooled for the same part, then nominal lead time. Only positive lead days up to 730 are included. Days are rounded up to weeks, with a one-week minimum.

The baseline uses MA(8) and buffer z=1.645. Selected policies search z in [0,.5,1,1.5,2,2.5,3,4,5,6] with validation seed 42. A lead-dependent warmup precedes validation scoring. Among candidates meeting the service target, choose minimum holding cost, then minimum ending backlog, then smaller z. If none meets the target, choose highest fill, then lowest cost, then smaller z and retain the infeasible flag. This is a finite search, not global optimization.

## Inventory flow and cost

Initial usable stock is max(on-hand minus blocked stock,0) at the training cutoff, with the recorded backlog and an empty initial pipeline. Each week receives arrivals, serves old backlog, serves current demand, then orders. An order placed at t arrives at t+L+1. Full receipts and unconstrained capacity are assumptions.

Protection weeks = ceil(mean lead days/7)+1.

Target = ceil(mu*protection + z*sqrt(sigma^2*protection + mu^2*(lead standard deviation days/7)^2)), floored at zero.

Order = max(0,ceil(target - (usable stock + in-transit stock - backlog))).

Holding cost = ending usable stock * unit cost * annual carrying rate /52. Source currency is unspecified, so results use cost units. Procurement, in-transit, shortage, repair, disposal and expedite costs are excluded. Immediate fill = units of current demand filled immediately / units demanded. Filling old backlog later does not improve immediate fill. With no demand, fill is undefined.

Inventory conservation and nonnegative states are checked for each site-part/week. Policies, input identity, effective settings and source identity are saved before evaluating the reserved test period. The app has previously examined that period, so subsequent tuning against it is exploratory.

## Paired evaluation

Default seeds 10001 through 10030 produce matching lead draws for baseline and selected policies at every possible site-part/order-week. Each pair evolves through validation into the test period; only the final 26 weeks are scored. Model identities and buffers remain fixed, while rolling forecasts may use demand already observed by their forecast origin.

Cost differences are baseline minus selected. Service differences are selected minus baseline. One-sided paired t intervals compare cost with 0 and service with -.01. Both lower bounds must exceed their respective null boundaries for the joint improvement criterion. Whether selected fill meets the absolute 95% target is a separate decision. Diagnostics include Shapiro-Wilk and paired-difference range/skew; small Monte Carlo variation is not evidence of population-wide certainty.

The lead multiplier is evaluation-only: it scales sampled leads and their mean/standard deviation in protection stock. It leaves original validation selections unchanged, enabling the paper's +25% sensitivity replay.

## Cohorts and recommendations

Site, family, criticality, supplier risk, repairability and training-only demand-frequency cohorts retain the full population. Fill is demand-weighted; costs are summed across series and averaged across replications. Cohort descriptions do not change portfolio inference. Family is not an interchangeability code, and the source lacks authentic basket/work-order identities.

Displayed forecasts and stock targets are planning estimates. Current purchase quantities require a reconciled open pipeline that this source does not supply. No current order quantity is fabricated.
