"""Guard, fallback, freezing, and holdout isolation tests for joint selection."""
import copy
import json
import threading
import unittest
from unittest.mock import patch

import numpy as np

from app import optimization, study
from app.engine import Cancelled
from test_study import fixture


class SelectionRuleTests(unittest.TestCase):
    def test_cost_objective_service_guards_and_exact_baseline_fallback(self):
        config = optimization.config_checked({"replications": 2,"optimizer_version":"joint-cost-service-v1"})
        costs = np.array([[[10]*5, [9]*5, [8]*5, [11]*5],
                          [[10]*5, [9]*5, [8]*5, [11]*5],
                          [[10]*5, [9]*5, [8]*5, [11]*5]], dtype=float)
        fills = np.array([
            [[.97]*5, [.969]*5, [.97]*5, [1.0]*5],
            [[.98]*5, [.976]*5, [.969,.99,.99,.99,.99], [1.0]*5],
            [[.93]*5, [.94]*5, [.945]*5, [.96]*5],
        ])
        scores = optimization._selection_masks(costs, fills, np.array([True, False, False]), config)
        options = [("ma8",1.645), ("ma8",1.), ("sba",1.5), ("tsb",2.)]
        chosen = optimization._choose(scores, np.zeros((3, 4)), options)
        self.assertEqual(chosen.tolist(), [2, 1, 0])
        self.assertFalse(scores["guard_pass"][0, 1], "Class A cannot accept even a .1pp validation drop")
        self.assertFalse(scores["worst_seed_guard"][1, 2], "Average service cannot conceal one poor shared-seed path")
        self.assertFalse(scores["guard_pass"][2, 0], "Baseline fallback below95% must remain visibly infeasible")
        self.assertFalse(scores["eligible"][2, 3], "A more costly target-feasible option is not a cost improvement")

    def test_undefined_service_and_cost_ties_do_not_force_adoption(self):
        config = optimization.config_checked({"replications": 2})
        costs = np.ones((2, 3, 5))
        fills = np.ones((2, 3, 5)); fills[0] = np.nan
        scores = optimization._selection_masks(costs, fills, np.array([False, False]), config)
        chosen = optimization._choose(scores, np.zeros((2, 3)), [("ma8",1.645), ("sba",0.), ("tsb",0.)])
        self.assertEqual(chosen.tolist(), [0,0])
        self.assertFalse(scores["guard_pass"][0].any())
        self.assertFalse(scores["eligible"].any())

    def test_exhaustive_bounded_candidates_and_fixed_settings(self):
        config = optimization.config_checked()
        options = optimization.candidates(config)
        self.assertEqual(len(options), 66)
        self.assertEqual(len(set(options)), 66)
        self.assertEqual(options[0], ("ma8", 1.645))
        self.assertTrue(all((model, 1.645) in options for model in study.MODELS))
        self.assertEqual(config["validation_seeds"], [42,43,44,45,46])
        for setting in ({"policy_mode":"research"}, {"validation_seeds":[42]},
                        {"criticality_a_tolerance":.01}, {"mean_fill_tolerance":.02},
                        {"seed_start":42}, {"seed_start":40,"replications":10}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                optimization.config_checked(setting)
        config["validation_seeds"].clear()
        self.assertEqual(optimization.DEFAULTS["validation_seeds"], [42,43,44,45,46])

    def test_v2_block_guards_reject_hidden_service_and_cost_tradeoffs(self):
        config = optimization.config_checked()
        costs = np.array([[[20]*5,[18]*5,[18]*5,[18]*5,[18]*5]], dtype=float)
        early_cost = np.array([[[10]*5,[9]*5,[11]*5,[9]*5,[9]*5]], dtype=float)
        served = np.array([[[16]*5,[16]*5,[17]*5,[17]*5,[17]*5]], dtype=float)
        early_served = np.array([[[8]*5,[7]*5,[9]*5,[7,9,9,9,9],[9]*5]], dtype=float)
        mask, blocks = optimization._block_guards(costs,served,np.array([20.]),early_cost,
            early_served,np.array([10.]),np.array([22.]),np.array([26.]),config)
        self.assertEqual(mask.tolist(), [[True,False,False,False,True]])
        self.assertGreaterEqual(blocks[0]["fills"][0,3].mean(),blocks[0]["fills"][0,0].mean())
        self.assertGreater(blocks[0]["worst_seed_fill_loss"][0,3],0)
        self.assertGreater(blocks[0]["mean_cost_increase"][0,2],0)
        no_demand,_ = optimization._block_guards(costs,served,np.array([20.]),early_cost,
            np.zeros_like(early_served),np.array([0.]),np.array([22.]),np.array([26.]),config)
        self.assertFalse(no_demand.any())


class OptimizedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = fixture()
        cls.snapshots = []
        cls.result = optimization.run_optimized_study(cls.dataset, {"replications":2}, freeze_callback=cls.snapshots.append)

    def test_frozen_candidate_evidence_precedes_evaluation_and_hashes_match(self):
        self.assertEqual(len(self.snapshots), 1)
        snapshot = self.snapshots[0]
        self.assertFalse(snapshot["test_outcomes_evaluated"])
        self.assertEqual(snapshot["config"]["policy_mode"], "cost_service")
        self.assertEqual(study._hash(snapshot["config"]), snapshot["provenance"]["config_sha256"])
        self.assertEqual(study._hash(snapshot["policies"]), snapshot["provenance"]["policies_sha256"])
        evidence = snapshot["selection_evidence"]
        self.assertEqual(study._hash(evidence), snapshot["provenance"]["selection_evidence_sha256"])
        self.assertEqual(np.array(evidence["carrying_cost"]).shape, (3,66,5))
        self.assertEqual(np.array(evidence["immediate_served"]).shape, (3,66,5))
        self.assertEqual(evidence["candidates"][0], {"model":"ma8","buffer_z":1.645})
        self.assertEqual(evidence["validation_seeds"], [42,43,44,45,46])
        json.dumps(snapshot, allow_nan=False)
        json.dumps(self.result, allow_nan=False)

    def test_test_demand_cannot_change_selected_policies_or_validation_evidence(self):
        modified = copy.deepcopy(self.dataset)
        for rows in modified[2].values():
            for row in rows[130:]:
                row["demand"] = row["demand"]*100+9
        before = copy.deepcopy(modified)
        snapshots = []
        result = optimization.run_optimized_study(modified, {"replications":2}, freeze_callback=snapshots.append)
        self.assertEqual(result["policies"], self.result["policies"])
        for field in ("policies_sha256","development_inputs_sha256","selection_evidence_sha256"):
            self.assertEqual(result["provenance"][field], self.result["provenance"][field])
        self.assertNotEqual(result["summary"], self.result["summary"])
        self.assertEqual(modified, before)
        self.assertEqual(snapshots[0]["selection_evidence"], self.snapshots[0]["selection_evidence"])

    def test_selector_receives_no_test_or_full_history_and_callback_can_abort(self):
        real_select = optimization._select
        shapes = []
        def inspect(data, *args, **kwargs):
            shapes.append(data["y"].shape)
            self.assertEqual(data["dates"][-1].isoformat(), "2024-06-24")
            self.assertNotIn("histories", data)
            self.assertNotIn("dataset", data)
            self.assertNotIn("meta", data)
            return real_select(data, *args, **kwargs)
        def stop(snapshot):
            self.assertFalse(snapshot["test_outcomes_evaluated"])
            raise RuntimeError("freeze cannot persist")
        prediction_lengths = []
        real_predictions = study._predictions
        def predict(y, cancel=None):
            prediction_lengths.append(y.shape[1])
            return real_predictions(y, cancel)
        with patch.object(optimization, "_select", inspect), patch.object(study, "_predictions", predict):
            with self.assertRaisesRegex(RuntimeError, "cannot persist"):
                optimization.run_optimized_study(self.dataset, {"replications":2}, freeze_callback=stop)
        self.assertEqual(shapes, [(3,130)])
        self.assertEqual(prediction_lengths, [130])

    def test_selected_options_satisfy_declared_validation_constraints(self):
        evidence = self.snapshots[0]["selection_evidence"]
        costs = np.array(evidence["carrying_cost"])
        served = np.array(evidence["immediate_served"])
        demand = np.array(evidence["scored_demand"])
        fills = served / demand[:,None,None]
        for i, policy in enumerate(self.result["policies"]):
            chosen = policy["selected_candidate_index"]
            if policy["baseline_fallback"]:
                self.assertEqual(chosen, 0)
                self.assertEqual((policy["model"],policy["buffer_z"]), ("ma8",1.645))
            else:
                self.assertLess(costs[i,chosen].mean(), costs[i,0].mean())
                self.assertGreaterEqual(fills[i,chosen].mean()+1e-12,.95)
                part = self.dataset[1][policy["part_id"]]
                tolerance = 0 if part["criticality"] == "A" else .005
                seed_tolerance = 0 if part["criticality"] == "A" else .01
                self.assertGreaterEqual(fills[i,chosen].mean()+1e-12,fills[i,0].mean()-tolerance)
                self.assertLessEqual(np.max(fills[i,0]-fills[i,chosen]),seed_tolerance+1e-12)
        for row in self.result["optimization"]["validation_cohort_guards"]:
            self.assertTrue(row["relative_service_guard_met"])
            self.assertTrue(row["cost_nonincrease_met"])
        self.assertFalse(self.result["optimization"]["global_optimality_claim"])
        self.assertIn("Exploratory",self.result["optimization"]["evidence_status"])

    def test_v2_whole_class_protection_and_block_scores(self):
        evidence = self.snapshots[0]["selection_evidence"]
        self.assertEqual(evidence["validation_block_split"],104)
        early_cost = np.array(evidence["early_carrying_cost"])
        late_cost = np.array(evidence["carrying_cost"])-early_cost
        early_served = np.array(evidence["early_immediate_served"])
        late_served = np.array(evidence["immediate_served"])-early_served
        early_demand = np.array(evidence["early_scored_demand"])
        late_demand = np.array(evidence["scored_demand"])-early_demand
        for i, policy in enumerate(self.result["policies"]):
            part=self.dataset[1][policy["part_id"]]
            chosen=policy["selected_candidate_index"]
            if part["criticality"]=='A':
                self.assertTrue(policy["criticality_protected"])
                self.assertEqual(chosen,0)
                self.assertEqual(policy["selection_status"],"baseline_protected_criticality_a")
                row=next(s for s in self.result["series"] if (s["site_id"],s["part_id"])==(policy["site_id"],policy["part_id"]))
                self.assertEqual(row["selected_cost"],row["baseline_cost"])
                self.assertEqual(row["selected_fill"],row["baseline_fill"])
            if not policy["baseline_fallback"]:
                self.assertTrue(policy["validation_block_guard_pass"])
                for cost,served,demand in ((early_cost,early_served,early_demand),(late_cost,late_served,late_demand)):
                    self.assertLessEqual(cost[i,chosen].mean(),cost[i,0].mean()+1e-9)
                    self.assertTrue(np.all(served[i,chosen]/demand[i]+1e-12>=served[i,0]/demand[i]))

    def test_v1_configuration_and_execution_branch_remain_available(self):
        configuration=optimization.config_checked({"optimizer_version":"joint-cost-service-v1","replications":2})
        self.assertEqual(configuration["mean_fill_tolerance"],.005)
        self.assertEqual(configuration["worst_seed_fill_tolerance"],.01)
        self.assertNotIn("validation_block_split",configuration)
        snapshots=[]
        result=optimization.run_optimized_study(self.dataset,configuration,freeze_callback=snapshots.append)
        self.assertEqual(result["optimization"]["version"],"joint-cost-service-v1")
        self.assertNotIn("early_carrying_cost",snapshots[0]["selection_evidence"])
        self.assertFalse(any("criticality_protected" in row for row in result["series"]))

    def test_evaluation_sensitivity_preserves_frozen_selection(self):
        result = optimization.run_optimized_study(self.dataset, {"replications":2,"lead_factor":1.25})
        self.assertEqual(result["policies"], self.result["policies"])
        self.assertEqual(result["provenance"]["selection_evidence_sha256"], self.result["provenance"]["selection_evidence_sha256"])
        self.assertNotEqual(result["summary"], self.result["summary"])

    def test_zero_demand_baseline_fallback_is_not_false_feasibility(self):
        data = fixture()
        for rows in data[2].values():
            for row in rows:
                row.update(demand=0,on_hand=0,blocked_stock=0)
        result = optimization.run_optimized_study(data, {"replications":2})
        for row in result["series"]:
            self.assertTrue(row["baseline_fallback"])
            self.assertIn(row["selection_status"], ("baseline_fallback_undefined_service","baseline_protected_criticality_a"))
            self.assertFalse(row["validation_feasible"])
            self.assertFalse(row["validation_guard_pass"])
        self.assertFalse(result["inference"]["absolute_target_met"])
        json.dumps(result, allow_nan=False)

    def test_cancellation_interrupts_candidate_search(self):
        event = threading.Event()
        def progress(done, total, message):
            if "candidate-seed evaluations" in message:
                event.set()
        with self.assertRaises(Cancelled):
            optimization.run_optimized_study(self.dataset, {"replications":2}, progress=progress, cancel=event)

    def test_forward_intervals_are_display_outputs_not_selection_inputs(self):
        for forecast in self.result["forecasts"].values():
            self.assertEqual(len(forecast["future"]), 13)
            self.assertFalse(forecast["intervals"]["coverage_guarantee"])
            for row in forecast["future"]:
                self.assertLessEqual(row["yhat_lower"],row["predicted"])
                self.assertGreaterEqual(row["yhat_upper"],row["predicted"])
                self.assertGreaterEqual(row["yhat_lower"],0)
            self.assertEqual(forecast["intervals"]["forecast_origin_index"],156)


if __name__ == "__main__":
    unittest.main()
