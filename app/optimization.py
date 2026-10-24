"""Versioned, bounded joint model/buffer selection on development data only.

This redesign is exploratory: the original evaluation period was already
examined when its weaknesses motivated a different selection objective.
"""
from __future__ import annotations

import copy
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import study

OPTIMIZER_VERSION = "joint-cost-service-v2"
DEFAULTS_V1 = {
    **copy.deepcopy(study.DEFAULTS),
    "name": "Cost and service evaluation",
    "policy_mode": "cost_service",
    "optimizer_version": "joint-cost-service-v1",
    "validation_seeds": [42, 43, 44, 45, 46],
    "mean_fill_tolerance": 0.005,
    "worst_seed_fill_tolerance": 0.01,
    "criticality_a_tolerance": 0.0,
    "optimization_buffer_grid": sorted(set(study.BUFFER_GRID + (1.645,))),
}
DEFAULTS = {**copy.deepcopy(DEFAULTS_V1), "optimizer_version": OPTIMIZER_VERSION,
    "name": "Protected cost and service evaluation", "mean_fill_tolerance": 0.0,
    "worst_seed_fill_tolerance": 0.0, "protected_criticalities": ["A"],
    "validation_block_split": 104, "minimum_block_weeks": 4,
    "block_mean_fill_loss_tolerance": 0.0, "block_worst_seed_fill_loss_tolerance": 0.0,
    "block_mean_cost_increase_tolerance": 0.0}
VERSIONS = {"joint-cost-service-v1": DEFAULTS_V1, OPTIMIZER_VERSION: DEFAULTS}


def config_checked(raw=None):
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise ValueError("Optimization settings must be an object.")
    version = raw.get("optimizer_version", OPTIMIZER_VERSION)
    if not isinstance(version, str) or version not in VERSIONS:
        raise ValueError("Unknown optimizer version.")
    defaults = VERSIONS[version]
    extra = set(defaults) - set(study.DEFAULTS)
    unknown = set(raw) - set(defaults)
    if unknown:
        raise ValueError("Unknown optimization setting: " + ", ".join(sorted(unknown)))
    for key in extra:
        if key in raw and raw[key] != defaults[key]:
            raise ValueError(f"{key} is fixed by optimizer version {version}.")
    base = study.config_checked({key: value for key, value in raw.items() if key in study.DEFAULTS})
    evaluation_seeds = range(base["seed_start"], base["seed_start"] + base["replications"])
    if any(seed in evaluation_seeds for seed in defaults["validation_seeds"]):
        raise ValueError("Evaluation seeds must not overlap the fixed validation seed set.")
    if "name" not in raw:
        base["name"] = defaults["name"]
    return {**base, **{key: copy.deepcopy(defaults[key]) for key in extra}}


def candidates(config):
    """Exactly 66 options, with the exact comparison policy first."""
    baseline = (config["baseline_model"], config["baseline_z"])
    return [baseline] + [(model, z) for model in study.MODELS for z in config["optimization_buffer_grid"]
                         if (model, z) != baseline]


def _selection_masks(costs, fills, criticality_a, config):
    """Return auditable constraints; inputs have axes series,candidate,seed."""
    mean_cost = costs.mean(axis=2)
    mean_fill = fills.mean(axis=2)
    baseline_cost, baseline_fill = mean_cost[:, 0], mean_fill[:, 0]
    tolerance = np.where(criticality_a, config["criticality_a_tolerance"], config["mean_fill_tolerance"])
    seed_tolerance = np.where(criticality_a, config["criticality_a_tolerance"], config["worst_seed_fill_tolerance"])
    floor = np.maximum(config["target"], baseline_fill - tolerance)
    worst_loss = np.max(fills[:, 0:1, :] - fills, axis=2)
    finite = np.isfinite(fills).all(axis=2) & np.isfinite(costs).all(axis=2)
    absolute = mean_fill + 1e-12 >= config["target"]
    mean_guard = mean_fill + 1e-12 >= floor[:, None]
    worst_guard = worst_loss <= seed_tolerance[:, None] + 1e-12
    guard_pass = finite & absolute & mean_guard & worst_guard
    saving = baseline_cost[:, None] - mean_cost
    improves = saving > 1e-9
    return dict(mean_cost=mean_cost, mean_fill=mean_fill, baseline_cost=baseline_cost,
                baseline_fill=baseline_fill, mean_fill_loss=baseline_fill[:, None] - mean_fill,
                worst_seed_loss=worst_loss, service_floor=floor, absolute_target_met=absolute & finite,
                mean_guard=mean_guard & finite, worst_seed_guard=worst_guard & finite,
                guard_pass=guard_pass, improves_cost=improves, eligible=guard_pass & improves,
                mean_cost_saving=saving)


