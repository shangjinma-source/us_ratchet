from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.saved_frontier_security_domain_v1 import plan_security_domain
from test_strategy_daily_security_domain_v1 import DynamicDomainTests


class FrontierDomainTests(unittest.TestCase):
    def test_explicit_quantities_and_risk_preserve_original_target(self):
        with TemporaryDirectory() as folder:
            case = DynamicDomainTests().case(folder)
            original = deepcopy(case.target)
            result = plan_security_domain(root=Path(folder), state=case.state,
                target=case.target, identity_reference=case.identity_reference,
                monthly_quantities={'A': 9}, extra_security_ids={'B'})
            self.assertEqual(case.target, original)
            self.assertEqual(result['target_id'], original['target_id'])
            self.assertEqual(set(result['securities']), {'A', 'B'})
            self.assertIn('MONTHLY_TARGET', result['securities']['A']['reasons'])
            self.assertNotIn('MONTHLY_TARGET', result['securities']['B']['reasons'])
            self.assertIn('MONTHLY_RISK_HISTORY', result['securities']['B']['reasons'])
            self.assertEqual(result['securities']['A']['status'], 'WAIT_UNIT_BASELINE')
            with self.assertRaisesRegex(ValueError, 'DOMAIN_IDENTITY_NOT_UNIQUE'):
                plan_security_domain(root=Path(folder), state=case.state, target=case.target,
                    identity_reference=case.identity_reference, monthly_quantities={'UNKNOWN': 1})
