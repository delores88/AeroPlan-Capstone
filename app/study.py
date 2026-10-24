"""Reproducible paired inventory study using canonical local Store.load() data.

The first 78 weeks train the models, the next 52 select one model and buffer
per site-part, and the final 26 evaluate frozen policies. There is no runtime
dependency on the coursework research directory or its stored results.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import platform
import random
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import scipy
from scipy import stats

from .engine import Cancelled
from .forecast import forecasts as causal_forecasts, future, metrics as forecast_metrics
from .intervals import prediction_intervals

ENGINE_VERSION = "2.0.0"
MODELS = ("ma8", "naive", "seasonal52", "ses", "sba", "tsb")
BUFFER_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
START, CUT, END = 78, 130, 156
DEFAULTS = {
    "name": "Inventory evaluation",
    "carry_rate": 0.24,
    "target": 0.95,
    "lead_factor": 1.0,
    "replications": 30,
    "seed_start": 10001,
    "training_weeks": 78,
    "validation_weeks": 52,
    "test_weeks": 26,
    "validation_seed": 42,
    "review_weeks": 1,
    "baseline_model": "ma8",
    "baseline_z": 1.645,
    "models": list(MODELS),
    "buffer_grid": list(BUFFER_GRID),
    "forecast_horizon": 13,
    "service_tolerance": 0.01,
    "alpha": 0.05,
}
_EDITABLE = {"name", "carry_rate", "target", "lead_factor", "replications", "seed_start"}


def config_checked(raw=None):
    """Validate settings, preserving all structural protocol choices.

    lead_factor is an evaluation-only sensitivity: model/buffer selection and
    the validation lead distribution always use the original training leads.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Study settings must be an object.")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown study setting: " + ", ".join(sorted(unknown)))
    out = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key not in _EDITABLE:
            if value != DEFAULTS[key]:
                raise ValueError(f"{key} is fixed by the study protocol.")
            continue
        if key == "name":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Study name must be nonempty text.")
            if len(value.strip()) > 180:
                raise ValueError("Study name must be at most 180 characters.")
            out[key] = value.strip()
            continue
        if isinstance(value, bool):
            raise ValueError(f"{key} must be numeric, not a Boolean.")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{key} must be finite.")
        if key in ("replications", "seed_start"):
            if not number.is_integer():
                raise ValueError(f"{key} must be an integer.")
            lower, upper = (2, 1000) if key == "replications" else (0, 2147483647)
            if not lower <= number <= upper:
                raise ValueError(f"{key} must be between {lower} and {upper}.")
            out[key] = int(number)
        else:
            lower, upper = {"carry_rate": (0.0, 5.0), "target": (0.000001, 1.0),
                            "lead_factor": (0.1, 4.0)}[key]
            if not lower <= number <= upper:
                raise ValueError(f"{key} must be between {lower} and {upper}.")
            out[key] = number
    if out["seed_start"] + out["replications"] - 1 > 2147483647:
        raise ValueError("The replication seed range exceeds 2147483647.")
    return out


