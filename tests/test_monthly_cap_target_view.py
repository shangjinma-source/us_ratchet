from copy import deepcopy
from hashlib import sha256
import unittest
from core.strategy_account_ledger import canonical
from data.monthly_cap_target_view import capped_target_view


class CapTargetViewTests(unittest.TestCase):
    def test_original_selection_preserved_and_cap_applied_once(self):
        binding = dict(strategy_equity='20000', search_arguments=dict(
            entered_cash='20000', prices={'A': '100', 'B': '100'}))
        selected = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest(),
                        target_quantities={'A': 180, 'B': 20})
        decision = dict(payload=selected, decision_id=sha256(canonical(selected)).hexdigest())
        payload = dict(decision=decision, target_quantities=dict(selected['target_quantities']))
        target = dict(payload=payload, target_id=sha256(canonical(payload)).hexdigest())
        before = deepcopy(target)
        result = capped_target_view(target)
        self.assertEqual(result['target_quantities'], {'A': 100, 'B': 20})
        self.assertEqual(result['unallocated_cash'], '8000')
        self.assertEqual(target, before)
        self.assertEqual(capped_target_view(target), result)
        target['payload']['target_quantities']['A'] = 100
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_TARGET_CHANGED'):
            capped_target_view(target)


if __name__ == '__main__':
    unittest.main()
