"""Past-only empirical prediction bands for the existing point forecasts.

These are horizon-specific marginal prediction intervals, not confidence
intervals for a mean and not guaranteed conformal coverage for dependent data.
"""
from __future__ import annotations
import math
from .forecast import MODELS, forecasts, mean

METHOD = "rolling_origin_absolute_error"
DEFAULT_LEVEL = 0.95
DEFAULT_MIN_HISTORY = 52
DEFAULT_MAX_ORIGINS = 104
DEFAULT_MIN_CALIBRATION = 20


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(label + " must be a positive integer.")
    return value


def _path_at_origin(y, model, origin, horizon, point_predictions):
    """Match forecast.future without recomputing every model at every origin."""
    if model != "seasonal52":
        return [float(point_predictions[model][origin])] * horizon
    previous = list(y[:origin])
    result = []
    for _ in range(horizon):
        value = previous[-52] if len(previous) >= 52 else mean(previous[-8:])
        result.append(float(value))
        previous.append(value)
    return result


def prediction_intervals(history, model, horizon=13, level=DEFAULT_LEVEL, *,
                         forecast_origin=None, min_history=DEFAULT_MIN_HISTORY,
                         max_origins=DEFAULT_MAX_ORIGINS,
                         min_calibration=DEFAULT_MIN_CALIBRATION):
    """Return future yhat/lower/upper rows and reproducible calibration metadata.

    forecast_origin is a zero-based cutoff: only history[:forecast_origin] is
    observable. Origin o predicts index o+h-1. Every calibration outcome must
    be strictly before the forecast cutoff. Each horizon retains at most the
    latest max_origins eligible errors after min_history observations.

    The radius is sorted absolute error at rank ceil((n+1)*level), counting
    ranks from one. Bounds are unavailable when n is too small or that rank
    exceeds n. There is no substitution of a fixed percentage or zero radius.
    """
    if model not in MODELS:
        raise ValueError("Unknown forecast model.")
    horizon = _positive_integer(horizon, "horizon")
    min_history = _positive_integer(min_history, "min_history")
    max_origins = _positive_integer(max_origins, "max_origins")
    min_calibration = _positive_integer(min_calibration, "min_calibration")
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 < level < 1:
        raise ValueError("level must be between zero and one.")
    if forecast_origin is None:
        forecast_origin = len(history)
    if (isinstance(forecast_origin, bool) or not isinstance(forecast_origin, int)
            or not 0 <= forecast_origin <= len(history)):
        raise ValueError("forecast_origin must be an index within the supplied history.")
    try:
        y = [float(v) for v in history[:forecast_origin]]
    except (TypeError, ValueError) as exc:
        raise ValueError("Observed demand must contain finite nonnegative numbers.") from exc
    if any(not math.isfinite(v) or v < 0 for v in y):
        raise ValueError("Observed demand must contain finite nonnegative numbers.")
    point_predictions = forecasts(y)
    future = _path_at_origin(y, model, len(y), horizon, point_predictions)
    origin_paths = {}
    rows, calibration = [], []
    for h in range(1, horizon + 1):
        last_origin = len(y) - h
        first_origin = max(min_history, last_origin - max_origins + 1)
        errors = []
        for origin in range(first_origin, last_origin + 1):
            if origin not in origin_paths:
                origin_paths[origin] = _path_at_origin(y, model, origin, horizon, point_predictions)
            errors.append(abs(y[origin + h - 1] - origin_paths[origin][h - 1]))
        count = len(errors)
        rank = math.ceil((count + 1) * level)
        available = count >= min_calibration and rank <= count
        radius = sorted(errors)[rank - 1] if available else None
        point = future[h - 1]
        lower = max(0.0, point - radius) if radius is not None else None
        upper = point + radius if radius is not None else None
        rows.append({"horizon": h, "yhat": point, "yhat_lower": lower,
                     "yhat_upper": upper, "calibration_n": count})
        calibration.append({
            "horizon": h, "n": count, "quantile_rank": rank, "radius": radius,
            "first_origin_index": first_origin if count else None,
            "last_origin_index": last_origin if count else None,
            "last_outcome_index": last_origin + h - 1 if count else None,
            "available": available,
            "status": "available" if available else "insufficient_calibration",
            "zero_error_history": bool(count and max(errors) == 0),
        })
    return {
        "future": rows,
        "metadata": {
            "level": float(level), "method": METHOD,
            "label": f"{level:.0%} empirical prediction interval",
            "scope": "Future weekly demand; marginal interval at each horizon",
            "forecast_origin_index": len(y), "observed_weeks": len(y),
            "minimum_history_weeks": min_history, "maximum_origins_per_horizon": max_origins,
            "minimum_calibration_n": min_calibration,
            "quantile_rule": "ceil((n + 1) * level)-th smallest absolute rolling-origin error",
            "lower_bound": "max(0, yhat - radius)",
            "upper_bound": "yhat + radius",
            "calibration": calibration,
            "calibration_model": model,
            "calibration_timing": "Conditional on the supplied model, each forecast state uses only preceding observations; every scored outcome precedes the current forecast origin.",
            "model_selection_scope": "Conditional on the supplied model; historical origins do not repeat model selection.",
            "coverage_guarantee": False,
            "limitations": [
                "The stated level is nominal. Serial dependence, model selection, and distribution shifts can change actual coverage.",
                "Intervals are marginal for individual future weeks, not simultaneous coverage for the complete horizon.",
                "Finite historical errors may miss rare demand spikes. All-zero histories can produce a degenerate interval.",
                "Symmetric absolute-error bands are clipped at zero and are not equal-tail quantiles.",
                "Future bands use all observations available now and do not establish out-of-sample coverage on an earlier evaluation period.",
            ],
        },
    }

