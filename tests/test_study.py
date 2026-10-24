"""Known-answer, isolation, and aggregation tests for the paired study engine."""
import copy
import json
import math
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.engine import Cancelled, simulate as scalar_simulate
from app.forecast import forecasts
from app.store import Store
from app import study


def fixture():
    start = date(2022, 1, 3)
    parts = {
        "P1": dict(part_id="P1", description="Small part", family="Hydraulics", criticality="A",
                   unit_cost=10.0, lead_time_days=14, supplier_risk="High", repairable="Yes"),
        "P2": dict(part_id="P2", description="Large part", family="Electrical", criticality="B",
                   unit_cost=500.0, lead_time_days=28, supplier_risk="Low", repairable="No"),
    }
    groups = {}
    for site, pid in (("S1", "P1"), ("S2", "P1"), ("S1", "P2")):
        pattern = [0, 3, 0, 1, 5, 0, 0, 2] if pid == "P1" else [2, 1, 3, 4]
        groups[(site, pid)] = [dict(site_id=site, part_id=pid,
            week=(start + timedelta(weeks=t)).isoformat(), demand=pattern[t % len(pattern)],
            on_hand=30.0 if pid == "P1" else 80.0, blocked_stock=1.0, backorders=0.0)
            for t in range(156)]
    orders = [dict(site_id="S1", part_id="P1", order_date="2022-01-03",
                   receipt_date=(start + timedelta(days=days)).isoformat()) for days in (7, 14, 21)]
    orders.append(dict(site_id="S2", part_id="P1", order_date="2022-01-03", receipt_date="2022-01-31"))
    # Future receipts must not enter the fitted lead distribution.
    orders.append(dict(site_id="S1", part_id="P1", order_date="2023-06-20", receipt_date="2023-12-01"))
    meta = dict(id="fixture", title="Independent test fixture", start="2022-01-03", end="2024-12-23",
                source_kind="demo", warnings=[], file_hashes={"fixture": "test-only"})
    return meta, parts, groups, orders, []


class ConfigurationTests(unittest.TestCase):
    def test_protocol_structure_and_bounds_are_enforced(self):
        invalid = [{"replications": 1}, {"replications": 2.5}, {"replications": True},
                   {"carry_rate": float("nan")}, {"carry_rate": -1}, {"target": 0},
                   {"target": 1.01}, {"lead_factor": 0}, {"seed_start": -1},
                   {"seed_start": 2147483647, "replications": 2},
                   {"training_weeks": 52}, {"models": ["ma8"]}, {"unknown": 3}]
        for settings in invalid:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                study.config_checked(settings)
        checked = study.config_checked({"replications": "2", "name": "  Trial  "})
        self.assertEqual(checked["replications"], 2)
        self.assertEqual(checked["name"], "Trial")
        checked["models"].clear()
        self.assertEqual(study.DEFAULTS["models"], list(study.MODELS))