def _native(value):
    if isinstance(value, np.ndarray):
        return _native(value.tolist())
    if isinstance(value, np.generic):
        return _native(value.item())
    if isinstance(value, dict):
        return {str(k): _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _hash(value):
    encoded = json.dumps(_native(value), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_cancel(cancel):
    if cancel is None:
        return
    requested = cancel.is_set() if hasattr(cancel, "is_set") else cancel()
    if requested:
        raise Cancelled("Study cancelled.")


def _number(value, name, positive=False):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be a finite nonnegative number.")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}.")
    return value


def _prepare(dataset, cancel=None):
    if not isinstance(dataset, (tuple, list)) or len(dataset) != 5:
        raise ValueError("The study requires the canonical Store.load() five-tuple.")
    meta, parts, groups, orders, quality = dataset
    if not groups or not parts:
        raise ValueError("Import a nonempty parts master and weekly history first.")
    keys = sorted(groups)
    dates, histories = None, []
    initial, backlog, cost = [], [], []
    assumed = Counter()
    for i, key in enumerate(keys):
        if i % 100 == 0:
            _check_cancel(cancel)
        if not isinstance(key, tuple) or len(key) != 2 or not all(isinstance(k, str) for k in key):
            raise ValueError("History keys must be (site_id, part_id) text pairs.")
        if key[1] not in parts:
            raise ValueError(f"{key}: part is absent from the parts master.")
        rows = sorted(groups[key], key=lambda row: row["week"])
        if len(rows) != END:
            raise ValueError(f"{key}: the fixed protocol requires exactly 156 uninterrupted weekly observations; found {len(rows)}.")
        try:
            row_dates = [date.fromisoformat(row["week"]) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{key}: history contains an invalid ISO week date.") from exc
        if any((b - a).days != 7 for a, b in zip(row_dates, row_dates[1:])):
            raise ValueError(f"{key}: history has duplicate, missing, or irregular weeks.")
        if dates is None:
            dates = row_dates
        elif dates != row_dates:
            raise ValueError("All site-part series must share the same 156 weekly dates.")
        for row in rows:
            _number(row.get("demand"), f"{key} demand")
        snapshot = rows[START - 1]
        stock = _number(snapshot.get("on_hand"), f"{key} training-end on_hand")
        values = {}
        for field in ("blocked_stock", "backorders"):
            value = snapshot.get(field)
            if value is None:
                assumed[field] += 1
                value = 0
            values[field] = _number(value, f"{key} training-end {field}")
        if values["blocked_stock"] > stock:
            assumed["blocked_above_on_hand"] += 1
        initial.append(max(0.0, stock - values["blocked_stock"]))
        backlog.append(values["backorders"])
        cost.append(_number(parts[key[1]].get("unit_cost"), f"{key} unit_cost", True))
        nominal = _number(parts[key[1]].get("lead_time_days"), f"{key} nominal lead_time_days", True)
        if nominal > 730:
            raise ValueError(f"{key}: nominal lead time exceeds 730 days.")
        histories.append(rows)
    y = np.array([[float(row["demand"]) for row in rows] for rows in histories], dtype=float)
    same, pooled = defaultdict(list), defaultdict(list)
    cutoff = dates[START - 1]
    eligible = 0
    excluded_orders = 0
    for row in orders:
        _check_cancel(cancel)
        try:
            ordered = date.fromisoformat(row["order_date"])
            received = date.fromisoformat(row["receipt_date"])
        except (KeyError, TypeError, ValueError):
            excluded_orders += 1
            continue
        days = (received - ordered).days
        if ordered > cutoff or received > cutoff or not 0 < days <= 730:
            excluded_orders += 1
            continue
        pid = row.get("part_id")
        if pid not in parts:
            excluded_orders += 1
            continue
        same[(row.get("site_id", ""), pid)].append(days)
        pooled[pid].append(days)
        eligible += 1
    samples, sources = [], []
    for site, pid in keys:
        own, all_part = same[(site, pid)], pooled[pid]
        values = own if len(own) >= 3 else all_part
        source = "site-part" if len(own) >= 3 else "part-pooled"
        if len(values) < 3:
            values = [float(parts[pid]["lead_time_days"])]
            source = "nominal"
        samples.append(list(values))
        sources.append(source)
    means = np.array([statistics.mean(values) for values in samples], dtype=float)
    stds = np.array([statistics.pstdev(values) for values in samples], dtype=float)
    warmup = np.maximum(4, np.ceil(means / 7) + 2).astype(int)
    if np.any(warmup + 4 > CUT - START):
        raise ValueError("Training lead times leave fewer than four scored validation weeks for at least one series.")
    warnings = list(meta.get("warnings", []))
    for field in ("blocked_stock", "backorders"):
        if assumed[field]:
            warnings.append(f"Assumed zero {field} at the training-end snapshot for {assumed[field]} series because those values are missing.")
    if assumed["blocked_above_on_hand"]:
        warnings.append(f"Floored usable starting inventory at zero for {assumed['blocked_above_on_hand']} series with blocked stock above on-hand.")
    warnings.extend([
        "Simulation assumes an empty initial pipeline, full receipts, no capacity constraints, and backlog priority over current demand.",
        "Carrying cost is the modeled ending usable inventory value times the annual carrying rate divided by 52; it excludes ordering, shortage, repair, and disposal costs.",
        "Cohorts describe site-part attributes. The imported tables do not establish customer cohorts or transaction baskets.",
        "Paired inference reflects simulated lead-time draws conditional on these data and assumptions, not independent real-world trials.",
    ])
    split = {
        "training": {"start": dates[0].isoformat(), "end": dates[START - 1].isoformat(), "weeks": START},
        "validation": {"start": dates[START].isoformat(), "end": dates[CUT - 1].isoformat(), "weeks": CUT - START},
        "test": {"start": dates[CUT].isoformat(), "end": dates[END - 1].isoformat(), "weeks": END - CUT},
        "training_end": dates[START - 1].isoformat(), "test_start": dates[CUT].isoformat(),
    }
    return dict(meta=meta, parts=parts, keys=keys, dates=dates, histories=histories, y=y,
                initial=np.array(initial), backlog=np.array(backlog), cost=np.array(cost),
                samples=samples, lead_sources=sources, lead_mean=means, lead_sd=stds,
                warmup=warmup, split=split, warnings=warnings, assumed=dict(assumed),
                eligible_orders=eligible, excluded_orders=excluded_orders, quality_rows=len(quality))


def _predictions(y, cancel=None):
    result = np.empty((len(y), len(MODELS), y.shape[1] + 1))
    for i, values in enumerate(y):
        if i % 100 == 0:
            _check_cancel(cancel)
        pred = causal_forecasts(values.tolist())
        for j, model in enumerate(MODELS):
            result[i, j] = pred[model]
    return result


def _lead_draws(seed, keys, samples, length=END):
    result = np.empty((len(keys), length), dtype=np.int64)
    for i, ((site, pid), values) in enumerate(zip(keys, samples)):
        material = f"{seed}|{site}|{pid}".encode()
        rng = random.Random(int(hashlib.sha256(material).hexdigest()[:16], 16))
        result[i] = [max(1, math.ceil(rng.choice(values) / 7)) for _ in range(length)]
    return result


def _simulate(y, pred, initial, backlog0, meanlead, stdlead, sigma, cost, z,
              draws, end, score_start, trace=False, carry_rate=0.24, cancel=None):
    """Vectorized site-part simulation with the protocol's exact weekly order.

    Returns (metrics, final_backlog, weekly_trace, flow_diagnostics). Metrics
    columns: demand, immediate served, carrying cost, stock sum, stockout weeks,
    ordered units, scored weeks. Orders placed at t arrive at t + draw[t] + 1.
    """
    n = len(y)
    indices = np.arange(n)
    stock, backlog = initial.copy(), backlog0.copy()
    pipeline = np.zeros((n, end + int(draws.max()) + 2))
    in_transit = np.zeros(n)
    metrics = np.zeros((n, 7))
    protection = np.ceil(meanlead / 7) + 1
    receipts_total, demand_total = np.zeros(n), np.zeros(n)
    weekly = []
    max_error = 0.0
    minimum = 0.0
    for t in range(START, end):
        _check_cancel(cancel)
        receipts = pipeline[:, t].copy()
        stock += receipts
        in_transit -= receipts
        old = np.minimum(stock, backlog)
        stock -= old
        backlog -= old
        demand = y[:, t]
        served = np.minimum(stock, demand)
        stock -= served
        backlog += demand - served
        mu = pred[:, t + 1]
        target = np.maximum(0, np.ceil(mu * protection + z * np.sqrt(
            sigma * sigma * protection + mu * mu * (stdlead / 7) ** 2)))
        ordered = np.maximum(0, np.ceil(target - (stock + in_transit - backlog)))
        pipeline[indices, t + draws[:, t] + 1] += ordered
        in_transit += ordered
        scored = t >= np.asarray(score_start)
        holding = stock * cost * carry_rate / 52
        stockout = demand - served > 1e-9
        metrics += np.column_stack([demand, served, holding, stock, stockout,
                                    ordered, np.ones(n)]) * np.asarray(scored)[..., None]
        receipts_total += receipts
        demand_total += demand
        error = float(np.max(np.abs(stock - backlog - (initial - backlog0 + receipts_total - demand_total))))
        max_error = max(max_error, error)
        minimum = min(minimum, float(stock.min()), float(backlog.min()), float(in_transit.min()))
        if minimum < -1e-8 or error > 1e-7:
            raise ArithmeticError("Inventory conservation failed; no study result was produced.")
        if not all(np.isfinite(v).all() for v in (stock, backlog, in_transit, metrics)):
            raise ArithmeticError("Inventory calculations overflowed; check input magnitudes.")
        if trace and t >= CUT:
            weekly.append({"week_index": t, "demand": float(demand.sum()),
                           "served": float(served.sum()), "carrying_cost": float(holding.sum()),
                           "ending_inventory_value": float((stock * cost).sum()),
                           "backlog": float(backlog.sum()),
                           "stockout_site_part_weeks": int(stockout.sum())})
    return metrics, backlog, weekly, {"conservation_pass": True,
        "max_inventory_flow_error": max_error, "minimum_inventory_state": minimum,
        "series_week_checks": n * (end - START), "max_draw_weeks": int(draws.max())}


def _inference(differences, boundary, alpha=0.05):
    values = np.asarray(differences, dtype=float)
    n = len(values)
    mean, sd = float(np.mean(values)), float(np.std(values, ddof=1))
    se = sd / math.sqrt(n)
    result = {"n": n, "mean": mean, "sd": sd, "se": se,
              "null_boundary": boundary, "df": n - 1, "reject_null": False,
              "test_available": bool(se > 0 and math.isfinite(se)),
              "min": float(values.min()), "max": float(values.max()),
              "confidence_level": 1 - alpha, "alternative": "mean difference greater than null boundary"}
    if not result["test_available"]:
        return {**result, "t": None, "p_one_sided": None, "lower_95_one_sided": None,
                "shapiro_w": None, "shapiro_p": None, "sample_skew": None,
                "largest_abs_standardized_deviation": None,
                "reason": "Zero paired variance; inferential statistics unavailable. Interpret descriptively."}
    t_value = (mean - boundary) / se
    lower = float(mean - stats.t.ppf(1 - alpha, n - 1) * se)
    result.update(t=float(t_value), p_one_sided=float(stats.t.sf(t_value, n - 1)),
                  lower_95_one_sided=lower, reject_null=bool(lower > boundary),
                  largest_abs_standardized_deviation=float(np.max(np.abs((values - mean) / sd))))
    if n >= 3:
        shapiro = stats.shapiro(values)
        result.update(shapiro_w=float(shapiro.statistic), shapiro_p=float(shapiro.pvalue),
                      sample_skew=float(stats.skew(values, bias=False)))
    else:
        result.update(shapiro_w=None, shapiro_p=None, sample_skew=None)
    return _native(result)


def _aggregate(metrics, backlog, cost, target):
    demand, served = float(metrics[:, 0].sum()), float(metrics[:, 1].sum())
    fill = np.divide(metrics[:, 1], metrics[:, 0], out=np.full(len(cost), np.nan), where=metrics[:, 0] > 0)
    return {"carrying_cost": float(metrics[:, 2].sum()), "fill_rate": served / demand if demand else None,
            "avg_inventory_value": float((metrics[:, 3] / (END - CUT) * cost).sum()),
            "end_backlog": float(backlog.sum()), "stockout_weeks": int(metrics[:, 4].sum()),
            "series_target_count": int((fill >= target).sum()), "demand": demand,
            "served": served, "ordered_units": float(metrics[:, 5].sum())}


def _training_frequency(values):
    share = float(np.count_nonzero(values) / len(values))
    if share == 0:
        return "No positive-demand weeks"
    if share <= 0.25:
        return "Positive demand in >0-25% of weeks"
    if share <= 0.50:
        return "Positive demand in >25-50% of weeks"
    if share <= 0.75:
        return "Positive demand in >50-75% of weeks"
    return "Positive demand in >75-100% of weeks"


def _category(value):
    return "Unspecified" if value is None or not str(value).strip() else str(value).strip()


def _cohorts(series):
    output = {}
    for dimension in ("site_id", "family", "criticality", "supplier_risk", "repairable", "training_frequency"):
        groups = defaultdict(list)
        for row in series:
            groups[row[dimension]].append(row)
        output[dimension] = []
        for key in sorted(groups):
            members = groups[key]
            demand = sum(row["demand"] for row in members)
            row = {"key": key, "series_count": len(members),
                   "part_count": len({item["part_id"] for item in members}), "demand": demand}
            for label in ("baseline", "selected"):
                served = sum(item[f"{label}_served"] for item in members)
                row.update({f"{label}_served": served,
                            f"{label}_fill": served / demand if demand else None,
                            f"{label}_cost": sum(item[f"{label}_cost"] for item in members),
                            f"{label}_avg_inventory_value": sum(item[f"{label}_avg_inventory_value"] for item in members),
                            f"{label}_end_backlog": sum(item[f"{label}_end_backlog"] for item in members),
                            f"{label}_stockout_weeks": sum(item[f"{label}_stockout_weeks"] for item in members)})
            row["cost_saving"] = row["baseline_cost"] - row["selected_cost"]
            row["fill_difference"] = row["selected_fill"] - row["baseline_fill"] if demand else None
            output[dimension].append(row)
    return output


def run_study(dataset, config=None, progress=lambda done, total, message: None,
              cancel=None, freeze_callback=None, *, _policy_selector=None, _config_snapshot=None):
    """Select, freeze, and evaluate a full local dataset without side effects.

    freeze_callback receives a detached JSON-safe policy snapshot before any
    test outcomes are evaluated. An exception in that callback aborts evaluation.
    The caller owns persistence. This function never reads coursework artifacts,
    changes the supplied dataset, or writes a file.
    """
    c = config_checked(config)
    saved_config = copy.deepcopy(_config_snapshot if _config_snapshot is not None else c)
    _check_cancel(cancel)
    total = 4 + len(BUFFER_GRID) + c["replications"]
    progress(0, total, "Validating complete weekly histories and training inputs")
    data = _prepare(dataset, cancel)
    keys, y = data["keys"], data["y"]
    n, indices = len(keys), np.arange(len(keys))
    dev = y[:, :CUT]
    progress(1, total, "Fitting causal forecasts on training and validation only")
    fdev = _predictions(dev, cancel)
    sigma = np.std(dev[:, None, 26:START] - fdev[:, :, 26:START], axis=2, ddof=0)
    maes = np.abs(dev[:, None, START:CUT] - fdev[:, :, START:CUT]).mean(axis=2)
    champion = np.argmin(maes, axis=1)
    selected_sigma = sigma[indices, champion]
    draws = _lead_draws(c["validation_seed"], keys, data["samples"])
    validation_metrics, validation_backlogs = [], []
    flow = {"conservation_pass": True, "max_inventory_flow_error": 0.0,
            "minimum_inventory_state": 0.0, "series_week_checks": 0, "max_draw_weeks": 0}

    def record_flow(check):
        flow["max_inventory_flow_error"] = max(flow["max_inventory_flow_error"], check["max_inventory_flow_error"])
        flow["minimum_inventory_state"] = min(flow["minimum_inventory_state"], check["minimum_inventory_state"])
        flow["series_week_checks"] += check["series_week_checks"]
        flow["max_draw_weeks"] = max(flow["max_draw_weeks"], check["max_draw_weeks"])

    for j, buffer in enumerate(BUFFER_GRID):
        m, backlog, _, check = _simulate(dev, fdev[indices, champion], data["initial"], data["backlog"],
            data["lead_mean"], data["lead_sd"], selected_sigma, data["cost"], buffer, draws,
            CUT, START + data["warmup"], carry_rate=c["carry_rate"], cancel=cancel)
        validation_metrics.append(m)
        validation_backlogs.append(backlog)
        record_flow(check)
        progress(2 + j, total, f"Selecting validation buffers: {j + 1}/{len(BUFFER_GRID)}")
    vm = np.stack(validation_metrics, axis=1)
    vb = np.stack(validation_backlogs, axis=1)
    vf = np.divide(vm[:, :, 1], vm[:, :, 0], out=np.full((n, len(BUFFER_GRID)), np.nan), where=vm[:, :, 0] > 0)
    chosen, feasible = [], []
    for i in range(n):
        candidates = [j for j in range(len(BUFFER_GRID)) if np.isfinite(vf[i, j]) and vf[i, j] >= c["target"]]
        if candidates:
            choice = min(candidates, key=lambda j: (vm[i, j, 2], vb[i, j], BUFFER_GRID[j]))
        else:
            choice = min(range(len(BUFFER_GRID)), key=lambda j: (
                -vf[i, j] if np.isfinite(vf[i, j]) else math.inf, vm[i, j, 2], BUFFER_GRID[j]))
        chosen.append(choice)
        feasible.append(bool(candidates))
    z = np.array(BUFFER_GRID)[chosen]
    policies = []
    for i, (site, pid) in enumerate(keys):
        j = chosen[i]
        policies.append({"site_id": site, "part_id": pid, "model": MODELS[int(champion[i])],
            "z": float(z[i]), "buffer_z": float(z[i]), "validation_feasible": feasible[i], "feasible": feasible[i],
            "validation_fill": float(vf[i, j]) if np.isfinite(vf[i, j]) else None,
            "validation_mae": float(maes[i, champion[i]]), "validation_carrying_cost": float(vm[i, j, 2]),
            "validation_end_backlog": float(vb[i, j]), "validation_scored_demand": float(vm[i, j, 0]),
            "validation_scored_weeks": int(vm[i, j, 6]), "warmup_weeks": int(data["warmup"][i]),
            "lead_source": data["lead_sources"][i], "lead_sample_count": len(data["samples"][i]) if data["lead_sources"][i] != "nominal" else 0,
            "lead_samples_days": data["samples"][i], "lead_mean_days": float(data["lead_mean"][i]),
            "lead_sd_days": float(data["lead_sd"][i]), "residual_sigma": float(selected_sigma[i]),
            "model_sigmas": {model: float(sigma[i, k]) for k, model in enumerate(MODELS)},
            "model_validation_maes": {model: float(maes[i, k]) for k, model in enumerate(MODELS)},
            "initial_usable_stock": float(data["initial"][i]), "initial_backlog": float(data["backlog"][i]),
            "unit_cost": float(data["cost"][i])})
    selection_details, selection_evidence = None, None
    if _policy_selector is not None:
        # Deliberately construct a development-only input. The selector receives
        # neither the test-demand matrix nor the full history/dataset tuple.
        selection_data = {key: copy.deepcopy(data[key]) for key in (
            "parts", "keys", "initial", "backlog", "cost", "samples", "lead_sources",
            "lead_mean", "lead_sd", "warmup")}
        selection_data["y"] = dev.copy()
        selection_data["dates"] = list(data["dates"][:CUT])
        selection = _policy_selector(selection_data, c, fdev, sigma, maes, copy.deepcopy(policies),
            lambda message: progress(11, total, message), cancel)
        policies = selection["policies"]
        if [(p["site_id"], p["part_id"]) for p in policies] != keys:
            raise ValueError("Policy selector changed the evaluated site-part population.")
        champion = np.array([MODELS.index(p["model"]) for p in policies], dtype=int)
        selected_sigma = sigma[indices, champion]
        z = np.array([p["buffer_z"] for p in policies], dtype=float)
        feasible = [bool(p["validation_feasible"]) for p in policies]
        selection_details = selection["details"]
        selection_evidence = selection["evidence"]
        record_flow(selection["flow"])
    config_hash, policy_hash = _hash(saved_config), _hash(policies)
    development_hash = _hash({"keys": keys, "dates": [d.isoformat() for d in data["dates"][:CUT]],
                              "demand": dev, "policies_training_inputs": [
                                  {k: p[k] for k in ("lead_samples_days", "initial_usable_stock", "initial_backlog", "unit_cost")} for p in policies]})
    provenance = {"engine_version": ENGINE_VERSION, "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_sha256": config_hash, "policies_sha256": policy_hash, "development_inputs_sha256": development_hash,
        "dataset": copy.deepcopy(data["meta"]), "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "split": data["split"], "validation_seed": c["validation_seed"],
        "replication_seeds": list(range(c["seed_start"], c["seed_start"] + c["replications"])),
        "lead_factor_scope": "evaluation only; original training leads and frozen model/buffer selection",
        "selection_lead_factor": 1.0, "evaluation_lead_factor": c["lead_factor"],
        "forecast_timing": "At week t, forecast[t] uses demand strictly before t; review orders use forecast[t+1] after observing demand[t].",
        "receipt_timing": "Order at t arrives at t + sampled lead weeks + 1, before backlog and current demand.",
        "residual_sigma": "Population SD (ddof=0) of causal residuals at training indices 26 through 77.",
        "initial_pipeline": "empty", "stock_basis": "max(0, on_hand - blocked_stock)",
        "demand_weighted_fill": True, "full_receipts": True}
    if selection_details is not None:
        provenance["optimization"] = selection_details
        provenance["selection_evidence_sha256"] = _hash(selection_evidence)
    snapshot = {"engine_version": ENGINE_VERSION, "config": copy.deepcopy(saved_config),
                "provenance": copy.deepcopy(provenance), "policies": copy.deepcopy(policies),
                "test_outcomes_evaluated": False}
    if selection_evidence is not None:
        snapshot["selection_evidence"] = selection_evidence
    _check_cancel(cancel)
    if freeze_callback is not None:
        freeze_callback(_native(snapshot))
    _check_cancel(cancel)
    progress(12, total, "Policies frozen; evaluating paired outcomes with shared lead draws")
    f = _predictions(y, cancel)
    if not np.array_equal(f[:, :, :CUT + 1], fdev):
        raise ArithmeticError("Causal forecast-prefix check failed.")
    eval_samples = [[value * c["lead_factor"] for value in values] for values in data["samples"]]
    eval_mean, eval_sd = data["lead_mean"] * c["lead_factor"], data["lead_sd"] * c["lead_factor"]
    repetitions = []
    series_sums = {label: np.zeros((n, 8)) for label in ("baseline", "selected")}
    weekly_sums = {label: np.zeros((END - CUT, 6)) for label in ("baseline", "selected")}
    for index, seed in enumerate(provenance["replication_seeds"]):
        _check_cancel(cancel)
        draws = _lead_draws(seed, keys, eval_samples)
        row = {"seed": seed}
        for label, pred, sig, buffer in (("baseline", f[:, 0], sigma[:, 0], c["baseline_z"]),
                                        ("selected", f[indices, champion], selected_sigma, z)):
            m, backlog, trace, check = _simulate(y, pred, data["initial"], data["backlog"], eval_mean,
                eval_sd, sig, data["cost"], buffer, draws, END, CUT, trace=True,
                carry_rate=c["carry_rate"], cancel=cancel)
            record_flow(check)
            row[label] = _aggregate(m, backlog, data["cost"], c["target"])
            series_sums[label] += np.column_stack([m, backlog])
            weekly_sums[label] += np.array([[item[key] for key in ("demand", "served", "carrying_cost",
                "ending_inventory_value", "backlog", "stockout_site_part_weeks")] for item in trace])
        row["cost_saving"] = row["baseline"]["carrying_cost"] - row["selected"]["carrying_cost"]
        row["fill_difference"] = (row["selected"]["fill_rate"] - row["baseline"]["fill_rate"]
                                  if row["baseline"]["fill_rate"] is not None else None)
        repetitions.append(row)
        progress(13 + index, total, f"Paired replications complete: {index + 1}/{c['replications']}")
    count = c["replications"]
    summary = {}
    for label in ("baseline", "selected"):
        summary[label] = {key: float(np.mean([row[label][key] for row in repetitions]))
                          if repetitions[0][label][key] is not None else None for key in repetitions[0][label]}
    cost_diff = [row["cost_saving"] for row in repetitions]
    cost_test = _inference(cost_diff, 0.0, c["alpha"])
    fill_diff = [row["fill_difference"] for row in repetitions]
    if fill_diff[0] is None:
        service_test = {"test_available": False, "reject_null": False, "n": count,
                        "null_boundary": -c["service_tolerance"], "mean": None,
                        "reason": "No test demand; immediate unit fill and service inference are undefined."}
    else:
        service_test = _inference(fill_diff, -c["service_tolerance"], c["alpha"])
    absolute_met = summary["selected"]["fill_rate"] is not None and summary["selected"]["fill_rate"] >= c["target"]
    joint = cost_test["reject_null"] and service_test["reject_null"]
    inference = {"cost": cost_test, "service": service_test, "absolute_target": c["target"],
                 "absolute_target_met": bool(absolute_met), "joint_improvement_met": bool(joint),
                 "joint_with_target_met": bool(joint and absolute_met),
                 "interpretation": "Cost superiority, service noninferiority, and the absolute service target are separate criteria.",
                 "diagnostic_note": "Assess paired-difference shape and influential values alongside Shapiro-Wilk; do not retune policies or seeds after viewing test outcomes."}
    saving = summary["baseline"]["carrying_cost"] - summary["selected"]["carrying_cost"]
    summary["changes"] = {"cost_saving": saving,
        "cost_saving_percent": 100 * saving / summary["baseline"]["carrying_cost"] if summary["baseline"]["carrying_cost"] else None,
        "fill_difference": service_test["mean"], "fill_difference_percentage_points":
            service_test["mean"] * 100 if service_test["mean"] is not None else None}
    series, forecast_output = [], {}
    averages = {label: values / count for label, values in series_sums.items()}
    for i, (site, pid) in enumerate(keys):
        if i % 100 == 0:
            _check_cancel(cancel)
        part, policy = data["parts"][pid], policies[i]
        model = policy["model"]
        demand = float(averages["baseline"][i, 0])
        latest = data["histories"][i][-1]
        onhand = latest.get("on_hand")
        blocked = latest.get("blocked_stock")
        latest_usable = max(0.0, float(onhand) - float(blocked)) if onhand is not None and blocked is not None else None
        mu = float(f[i, champion[i], END])
        protection = math.ceil(float(eval_mean[i]) / 7) + 1
        target_units = max(0, math.ceil(mu * protection + float(z[i]) * math.sqrt(
            float(selected_sigma[i]) ** 2 * protection + mu ** 2 * (float(eval_sd[i]) / 7) ** 2)))
        row = {"site_id": site, "part_id": pid, "description": _category(part.get("description")),
            "family": _category(part.get("family")), "criticality": _category(part.get("criticality")),
            "supplier_risk": _category(part.get("supplier_risk")), "repairable": _category(part.get("repairable")),
            "training_frequency": _training_frequency(y[i, :START]),
            "training_nonzero_fraction": float(np.count_nonzero(y[i, :START]) / START),
            "model": model, "buffer_z": policy["buffer_z"], "validation_feasible": policy["validation_feasible"],
            "validation_fill": policy["validation_fill"], "demand": demand, "unit_cost": float(data["cost"][i]),
            "latest_date": latest["week"], "latest_usable_on_hand": latest_usable,
            "latest_backlog": latest.get("backorders"), "nominal_lead_days": float(part["lead_time_days"]),
            "lead_mean_days": float(eval_mean[i]), "lead_sd_days": float(eval_sd[i]),
            "next_forecast": mu, "target_units": target_units, "order_up_to": target_units,
            "estimated_order_units": None, "current_pipeline": None,
            "recommendation_note": "Target stock only. A purchase quantity requires a reconciled current inventory position, including open pipeline; no actual order quantity is inferred."}
        for field in ("selection_status", "baseline_fallback", "validation_guard_pass", "selection_reason",
                      "validation_absolute_target_met", "validation_baseline_fill", "validation_mean_fill_loss",
                      "validation_worst_seed_loss", "validation_mean_cost_saving", "candidate_count", "feasible_candidate_count",
                      "criticality_protected", "validation_block_guard_pass"):
            if field in policy:
                row[field] = policy[field]
        for label in ("baseline", "selected"):
            avg = averages[label][i]
            row.update({f"{label}_cost": float(avg[2]), f"{label}_fill": float(avg[1] / avg[0]) if avg[0] else None,
                        f"{label}_served": float(avg[1]), f"{label}_avg_inventory_value": float(avg[3] / (END - CUT) * data["cost"][i]),
                        f"{label}_stockout_weeks": float(avg[4]), f"{label}_ordered_units": float(avg[5]),
                        f"{label}_end_backlog": float(avg[7])})
        row["cost_saving"] = row["baseline_cost"] - row["selected_cost"]
        row["fill_difference"] = row["selected_fill"] - row["baseline_fill"] if demand else None
        series.append(row)
        band = prediction_intervals(y[i].tolist(), model, horizon=c["forecast_horizon"], level=.95)
        forecast_output[f"{site}|{pid}"] = {"site_id": site, "part_id": pid, "model": model,
            "history": [{"date": day.isoformat(), "actual": float(y[i, t]),
                         "predicted": float(f[i, champion[i], t]), "baseline_predicted": float(f[i, 0, t]),
                         "period": "training" if t < START else "validation" if t < CUT else "test"}
                        for t, day in enumerate(data["dates"])],
            "future": [{"date": (data["dates"][-1] + timedelta(weeks=t + 1)).isoformat(),
                        "predicted": float(item["yhat"]), **item} for t, item in enumerate(band["future"])],
            "intervals": band["metadata"],
            "future_note": "Conditional point forecasts with horizon-specific empirical prediction intervals; temporal dependence and model selection mean nominal coverage is not guaranteed.",
            "target_units": target_units, "estimated_order_units": None}
    weekly = []
    for i in range(END - CUT):
        row = {"date": data["dates"][CUT + i].isoformat(), "week_index": CUT + i}
        for label in ("baseline", "selected"):
            values = weekly_sums[label][i] / count
            row[label] = {key: float(value) for key, value in zip(("demand", "served", "carrying_cost",
                "ending_inventory_value", "backlog", "stockout_site_part_weeks"), values)}
            row[label]["fill_rate"] = float(values[1] / values[0]) if values[0] else None
        row["cost_saving"] = row["baseline"]["carrying_cost"] - row["selected"]["carrying_cost"]
        row["fill_difference"] = (row["selected"]["fill_rate"] - row["baseline"]["fill_rate"]
                                  if row["baseline"]["fill_rate"] is not None else None)
        weekly.append(row)
    forecast_scores = []
    actual = y[:, CUT:END].ravel().tolist()
    for j, model in enumerate(MODELS + ("selected",)):
        predicted = f[:, j, CUT:END] if j < len(MODELS) else f[indices, champion, CUT:END]
        forecast_scores.append({"model": model, **forecast_metrics(actual, predicted.ravel().tolist())})
    diagnostics = {**flow, "causal_forecast_prefix_pass": True, "series_count": n,
        "part_count": len({key[1] for key in keys}), "site_count": len({key[0] for key in keys}),
        "history_rows": n * END, "test_demand": float(y[:, CUT:END].sum()),
        "model_counts": dict(Counter(policy["model"] for policy in policies)),
        "buffer_counts": dict(Counter(str(policy["buffer_z"]) for policy in policies)),
        "validation_feasible_count": sum(feasible), "validation_infeasible_count": n - sum(feasible),
        "validation_undefined_fill_count": sum(p["validation_fill"] is None for p in policies),
        "eligible_training_receipts": data["eligible_orders"], "excluded_receipt_rows": data["excluded_orders"],
        "lead_source_counts": dict(Counter(data["lead_sources"])), "initial_value_assumptions": data["assumed"],
        "quality_incident_rows": data["quality_rows"], "forecast_metrics": forecast_scores,
        "frequency_cohort_basis": "Training-only proportion of weeks with positive consumption; fixed quartile-width bins, not distribution quantiles.",
        "test_selection_separation": "No test outcome entered model selection, residual sigma, lead profiles, or buffer selection.",
        "warnings": data["warnings"]}
    if selection_details is not None:
        diagnostics["optimization"] = selection_details
    result = {"config": saved_config, "provenance": provenance, "summary": summary, "inference": inference,
              "policies": policies, "replications": repetitions, "weekly": weekly,
              "cohorts": _cohorts(series), "series": series, "forecasts": forecast_output,
              "diagnostics": diagnostics, "split": data["split"]}
    _check_cancel(cancel)
    progress(total, total, "Evaluation complete; paired results and provenance ready")
    return _native(result)
