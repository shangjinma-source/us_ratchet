"""A saved audit projection must preserve the account role and authority."""
from copy import deepcopy
import unittest

from backtest import ndx_multidecision_path_comparison_research as comparison
from test_ndx_multidecision_path_comparison_research import fixture


class AuditRoleScope(unittest.TestCase):
    def test_candidate_cannot_borrow_other_inspection_role_or_authority(self):
        arguments = fixture()
        comparison.compare_multidecision_paths(**arguments)
        for field, value in (
            ('schema', 'MULTIDECISION_ORIGINAL_EIGHT_LEDGER_INSPECTION_V1'),
            ('point_in_time_verified', True),
            ('promotion_allowed', True),
        ):
            with self.subTest(field=field):
                changed = deepcopy(arguments)
                changed['candidate_slots'][8]['audit_evidence']['inspection'][field] = value
                with self.assertRaises(ValueError):
                    comparison.compare_multidecision_paths(**changed)


if __name__ == '__main__':
    unittest.main()