def _choose(scores, mean_backlog, options):
    choices = []
    for i in range(len(scores["mean_cost"])):
        eligible = np.flatnonzero(scores["eligible"][i]).tolist()
        selected = min(eligible, key=lambda j: (scores["mean_cost"][i, j], mean_backlog[i, j],
                      study.MODELS.index(options[j][0]), options[j][1])) if eligible else 0
        choices.append(selected)
    return np.array(choices, dtype=int)


def _block_guards(full_cost, full_served, demand, early_cost, early_served,
                  early_demand, early_weeks, late_weeks, config):
    """Half-period scores preserve the full run's state and existing warmup."""
    combined = np.ones(full_cost.shape[:2], dtype=bool)
    blocks = []
    for name, costs, served, denominator, weeks in (
        ("early", early_cost, early_served, early_demand, early_weeks),
        ("late", full_cost - early_cost, full_served - early_served, demand - early_demand, late_weeks)):
        fills = np.divide(served, denominator[:, None, None], out=np.full_like(served, np.nan),
                          where=denominator[:, None, None] > 0)
        mean_loss = fills[:, 0, :].mean(axis=1)[:, None] - fills.mean(axis=2)
        worst_loss = np.max(fills[:, 0:1, :] - fills, axis=2)
        cost_increase = costs.mean(axis=2) - costs[:, 0, :].mean(axis=1)[:, None]
        eligible = (np.isfinite(fills).all(axis=2)
                    & (weeks[:, None] >= config["minimum_block_weeks"])
                    & (mean_loss <= config["block_mean_fill_loss_tolerance"] + 1e-12)
                    & (worst_loss <= config["block_worst_seed_fill_loss_tolerance"] + 1e-12)
                    & (cost_increase <= config["block_mean_cost_increase_tolerance"] + 1e-9))
        combined &= eligible
        blocks.append(dict(name=name, costs=costs, served=served, demand=denominator, weeks=weeks,
                           fills=fills, mean_fill_loss=mean_loss, worst_seed_fill_loss=worst_loss,
                           mean_cost_increase=cost_increase, guard_pass=eligible))
    return combined, blocks


def _validation_cohort_guards(data, selected, costs, served, demand, config):
    groups = defaultdict(list)
    for i, (site, pid) in enumerate(data["keys"]):
        groups[("site_id", site)].append(i)
        groups[("criticality", study._category(data["parts"][pid].get("criticality")))].append(i)
    guards = []
    for (dimension, key), members in sorted(groups.items()):
        ids = np.array(members, dtype=int)
        denom = float(demand[ids].sum())
        bcost = costs[ids, 0, :].sum(axis=0)
        scost = costs[ids, selected[ids], :].sum(axis=0)
        bserved = served[ids, 0, :].sum(axis=0)
        sserved = served[ids, selected[ids], :].sum(axis=0)
        bfill = bserved / denom if denom else None
        sfill = sserved / denom if denom else None
        is_a = dimension == "criticality" and key.strip().upper() == "A"
        mean_tolerance = config["criticality_a_tolerance"] if is_a else config["mean_fill_tolerance"]
        worst_tolerance = config["criticality_a_tolerance"] if is_a else config["worst_seed_fill_tolerance"]
        mean_loss = float(np.mean(bfill - sfill)) if denom else None
        worst_loss = float(np.max(bfill - sfill)) if denom else None
        guards.append({"dimension": dimension, "key": key, "series_count": len(members),
            "demand": denom, "baseline_mean_cost": float(bcost.mean()), "selected_mean_cost": float(scost.mean()),
            "baseline_mean_fill": float(bfill.mean()) if denom else None,
            "selected_mean_fill": float(sfill.mean()) if denom else None,
            "mean_fill_loss": mean_loss, "worst_seed_fill_loss": worst_loss,
            "mean_fill_tolerance": mean_tolerance, "worst_seed_fill_tolerance": worst_tolerance,
            "relative_service_guard_met": bool(mean_loss <= mean_tolerance + 1e-12 and worst_loss <= worst_tolerance + 1e-12) if denom else None,
            "absolute_target_met": bool(sfill.mean() + 1e-12 >= config["target"]) if denom else False,
            "cost_nonincrease_met": bool(scost.mean() <= bcost.mean() + 1e-9),
            "baseline_cost_by_seed": bcost.tolist(), "selected_cost_by_seed": scost.tolist(),
            "baseline_fill_by_seed": bfill.tolist() if denom else None,
            "selected_fill_by_seed": sfill.tolist() if denom else None})
    return guards


