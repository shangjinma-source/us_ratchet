"""Late-result rejection using the actual ledger-backed projection fixture."""
from copy import deepcopy
import unittest

import test_reentry_preview_projection_v1 as fixture
from data.reentry_publication_guard_v1 import seal_projection, check_publication


class PublicationTests(unittest.TestCase):
    def case(self):
        args = fixture.ProjectionTests().case()
        projection = fixture.project(**args)
        seal = seal_projection(projection=projection, configuration_sha256='c' * 64)
        return dict(projection=projection, seal=seal,
                    current_binding=deepcopy(projection['binding']['original_binding']),
                    current_reference_state=args['reference_state'],
                    current_configuration_sha256='c' * 64, now=fixture.NOW)

    def test_current_result_is_checked_but_not_executable(self):
        args = self.case(); before = deepcopy(args)
        result = check_publication(**args)
        self.assertFalse(result['executable'])
        self.assertEqual(args, before)

    def test_same_request_ids_do_not_hide_changed_lock(self):
        args = self.case()
        args['current_reference_state']['version'] += 1
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_REFERENCE_CHANGED'):
            check_publication(**args)
        args = self.case()
        args['current_reference_state']['locks'].clear()
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_REFERENCE_CHANGED'):
            check_publication(**args)

    def test_cash_target_configuration_or_order_changes_rejected(self):
        for change in ('account_revision', 'target_id', 'proposal_id', 'config', 'order'):
            args = self.case()
            if change == 'config': args['current_configuration_sha256'] = 'd' * 64
            elif change == 'order': args['projection']['candidate_orders'][0]['quantity'] += 1
            else: args['current_binding'][change] += '-changed'
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_publication(**args)

    def test_expiry_boundary_and_future_result_rejected(self):
        for timestamp in ('2026-10-28T13:59:59+00:00', self.case()['seal']['valid_until']):
            args = self.case(); args['now'] = timestamp
            with self.assertRaisesRegex(ValueError, 'PUBLICATION_EXPIRED_OR_FUTURE'):
                check_publication(**args)


if __name__ == '__main__': unittest.main()
