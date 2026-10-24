# Forecast prediction intervals

## Purpose and output

AeroPlan adds a **nominal 95% empirical prediction interval for future weekly demand** to each point forecast. It is a prediction interval for an individual future observation, not a confidence interval for mean demand. It is not an order recommendation or a service-level guarantee.

The existing point-forecast algorithms are unchanged. The public function is:

    prediction_intervals(history, model, horizon=13, level=0.95)

It returns future rows containing horizon, yhat, yhat_lower, yhat_upper, and calibration_n, together with calibration metadata. An optional forecast_origin index restricts the function to history[:forecast_origin]. Missing bounds are JSON null. The UI shades only finite, available bounds and includes the upper bound when scaling the vertical axis.

## Calibration

For current origin T and horizon h, an earlier origin o predicts observation y[o+h-1] using only observations y[:o]. Calibration is permitted only when o+h-1 < T. Origins begin after 52 observed weeks. Each horizon retains at most its latest 104 eligible origins.

The selected model is held fixed during calibration. Parameters/states are reconstructed causally at each origin, using the same algorithm as the normal point forecast. Constant-level methods remain constant for their forward path; seasonal naive forecasts repeat their 52-week pattern recursively. Calibration errors are therefore genuinely horizon-specific, rather than a one-step error multiplied by a guessed percentage.

For each horizon, calculate absolute errors:

    e[o,h] = abs(y[o+h-1] - forecast(y[:o], model, h))

For n eligible errors and nominal coverage level L, use the k-th smallest error, counting from one, where:

    k = ceil((n + 1) * L)
    radius[h] = sorted(errors)[k - 1]
    lower[h] = max(0, yhat[h] - radius[h])
    upper[h] = yhat[h] + radius[h]

At least 20 calibration errors are required. When n < 20 or k > n, both bounds are unavailable. The algorithm does not cap an unattainable quantile rank at the largest error. With the 156-week aerospace history, horizons 1 through 13 have 104 through 92 calibration observations. Metadata records actual counts, rank, radius, origin indexes, and last scored outcome for every horizon.

The nonnegative floor reflects the demand domain. These clipped symmetric absolute-error bands are not equal-tail quantiles. They need not widen monotonically across horizons because each horizon has its own empirical errors. All-zero error histories can produce a zero-width band; metadata flags this rather than inventing uncertainty.

## Timing and saved results

Future intervals use all observations available at the current forward-forecast origin, including the now-observed historical evaluation period. They are not retrospective evidence of coverage on that period. They do not change model selection, buffer selection, simulation, or hypothesis tests.

New runs save their interval fields and metadata with the forecast output. Older immutable runs may receive a read-only display calculation in the results adapter. Such metadata must carry display_only: true. The original stored run and its exported reproducibility record must remain unchanged.

## Limits of interpretation

The nominal 95% label is not an empirically established 95% coverage claim. Forecast errors overlap in time, demand may be serially dependent or nonstationary, and the supplied model was selected using historical data. The finite-sample rank adjustment alone does not create a conformal coverage guarantee in this setting. Coverage is marginal for each future week, not simultaneous coverage of all 13 weeks. Rare spikes absent from calibration, structural changes, and newly active demand may fall outside the interval.

Assess interval coverage and width prospectively on new observations before relying on these bands operationally. The current functionality does not report fabricated observed coverage or imply that a 95% demand interval delivers a 95% inventory fill rate.

## Verification

tests/test_intervals.py checks all-model point equality, an analytic multi-horizon naive-trend example, independence from an unobserved future tail, recursive seasonal forecasts, nonnegative finite bounds, insufficient samples, degenerate zero-error histories, sample caps, quantile ranks, nominal-level monotonicity, and invalid input rejection.

## Method references

Hyndman, R. J., & Athanasopoulos, G. Forecasting: Principles and Practice (3rd ed.), sections 5.5 and 5.10. These explain prediction intervals and rolling-origin evaluation with distinct forecast horizons.
https://otexts.com/fpp3/toolbox.html#sec-prediction-intervals
https://otexts.com/fpp3/toolbox.html#sec-tscv

Angelopoulos, A. N., & Bates, S. (2022). A gentle introduction to conformal prediction and distribution-free uncertainty quantification (Version 6). The empirical rank adjustment follows the split-conformal quantile convention; AeroPlan does not claim that the corresponding exchangeability conditions hold.
https://arxiv.org/abs/2107.07511v6

