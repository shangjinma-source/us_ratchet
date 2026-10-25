from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from data.strategy_prospective_paper_cap_target_v1 import CODE_PATHS, capped_paper_target
from test_strategy_prospective_paper_integration_v1 import fixture


class PaperCapTests(unittest.TestCase):
    def test_actual_registered_selection_caps_without_mutating_book_or_target(self):
        with TemporaryDirectory() as folder:
            daily = fixture(folder, extra_code_paths=CODE_PATHS)
            before = deepcopy(daily)
            result = capped_paper_target(selection_result=daily['selection_result'],
                                         selection_arguments=daily['selection_arguments'])
            self.assertEqual(result['original_quantities'], {'B': 20})
            self.assertEqual(result['target_quantities'], {'B': 10})
            self.assertEqual(result['unallocated_cash'], '10000')
            self.assertEqual(result['base_target_id'], daily['selection_result']['decision_id'])
            self.assertEqual(result['registration_sha256'], daily['book']['registration_sha256'])
            self.assertFalse(result['daily_exit_applied'])
            self.assertFalse(result['automatic_acceptance_allowed'])
            self.assertEqual(daily, before)
            # A changed quantity must not pass simply because it looks affordable.
            bad = deepcopy(daily['selection_result'])
            bad['payload']['target_quantities']['B'] = 19
            with self.assertRaises(ValueError):
                capped_paper_target(selection_result=bad,
                                    selection_arguments=daily['selection_arguments'])

    def test_old_registered_protocol_cannot_silently_acquire_new_policy(self):
        with TemporaryDirectory() as folder:
            daily = fixture(folder)
            with self.assertRaisesRegex(ValueError, 'PAPER_CAP_CODE_SCOPE'):
                capped_paper_target(selection_result=daily['selection_result'],
                                    selection_arguments=daily['selection_arguments'])


if __name__ == '__main__':
    unittest.main()
