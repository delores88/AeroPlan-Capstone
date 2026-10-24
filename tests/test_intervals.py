import math
import unittest
from app.forecast import MODELS, future
from app.intervals import prediction_intervals


class PredictionIntervalTests(unittest.TestCase):
    def test_point_forecasts_match_all_existing_models(self):
        history = [0.0 if i % 4 else float(i % 9 + 1) for i in range(156)]
        for model in MODELS:
            with self.subTest(model=model):
                rows = prediction_intervals(history, model)["future"]
                self.assertEqual([row["yhat"] for row in rows], future(history, model, 13))

    def test_multistep_errors_are_calibrated_by_horizon(self):
        # For a last-value forecast of the sequence 0,1,2,..., every h-step
        # historical error is exactly h, giving an independent analytic check.
        result = prediction_intervals(list(range(156)), "naive")
        for h, row in enumerate(result["future"], start=1):
            self.assertEqual(row["yhat"], 155)
            self.assertEqual(row["yhat_lower"], 155 - h)
            self.assertEqual(row["yhat_upper"], 155 + h)
            self.assertEqual(row["calibration_n"], 105 - h)
            cal = result["metadata"]["calibration"][h - 1]
            self.assertLess(cal["last_outcome_index"], 156)

    def test_unobserved_tail_cannot_change_bands(self):
        past = [float((i * 7) % 11) for i in range(100)]
        for model in MODELS:
            expected = prediction_intervals(past, model)
            modified_future = prediction_intervals(
                past + [1e9] * 56, model, forecast_origin=100)
            self.assertEqual(expected, modified_future)

    def test_seasonal_recursion_beyond_one_season_stays_causal(self):
        history = [float(i) for i in range(156)]
        result = prediction_intervals(history, "seasonal52", horizon=60)
        self.assertEqual([r["yhat"] for r in result["future"]],
                         future(history, "seasonal52", 60))
        self.assertEqual(result["future"][52]["yhat"], history[-52])

    def test_sparse_demand_bounds_are_finite_and_nonnegative(self):
        history = [0.0] * 156
        for i in (53, 77, 106, 120, 149):
            history[i] = 20.0
        for model in MODELS:
            for row in prediction_intervals(history, model)["future"]:
                self.assertGreaterEqual(row["yhat_lower"], 0)
                self.assertLessEqual(row["yhat_lower"], row["yhat"])
                self.assertGreaterEqual(row["yhat_upper"], row["yhat"])
                self.assertTrue(math.isfinite(row["yhat_upper"]))

    def test_insufficient_history_does_not_invent_bands(self):
        result = prediction_intervals([1.0] * 60, "ma8")
        for row in result["future"]:
            self.assertIsNone(row["yhat_lower"])
            self.assertIsNone(row["yhat_upper"])
            self.assertEqual(row["yhat"], 1)
        self.assertFalse(result["metadata"]["calibration"][0]["available"])

    def test_zero_error_history_is_exposed_without_arbitrary_width(self):
        result = prediction_intervals([0.0] * 156, "naive")
        self.assertEqual(result["future"][0]["yhat_upper"], 0)
        self.assertTrue(result["metadata"]["calibration"][0]["zero_error_history"])
        self.assertFalse(result["metadata"]["coverage_guarantee"])

    def test_sample_cap_and_finite_quantile_rank(self):
        result = prediction_intervals(list(range(260)), "naive", max_origins=40)
        for row in result["metadata"]["calibration"]:
            self.assertEqual(row["n"], 40)
            self.assertEqual(row["quantile_rank"], 39)
        # An unattainable empirical rank is unavailable, not clipped to max(error).
        result = prediction_intervals(list(range(156)), "naive", level=.999)
        self.assertIsNone(result["future"][0]["yhat_upper"])

    def test_higher_nominal_level_does_not_narrow_same_calibration(self):
        history = [float((i * i) % 37) for i in range(156)]
        low = prediction_intervals(history, "ma8", level=.8)
        high = prediction_intervals(history, "ma8", level=.95)
        for a, b in zip(low["future"], high["future"]):
            self.assertLessEqual(b["yhat_lower"], a["yhat_lower"])
            self.assertGreaterEqual(b["yhat_upper"], a["yhat_upper"])

    def test_invalid_inputs_fail_explicitly(self):
        for bad in ([-1], [float("inf")], [float("nan")]):
            with self.assertRaises(ValueError):
                prediction_intervals(bad, "naive")
        for kwargs in ({"horizon": 0}, {"level": 1}, {"forecast_origin": -1},
                       {"max_origins": 0}, {"min_calibration": True}):
            with self.assertRaises(ValueError):
                prediction_intervals([1] * 156, "naive", **kwargs)
        with self.assertRaises(ValueError):
            prediction_intervals([1] * 156, "unknown")


if __name__ == "__main__":
    unittest.main()

