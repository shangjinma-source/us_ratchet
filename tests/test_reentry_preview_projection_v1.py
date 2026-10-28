"""Real ledger and cash allocator; no production account or network."""
import os
import importlib.util
from pathlib import Path
import sys
import unittest
from copy import deepcopy
from data.strategy_account_preview import preview_scoped_account

ROOT = Path.cwd()
STAGE = Path(os.environ.get('REENTRY_CANDIDATE_ROOT', '.'))
for name, path in [
    ('core.reentry_buy_scope_v1', STAGE / 'core/reentry_buy_scope_v1.py'),
    ('projection_candidate', STAGE / 'data/reentry_preview_projection_v1.py'),
    ('original_fixture', ROOT / 'tests/test_news_risk_plan_v1.py')]:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
project = sys.modules['projection_candidate'].project_reference_preview
fixture = sys.modules['original_fixture'].fixture
NOW = sys.modules['original_fixture'].NOW
digest = sys.modules['core.reentry_buy_scope_v1'].digest


class ProjectionTests(unittest.TestCase):
    def case(self):
        account, original, _ = fixture(held={'A': 0, 'B': 0, 'C': 3},
                                      targets={'A': 4, 'B': 4, 'C': 1}, cash='200')
        state = dict(schema='REENTRY_REFERENCE_V1', account_id=account['account_id'],
                     version=1, locks={'A': {'security_id': 'A'}})
        binding = dict(account_id=account['account_id'], account_revision=account['revision'],
                       target_id=original['target_id'], proposal_id=original['proposal_id'])
        proof = dict(origin_security_id='A', reference_version=1,
            reference_state_sha256=digest(state), decision_session='2026-10-27',
            buy_security_ids=['A', 'B'], original_binding=binding,
            status='INTERSECTS_BUY_SCOPE', current_security_ids=['A'],
            identity_evidence_sha256='a'*64, price_status='LOCKED',
            price_evidence_sha256='b'*64, price_completed_through='2026-10-27')
        return dict(account=account, original_preview=original, reference_state=state,
                    decision_session='2026-10-27', scope_proofs=[proof], now=NOW)

    def test_cash_reallocated_before_fill_and_sell_unchanged(self):
        args = self.case(); before = deepcopy(args)
        result = project(**args)
        self.assertEqual([(x['security_id'],x['quantity']) for x in args['original_preview']['new_orders'] if x['side']=='BUY'], [('A',1),('B',1)])
        self.assertEqual([(x['security_id'],x['quantity']) for x in result['candidate_orders'] if x['side']=='BUY'], [('B',2)])
        self.assertEqual([x for x in result['candidate_orders'] if x['side']=='SELL'],
                         [x for x in args['original_preview']['new_orders'] if x['side']=='SELL'])
        self.assertEqual(result['difference']['new_buy_cash_required'], '200')
        self.assertFalse(result['sell_proceeds_assumed']); self.assertFalse(result['executable'])
        self.assertEqual(args, before)

    def test_real_composition_order_provenance_survives_projection(self):
        args = self.case(); original = args['original_preview']
        for orders in (original['new_orders'], original['difference']['new_orders']):
            for order in orders:
                order.update(source_target_id=original['target_id'], proposal_id=original['proposal_id'])
        result = project(**args)
        self.assertEqual([o for o in result['candidate_orders'] if o['side']=='SELL'],
                         [o for o in original['new_orders'] if o['side']=='SELL'])
        for order in result['candidate_orders']:
            self.assertEqual(order['source_target_id'], original['target_id'])
            self.assertEqual(order['proposal_id'], original['proposal_id'])
        original['new_orders'][0]['proposal_id'] = 'different-proposal'
        with self.assertRaisesRegex(ValueError, 'REFERENCE_ORDER_PROVENANCE_CHANGED'):
            project(**args)

    def test_unknown_identity_waits_buys_but_keeps_sell(self):
        args = self.case(); args['scope_proofs'] = []
        result = project(**args)
        self.assertEqual(result['status'],'WAIT_BUY_REFERENCE')
        self.assertEqual([x['side'] for x in result['candidate_orders']],['SELL'])

    def test_expired_or_changed_original_is_never_upgraded(self):
        for change in ('time','orders','account','state','status'):
            args = self.case()
            if change=='time': args['now']='2026-10-28T14:01:00+00:00'
            elif change=='orders': args['original_preview']['new_orders'][0]['quantity']+=1
            elif change=='account': args['account']['shares']['C']+=1
            elif change=='state': args['reference_state']['version']+=1
            else: args['original_preview']['status']='WAIT'
            with self.subTest(change=change), self.assertRaises(ValueError): project(**args)

    def test_disjoint_identity_allows_original_buys_without_price_release(self):
        args = self.case(); p=args['scope_proofs'][0]
        p.update(status='DISJOINT_IDENTITY_CERTIFIED',current_security_ids=['D'])
        p.pop('price_status'); p.pop('price_evidence_sha256'); p.pop('price_completed_through')
        result=project(**args)
        self.assertEqual(result['candidate_orders'],args['original_preview']['new_orders'])
        self.assertEqual(args['reference_state']['version'],1)

    def test_validity_cannot_outlive_old_mark(self):
        args=self.case(); original=args['original_preview']; proof=original['difference']['binding']
        marks=deepcopy(proof['marks']); limits=deepcopy(proof['limits'])
        for mark in marks.values(): mark['observed_at']='2026-10-28T13:58:10+00:00'
        for limit in limits.values(): limit['observed_at']='2026-10-28T13:58:10+00:00'
        original['reference_quotes']=limits
        original['difference']=preview_scoped_account(state=args['account'],legacy_shares={},
            marks=marks,limits=limits,target_quantities=proof['target_quantities'],
            now=NOW,maximum_mark_age_seconds=120,fee_bps='0')
        original['new_orders']=original['difference']['new_orders']
        result=project(**args)
        self.assertEqual(result['valid_until'],'2026-10-28T14:00:10+00:00')
        args['now']='2026-10-28T14:00:10+00:00'
        with self.assertRaisesRegex(ValueError,'REFERENCE_MARK_EXPIRED'): project(**args)


if __name__ == '__main__': unittest.main()