def _select(data, base_config, predictions, sigma, maes, templates, progress, cancel, *, config):
    if data["y"].shape[1] != study.CUT or len(data["dates"]) != study.CUT:
        raise ValueError("The optimizer accepts only the 130-week development prefix.")
    if any(key in data for key in ("dataset", "histories", "test", "forecasts")):
        raise ValueError("Unexpected full-history input to the development-only selector.")
    options = candidates(config)
    version2 = config["optimizer_version"] == "joint-cost-service-v2"
    n, k, r = len(data["keys"]), len(options), len(config["validation_seeds"])
    costs, served, backlogs = (np.empty((n, k, r)) for _ in range(3))
    early_cost = np.empty((n, k, r)) if version2 else None
    early_served = np.empty((n, k, r)) if version2 else None
    early_demand = early_weeks = None
    demand = None
    draws = [study._lead_draws(seed, data["keys"], data["samples"]) for seed in config["validation_seeds"]]
    flow = {"conservation_pass": True, "max_inventory_flow_error": 0.0,
            "minimum_inventory_state": 0.0, "series_week_checks": 0, "max_draw_weeks": 0}
    completed = 0
    for j, (model, buffer) in enumerate(options):
        model_index = study.MODELS.index(model)
        for s in range(r):
            study._check_cancel(cancel)
            metrics, final_backlog, _, check = study._simulate(data["y"], predictions[:, model_index],
                data["initial"], data["backlog"], data["lead_mean"], data["lead_sd"], sigma[:, model_index],
                data["cost"], buffer, draws[s], study.CUT, study.START + data["warmup"],
                carry_rate=config["carry_rate"], cancel=cancel)
            if demand is None:
                demand = metrics[:, 0].copy()
            elif not np.array_equal(demand, metrics[:, 0]):
                raise ArithmeticError("Validation candidates did not share identical scored demand.")
            costs[:, j, s], served[:, j, s], backlogs[:, j, s] = metrics[:, 2], metrics[:, 1], final_backlog
            flow["max_inventory_flow_error"] = max(flow["max_inventory_flow_error"], check["max_inventory_flow_error"])
            flow["minimum_inventory_state"] = min(flow["minimum_inventory_state"], check["minimum_inventory_state"])
            flow["series_week_checks"] += check["series_week_checks"]
            flow["max_draw_weeks"] = max(flow["max_draw_weeks"], check["max_draw_weeks"])
            if version2:
                # Replaying the identical prefix to a fixed midpoint yields the
                # exact early accumulated scores. Late scores are full minus
                # early; no inventory, pipeline, or backlog reset is introduced.
                early, _, _, early_check = study._simulate(data["y"], predictions[:, model_index],
                    data["initial"], data["backlog"], data["lead_mean"], data["lead_sd"], sigma[:, model_index],
                    data["cost"], buffer, draws[s], config["validation_block_split"],
                    study.START + data["warmup"], carry_rate=config["carry_rate"], cancel=cancel)
                early_cost[:, j, s], early_served[:, j, s] = early[:, 2], early[:, 1]
                if early_demand is None:
                    early_demand, early_weeks = early[:, 0].copy(), early[:, 6].copy()
                elif not np.array_equal(early_demand, early[:, 0]):
                    raise ArithmeticError("Validation block candidates did not share scored demand.")
                flow["max_inventory_flow_error"] = max(flow["max_inventory_flow_error"], early_check["max_inventory_flow_error"])
                flow["minimum_inventory_state"] = min(flow["minimum_inventory_state"], early_check["minimum_inventory_state"])
                flow["series_week_checks"] += early_check["series_week_checks"]
            completed += 1
            if completed % 5 == 0:
                progress(f"Comparing cost and service on validation: {completed}/{k*r} candidate-seed evaluations")
    fills = np.divide(served, demand[:, None, None], out=np.full_like(served, np.nan), where=demand[:, None, None] > 0)
    is_a = np.array([str(data["parts"][pid].get("criticality", "")).strip().upper() == "A" for _, pid in data["keys"]])
    scores = _selection_masks(costs, fills, is_a, config)
    block_pass, blocks = None, []
    if version2:
        full_weeks = study.CUT - study.START - data["warmup"]
        block_pass, blocks = _block_guards(costs, served, demand, early_cost, early_served,
            early_demand, early_weeks, full_weeks - early_weeks, config)
        scores["guard_pass"] &= block_pass
        scores["eligible"] &= block_pass
        # This is a declared whole-class protection rule, not a decision about
        # individual identities selected after inspecting evaluation outcomes.
        scores["eligible"][is_a, :] = False
    mean_backlog = backlogs.mean(axis=2)
    selected = _choose(scores, mean_backlog, options)
    policies = []
    for i, template in enumerate(templates):
        j = int(selected[i])
        model, buffer = options[j]
        model_index = study.MODELS.index(model)
        fallback = j == 0
        valid = bool(np.isfinite(scores["mean_fill"][i, j]))
        absolute = bool(scores["absolute_target_met"][i, j])
        protected = bool(version2 and is_a[i])
        if protected:
            status = "baseline_protected_criticality_a"
            reason = "Class A protection rule: retain the exact baseline for every Class A site-part, irrespective of candidate scores."
        elif not fallback:
            status = "cost_saving_candidate"
            reason = "Lowest mean validation carrying cost among cost-improving candidates meeting absolute, relative, and worst-seed service guards."
        elif not valid:
            status = "baseline_fallback_undefined_service"
            reason = "No positive scored validation demand; retain the exact baseline and flag service as undefined."
        elif version2 and not block_pass[i, j]:
            status = "baseline_fallback_unresolved_block"
            reason = "No eligible cost-saving candidate passed both chronological block checks; retain the baseline and expose the unresolved block guard."
        elif not absolute:
            status = "baseline_fallback_service_shortfall"
            reason = "No cost-improving candidate met every service guard; retain the exact baseline and disclose its absolute service shortfall."
        else:
            status = "baseline_fallback"
            reason = "No candidate improved mean carrying cost while meeting every service guard; retain the exact baseline."
        policy = {**template, "model": model, "z": buffer, "buffer_z": buffer,
            "validation_feasible": bool(scores["guard_pass"][i, j]), "feasible": bool(scores["guard_pass"][i, j]),
            "validation_fill": float(scores["mean_fill"][i, j]) if valid else None,
            "validation_mae": float(maes[i, model_index]), "validation_carrying_cost": float(scores["mean_cost"][i, j]),
            "validation_end_backlog": float(mean_backlog[i, j]), "validation_scored_demand": float(demand[i]),
            "residual_sigma": float(sigma[i, model_index]), "selection_status": status,
            "baseline_fallback": fallback, "validation_guard_pass": bool(scores["guard_pass"][i, j]),
            "selection_reason": reason, "validation_absolute_target_met": absolute,
            "validation_baseline_fill": float(scores["baseline_fill"][i]) if valid else None,
            "validation_baseline_cost": float(scores["baseline_cost"][i]),
            "validation_mean_fill_loss": float(scores["mean_fill_loss"][i, j]) if valid else None,
            "validation_worst_seed_loss": float(scores["worst_seed_loss"][i, j]) if valid else None,
            "validation_mean_cost_saving": float(scores["mean_cost_saving"][i, j]),
            "validation_service_floor": float(scores["service_floor"][i]) if valid else None,
            "candidate_count": k, "feasible_candidate_count": int(scores["eligible"][i].sum()),
            "service_guard_candidate_count": int(scores["guard_pass"][i].sum()),
            "selected_candidate_index": j, "validation_seeds": list(config["validation_seeds"]),
            "validation_costs_by_seed": costs[i, j].tolist(),
            "validation_fills_by_seed": fills[i, j].tolist() if valid else [None] * r}
        if version2:
            policy["criticality_protected"] = protected
            policy["validation_block_guard_pass"] = bool(block_pass[i, j])
            for block in blocks:
                name = block["name"]
                policy[f"validation_{name}_mean_fill_loss"] = float(block["mean_fill_loss"][i, j])
                policy[f"validation_{name}_worst_seed_fill_loss"] = float(block["worst_seed_fill_loss"][i, j])
                policy[f"validation_{name}_mean_cost_increase"] = float(block["mean_cost_increase"][i, j])
                policy[f"validation_{name}_scored_demand"] = float(block["demand"][i])
                policy[f"validation_{name}_scored_weeks"] = int(block["weeks"][i])
        policies.append(policy)
    guards = _validation_cohort_guards(data, selected, costs, served, demand, config)
    if any(g["relative_service_guard_met"] is False or not g["cost_nonincrease_met"] for g in guards):
        raise ArithmeticError("Selected policies violated a declared validation cohort guard.")
    ix = np.arange(n)
    details = {"version": config["optimizer_version"], "policy_mode": "cost_service",
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "objective": "Minimum mean validation ending-inventory carrying cost among enumerated candidates with positive baseline cost saving and all service guards satisfied.",
        "selection_scope": "Joint forecast-model and buffer selection independently for every site-part; shared stochastic validation leads across candidates.",
        "candidate_count": k, "validation_seed_count": r, "validation_seeds": list(config["validation_seeds"]),
        "candidate_seed_simulations": k * r, "site_part_candidate_seed_evaluations": n * k * r,
        "baseline_candidate_index": 0, "baseline": {"model": config["baseline_model"], "z": config["baseline_z"]},
        "guards": {"absolute_mean_fill_target": config["target"], "mean_fill_loss_tolerance": config["mean_fill_tolerance"],
            "worst_seed_fill_loss_tolerance": config["worst_seed_fill_tolerance"],
            "criticality_a_mean_and_worst_seed_loss_tolerance": config["criticality_a_tolerance"],
            "numerical_service_tolerance": 1e-12, "minimum_cost_saving": 1e-9},
        "tie_break": "Mean carrying cost, mean ending backlog, fixed model order, buffer z; exact baseline retained when no strictly cost-improving candidate is feasible.",
        "adopted_candidate_count": int(np.count_nonzero(selected)), "baseline_fallback_count": int(np.count_nonzero(selected == 0)),
        "selection_status_counts": dict(Counter(p["selection_status"] for p in policies)),
        "validation_baseline_cost": float(scores["baseline_cost"].sum()),
        "validation_selected_cost": float(scores["mean_cost"][ix, selected].sum()),
        "validation_baseline_fill": float(served[:, 0, :].sum(axis=0).mean() / demand.sum()) if demand.sum() else None,
        "validation_selected_fill": float(served[ix, selected, :].sum(axis=0).mean() / demand.sum()) if demand.sum() else None,
        "validation_cohort_guards": guards, "search_complete": True,
        "global_optimality_claim": False, "test_used_in_candidate_selection": False,
        "evidence_status": "Exploratory redesign after the original test outcomes were examined; the same evaluation period is no longer an untouched confirmatory holdout.",
        "generalization_limit": "Validation constraints hold for the fixed candidate set and five sampled lead paths. They do not guarantee future service or globally optimal inventory decisions.",
        "candidate_evidence_location": "Frozen snapshot selection_evidence; axes series,candidate,validation seed."}
    evidence = {"keys": [list(key) for key in data["keys"]],
        "candidates": [{"model": model, "buffer_z": buffer} for model, buffer in options],
        "validation_seeds": list(config["validation_seeds"]), "scored_demand": demand,
        "scored_weeks": study.CUT - study.START - data["warmup"],
        "carrying_cost": costs, "immediate_served": served, "ending_backlog": backlogs,
        "service_guard_pass": scores["guard_pass"], "cost_improving_and_service_eligible": scores["eligible"],
        "selected_candidate_indices": selected, "layout": "series,candidate,validation_seed for numeric score cubes; series,candidate for eligibility matrices"}
    if version2:
        details.update(protected_criticalities=["A"], protected_series_count=int(is_a.sum()),
            validation_block_split=config["validation_block_split"],
            block_guard_rule="Each half requires positive scored demand, at least four scored weeks, no mean or worst-seed fill loss, and no mean carrying-cost increase relative to baseline.",
            validation_block_state="Same continuous replay and shared lead draws; existing warmup retained; late scores equal full minus early scores.",
            validation_block_cohort_guards=[{"block": block["name"], "cohorts": _validation_cohort_guards(
                data, selected, block["costs"], block["served"], block["demand"], config)} for block in blocks],
            stopping_rule="Exactly this v2 primary comparison and the predefined 25% longer-lead sensitivity; no further selection retuning in this evaluation pass.")
        details["objective"] += " Class A is restricted to the exact baseline; other adoptions must also pass both chronological half-period cost and service guards."
        details["candidate_seed_simulations"] = k * r * 2
        details["evidence_status"] = "Exploratory second redesign after the original and v1 evaluation outcomes were examined; the same evaluation period is not an untouched confirmatory holdout."
        evidence.update(validation_block_split=config["validation_block_split"],
            early_carrying_cost=early_cost, early_immediate_served=early_served,
            early_scored_demand=early_demand, early_scored_weeks=early_weeks,
            block_guard_pass=block_pass, protected_criticality_a=is_a,
            late_score_derivation="Subtract early from full scores; no state reset.")
    policies = study._native(policies)
    return {"policies": policies, "details": details, "evidence": evidence, "flow": flow}


