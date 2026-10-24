"""Protect legacy records while adding new defaults and derived display data."""
import copy
import unittest
from unittest.mock import patch

from app.results import forecast_with_intervals
from app.runner import check_new_run, run_configured


class DispatchTests(unittest.TestCase):
    def test_new_runs_default_to_cost_and_service(self):
        config = check_new_run({'name': 'Improved'})
        self.assertEqual(config['policy_mode'], 'cost_service')
        self.assertEqual(config['validation_seeds'], [42, 43, 44, 45, 46])
        with patch('app.optimization.run_optimized_study', return_value='improved') as run:
            self.assertEqual(run_configured('dataset', config), 'improved')
            run.assert_called_once_with('dataset', config)

    def test_legacy_config_uses_original_engine(self):
        config = {'name': 'Original'}
        with patch('app.study.run_study', return_value='legacy') as run:
            self.assertEqual(run_configured('dataset', config), 'legacy')
            run.assert_called_once_with('dataset', config)

    def test_explicit_original_mode_preserves_legacy_config(self):
        from app.study import config_checked
        self.assertEqual(check_new_run({'policy_mode': 'research', 'name': 'Original'}),
                         config_checked({'name': 'Original'}))

    def test_bad_mode_is_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, 'Unknown inventory'):
            check_new_run({'policy_mode': 'made_up'})
        with self.assertRaisesRegex(ValueError, 'Unknown inventory'):
            run_configured('dataset', {'policy_mode': 'made_up'})

    def test_legacy_forecast_bands_are_additive_not_mutation(self):
        forecast = {'model': 'naive', 'history': [{'actual': i} for i in range(156)],
                    'future': [{'date': '2024-12-30', 'predicted': 155.0}]}
        saved = copy.deepcopy(forecast)
        display = forecast_with_intervals(forecast)
        self.assertEqual(forecast, saved)
        self.assertEqual(display['future'][0]['yhat'], 155)
        self.assertEqual(display['future'][0]['yhat_lower'], 154)
        self.assertEqual(display['future'][0]['yhat_upper'], 156)
        self.assertTrue(display['intervals']['display_only'])
        self.assertFalse(display['intervals']['coverage_guarantee'])

    def test_saved_interval_output_is_not_recalibrated(self):
        forecast = {'intervals': {'level': .95}, 'future': [{'yhat': 2}]}
        self.assertIs(forecast_with_intervals(forecast), forecast)


if __name__ == '__main__':
    unittest.main()
