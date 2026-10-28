import unittest
from copy import deepcopy
import test_reentry_preview_projection_v1 as fixture
from data.reentry_daily_response_v1 import format_reference_advice


class ResponseTests(unittest.TestCase):
    def case(self):
        args = fixture.ProjectionTests().case()
        return args

    def test_mixed_wait_does_not_hide_valid_sell_or_reallocated_buy(self):
        args = self.case(); projection = fixture.project(**args)
        before = deepcopy(args)
        result = format_reference_advice(original_preview=args['original_preview'],
                                        projection=projection, account=args['account'])
        rows = {r['security_id']: r for r in result['daily_gate']['rows']}
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(rows['A']['action'], 'WAIT')
        self.assertEqual(rows['A']['reason'], 'WAIT_REENTRY_RECOVERY')
        self.assertEqual(rows['B']['action'], 'BUY')
        self.assertEqual(rows['C']['action'], 'SELL')
        self.assertEqual(set(result['reference_quotes']), {'B', 'C'})
        self.assertNotIn('candidate_orders', result['reference_projection'])
        self.assertNotIn('difference', result['reference_projection'])
        self.assertEqual(set(result['reference_projection']),
                         {'schema', 'projection_sha256', 'reference_version',
                          'reference_state_sha256', 'buy_status'})
        self.assertEqual(args, before)

    def test_unknown_source_keeps_sell_but_no_buy_quote(self):
        args = self.case(); args['scope_proofs'] = []
        result = format_reference_advice(original_preview=args['original_preview'],
            projection=fixture.project(**args), account=args['account'])
        self.assertEqual([o['side'] for o in result['new_orders']], ['SELL'])
        self.assertEqual(set(result['reference_quotes']), {'C'})

    def test_changed_original_rejected(self):
        args = self.case(); projection = fixture.project(**args)
        args['original_preview']['proposal_id'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_CHANGED'):
            format_reference_advice(original_preview=args['original_preview'],
                                    projection=projection, account=args['account'])

    def test_all_buys_blocked_is_wait_without_executable_fields(self):
        args = self.case()
        account, original, _ = fixture.fixture(held={'A': 0}, targets={'A': 4}, cash='200')
        args.update(account=account, original_preview=original)
        proof = args['scope_proofs'][0]
        proof['buy_security_ids'] = ['A']
        proof['original_binding'] = dict(account_id=account['account_id'], account_revision=account['revision'],
                                        target_id=original['target_id'], proposal_id=original['proposal_id'])
        result = format_reference_advice(original_preview=original,
            projection=fixture.project(**args), account=account)
        self.assertEqual(result['status'], 'WAIT')
        self.assertEqual(result['new_orders'], [])
        self.assertEqual(result['reference_quotes'], {})
        self.assertEqual(result['difference']['new_orders'], [])


if __name__ == '__main__': unittest.main()