def run_optimized_study(dataset, config=None, progress=lambda done, total, message: None,
                        cancel=None, freeze_callback=None):
    """Use versioned development-only selection and the unchanged paired replay."""
    checked = config_checked(config)
    base = {key: checked[key] for key in study.DEFAULTS}
    def selector(*args):
        return _select(*args, config=checked)
    result = study.run_study(dataset, base, progress, cancel, freeze_callback,
                            _policy_selector=selector, _config_snapshot=checked)
    observed = []
    for dimension in ("site_id", "criticality"):
        for row in result["cohorts"][dimension]:
            is_a = dimension == "criticality" and row["key"].strip().upper() == "A"
            tolerance = checked["criticality_a_tolerance"] if is_a else checked["mean_fill_tolerance"]
            loss = row["baseline_fill"] - row["selected_fill"] if row["demand"] else None
            observed.append({"dimension": dimension, "key": row["key"], "demand": row["demand"],
                "baseline_cost": row["baseline_cost"], "selected_cost": row["selected_cost"],
                "baseline_fill": row["baseline_fill"], "selected_fill": row["selected_fill"],
                "fill_loss": loss, "validation_design_mean_loss_tolerance": tolerance,
                "observed_relative_service_guard_met": bool(loss <= tolerance + 1e-12) if loss is not None else None,
                "observed_absolute_target_met": bool(row["selected_fill"] >= checked["target"]) if row["demand"] else False,
                "observed_cost_nonincrease_met": bool(row["selected_cost"] <= row["baseline_cost"] + 1e-9)})
    result["optimization"] = {**result["provenance"]["optimization"], "evaluation_cohort_checks": observed,
        "evaluation_checks_status": "Descriptive post-selection observations, not additional predeclared hypothesis tests."}
    result["inference"]["evidence_status"] = "Exploratory paired simulation comparison on a previously examined evaluation period; p values do not establish independent confirmatory evidence."
    result["diagnostics"]["warnings"].append(result["optimization"]["evidence_status"])
    return result