class SimulatorTests(unittest.TestCase):
    def test_five_week_known_answer_and_conservation(self):
        y = np.zeros((1, 83)); y[0, 79:] = 2
        pred = np.full((1, 84), 2.0)
        m, backlog, _, flow = study._simulate(y, pred, np.array([2.0]), np.array([0.0]),
            np.array([7.0]), np.array([0.0]), np.array([0.0]), np.array([10.0]), 0.0,
            np.ones((1, 83), dtype=int), 83, 78)
        self.assertEqual(m[0, 0], 8)
        self.assertEqual(m[0, 1], 8)
        self.assertEqual(m[0, 4], 0)
        self.assertEqual(backlog[0], 0)
        self.assertAlmostEqual(m[0, 2], 2 * 10 * .24 / 52)
        self.assertTrue(flow["conservation_pass"])
        self.assertEqual(flow["max_inventory_flow_error"], 0)
        self.assertEqual(flow["series_week_checks"], 5)

    def test_old_backlog_precedes_new_demand(self):
        y = np.zeros((1, 79)); y[0, 78] = 2
        m, backlog, _, _ = study._simulate(y, np.zeros((1, 80)), np.array([3.0]), np.array([2.0]),
            np.array([7.0]), np.array([0.0]), np.array([0.0]), np.array([10.0]), 0.0,
            np.ones((1, 79), dtype=int), 79, 78)
        self.assertEqual(m[0, 1], 1)
        self.assertEqual(backlog[0], 1)
        self.assertEqual(m[0, 4], 1)

    def test_vectorized_results_match_independent_scalar_reference(self):
        rng = np.random.default_rng(17)
        y = rng.integers(0, 9, size=(3, 156)).astype(float)
        pred = np.array([forecasts(row.tolist())["ma8"] for row in y])
        stock, backlog = np.array([3., 25., 100.]), np.array([0., 4., 12.])
        meanlead, sdlead = np.array([7., 19., 35.]), np.array([0., 3., 9.])
        sigma, costs = np.array([2., 5., 1.]), np.array([10., 77., 1000.])
        draws = rng.integers(1, 10, size=(3, 156))
        for buffer in (0., 1.645, 6.):
            m, b, _, flow = study._simulate(y, pred, stock, backlog, meanlead, sdlead,
                sigma, costs, buffer, draws, 156, 130)
            for i in range(3):
                scalar = scalar_simulate(y[i].tolist(), pred[i].tolist(), 78, 156,
                    {"stock": stock[i], "backlog": backlog[i], "pipeline": []},
                    {"mean_days": meanlead[i], "std_days": sdlead[i]},
                    {"carry_rate": .24, "review_weeks": 1}, buffer, sigma[i], costs[i],
                    draws[i].tolist(), score_start=130)
                expected = [scalar["demand"], scalar["immediate_filled"], scalar["carrying_cost"],
                    scalar["avg_on_hand"] * scalar["weeks"], scalar["stockout_weeks"],
                    scalar["ordered_units"], scalar["weeks"]]
                np.testing.assert_allclose(m[i], expected, atol=1e-9, rtol=1e-12)
                self.assertEqual(b[i], scalar["end_backlog"])
            self.assertTrue(flow["conservation_pass"])

    def test_statistical_direction_zero_variance_and_noninferiority(self):
        equal_mean = study._inference([-1., 0., 1.], 0.)
        self.assertAlmostEqual(equal_mean["p_one_sided"], .5)
        self.assertFalse(equal_mean["reject_null"])
        saving = study._inference([4., 5., 6.], 0.)
        cost_increase = study._inference([-4., -5., -6.], 0.)
        self.assertTrue(saving["reject_null"])
        self.assertFalse(cost_increase["reject_null"])
        service = study._inference([-.009, -.008, -.0095, -.0085], -.01)
        self.assertTrue(service["reject_null"])
        self.assertLess(service["mean"], 0)
        degenerate = study._inference([2., 2.], 0.)
        self.assertFalse(degenerate["test_available"])
        self.assertFalse(degenerate["reject_null"])
        self.assertIsNone(degenerate["p_one_sided"])


class IntegratedStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.result = study.run_study(cls.data, {"replications": 4})

    def test_canonical_store_round_trip_and_repeatability(self):
        meta, parts, groups, orders, quality = self.data
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            store.save_dataset(meta, list(parts.values()), [r for rows in groups.values() for r in rows], orders, quality)
            repeated = study.run_study(store.load(), {"replications": 4})
        self.assertEqual(repeated["summary"], self.result["summary"])
        self.assertEqual(repeated["replications"], self.result["replications"])
        self.assertEqual(repeated["provenance"]["policies_sha256"], self.result["provenance"]["policies_sha256"])
        json.dumps(repeated, allow_nan=False)

    def test_holdout_changes_cannot_select_policies(self):
        changed = copy.deepcopy(self.data)
        for rows in changed[2].values():
            for row in rows[130:]:
                row["demand"] = row["demand"] * 50 + 7
        original = copy.deepcopy(changed)
        result = study.run_study(changed, {"replications": 4})
        self.assertEqual(result["policies"], self.result["policies"])
        self.assertEqual(result["provenance"]["development_inputs_sha256"], self.result["provenance"]["development_inputs_sha256"])
        self.assertNotEqual(result["summary"], self.result["summary"])
        self.assertEqual(changed, original)
        for key in result["forecasts"]:
            self.assertEqual(result["forecasts"][key]["history"][130]["predicted"],
                             self.result["forecasts"][key]["history"][130]["predicted"])

    def test_freeze_precedes_full_predictions_and_can_abort(self):
        observed = []
        real_predictions = study._predictions
        def observed_predictions(y, cancel=None):
            observed.append(y.shape[1])
            return real_predictions(y, cancel)
        def capture(snapshot):
            self.assertEqual(observed, [130])
            self.assertFalse(snapshot["test_outcomes_evaluated"])
            self.assertEqual(snapshot["provenance"]["policies_sha256"], study._hash(snapshot["policies"]))
            snapshot["policies"][0]["model"] = "tampered callback copy"
        with patch.object(study, "_predictions", observed_predictions):
            result = study.run_study(self.data, {"replications": 4}, freeze_callback=capture)
        self.assertEqual(observed, [130, 156])
        self.assertEqual(result["policies"], self.result["policies"])
        def abort(_):
            raise RuntimeError("cannot persist freeze")
        observed.clear()
        with patch.object(study, "_predictions", observed_predictions), self.assertRaisesRegex(RuntimeError, "cannot persist"):
            study.run_study(self.data, {"replications": 2}, freeze_callback=abort)
        self.assertEqual(observed, [130])

    def test_lead_factor_is_frozen_policy_sensitivity(self):
        altered = study.run_study(self.data, {"replications": 4, "lead_factor": 1.25})
        self.assertEqual(altered["policies"], self.result["policies"])
        self.assertEqual(altered["provenance"]["policies_sha256"], self.result["provenance"]["policies_sha256"])
        self.assertNotEqual(altered["summary"], self.result["summary"])
        self.assertEqual(altered["provenance"]["selection_lead_factor"], 1.0)
        self.assertEqual(altered["provenance"]["evaluation_lead_factor"], 1.25)

    def test_training_only_lead_sources_and_unavailable_order_quantities(self):
        policies = {(row["site_id"], row["part_id"]): row for row in self.result["policies"]}
        self.assertEqual(policies[("S1", "P1")]["lead_samples_days"], [7, 14, 21])
        self.assertEqual(policies[("S1", "P1")]["lead_source"], "site-part")
        self.assertEqual(policies[("S2", "P1")]["lead_samples_days"], [7, 14, 21, 28])
        self.assertEqual(policies[("S2", "P1")]["lead_source"], "part-pooled")
        self.assertEqual(policies[("S1", "P2")]["lead_source"], "nominal")
        for row in self.result["series"]:
            self.assertIsNone(row["estimated_order_units"])
            self.assertIsNone(row["current_pipeline"])
            self.assertGreaterEqual(row["target_units"], 0)

    def test_cohorts_are_demand_weighted_and_reconcile(self):
        total_demand = self.result["diagnostics"]["test_demand"]
        for dimension, rows in self.result["cohorts"].items():
            with self.subTest(dimension=dimension):
                self.assertEqual(sum(row["series_count"] for row in rows), 3)
                self.assertAlmostEqual(sum(row["demand"] for row in rows), total_demand)
                for label in ("baseline", "selected"):
                    self.assertAlmostEqual(sum(row[f"{label}_cost"] for row in rows),
                                           self.result["summary"][label]["carrying_cost"])
                    for row in rows:
                        self.assertAlmostEqual(row[f"{label}_fill"], row[f"{label}_served"] / row["demand"])
        self.assertEqual(len(self.result["weekly"]), 26)
        for label in ("baseline", "selected"):
            self.assertAlmostEqual(sum(row[label]["carrying_cost"] for row in self.result["weekly"]),
                                   self.result["summary"][label]["carrying_cost"])
        self.assertTrue(self.result["diagnostics"]["conservation_pass"])

    def test_zero_demand_remains_undefined_and_infeasible(self):
        data = fixture()
        for rows in data[2].values():
            for row in rows:
                row["demand"] = 0
                row["on_hand"] = 0
                row["blocked_stock"] = 0
        result = study.run_study(data, {"replications": 2})
        self.assertEqual(result["diagnostics"]["validation_infeasible_count"], 3)
        self.assertTrue(all(p["validation_fill"] is None and not p["feasible"] for p in result["policies"]))
        self.assertTrue(all(p["model"] == "ma8" for p in result["policies"]))
        self.assertIsNone(result["summary"]["selected"]["fill_rate"])
        self.assertFalse(result["inference"]["service"]["test_available"])
        self.assertFalse(result["inference"]["absolute_target_met"])
        self.assertFalse(result["inference"]["joint_with_target_met"])
        json.dumps(result, allow_nan=False)

    def test_invalid_histories_fail_instead_of_silent_exclusion(self):
        for change, message in ((lambda rows: rows.pop(4), "exactly 156"),
                                (lambda rows: rows[4].update(week=rows[3]["week"]), "duplicate"),
                                (lambda rows: rows[77].update(on_hand=None), "on_hand"),
                                (lambda rows: rows[140].update(demand=-1), "nonnegative")):
            data = fixture()
            change(data[2][("S1", "P1")])
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                study.run_study(data, {"replications": 2})

    def test_cancellation_and_missing_initial_optional_fields_are_explicit(self):
        event = threading.Event(); event.set()
        with self.assertRaises(Cancelled):
            study.run_study(self.data, {"replications": 2}, cancel=event)
        event.clear()
        def freeze(_):
            event.set()
        with self.assertRaises(Cancelled):
            study.run_study(self.data, {"replications": 2}, cancel=event, freeze_callback=freeze)
        data = fixture()
        data[2][("S1", "P1")][77]["blocked_stock"] = None
        result = study.run_study(data, {"replications": 2})
        self.assertEqual(result["diagnostics"]["initial_value_assumptions"]["blocked_stock"], 1)
        self.assertTrue(any("Assumed zero blocked_stock" in item for item in result["diagnostics"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
