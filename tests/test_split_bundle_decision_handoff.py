"""Synthetic economic invariance plus explicit current production bridge gap."""
from copy import deepcopy
from fractions import Fraction
import unittest

from core.strategy_account_difference import build_strategy_difference
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.strategy_account_preview import preview_scoped_account
from data.strategy_split_bundle_v1 import prepare_split_bundle, verify_split_bundle
from data.strategy_split_native_projection_v1 import project_native_split
from data.monthly_peak_exit_store import MonthlyPeakExitStore
import test_strategy_split_bundle_v1 as fixtures


class SplitBundleDecisionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.SplitBundleTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.before=self.base.source.read()
        prepare_split_bundle(**self.base.arguments)
        self.manifest=verify_split_bundle(self.base.directory)
        self.store=SplitStrategyAccountStore(self.base.directory/'account.sqlite3',clock=self.base.clock)
        self.after=self.store.read()
        self.transition=project_native_split(account_after=self.after,
            action_id=self.base.arguments['action']['action_id'],
            risk_before=self.base.arguments['risk_before'],target=self.base.arguments['target'],
            expected_proposal_id=self.base.arguments['expected_proposal_id'])

    def arguments(self, price):
        now=self.base.clock().isoformat()
        marks={sid:dict(security_id=sid,currency='USD',price_basis='SYNTHETIC',
            price=value,observed_at=now) for sid,value in [('A',price),('B','100')]}
        limits={sid:dict(security_id=sid,price_basis='SYNTHETIC',buy=value['price'],
            sell=value['price'],observed_at=now) for sid,value in marks.items()}
        return dict(legacy_shares={},pending_orders=[],marks=marks,limits=limits,
            now=now,maximum_mark_age_seconds=120,fee_bps='0')

    def difference(self,state,targets,price):
        # Arithmetic check only: caller-supplied synthetic marks, not source admission.
        return build_strategy_difference(account_id=state['account_id'],account_revision=state['revision'],
            holdings_revision=state['holdings_revision'],
            cash_confirmed_for_holdings_revision=state['holdings_revision'],
            cash_balance='1000',cash_basis='TOTAL_UNINVESTED',strategy_shares=state['shares'],
            target_quantities=targets,**self.arguments(price))

    def test_same_equity_and_target_value_with_finer_integer_share_rounding(self):
        original=build_frontier_proposal(target=self.base.arguments['target'])['payload']['proposed_target_quantities']
        adjusted=self.transition['payload']['risk_projection']['target_quantities']
        before=self.difference(self.before,original,'100')
        after=self.difference(self.after,adjusted,'12.5')
        self.assertEqual(before['strategy_equity'],after['strategy_equity'])
        self.assertEqual(original['A']*100,Fraction(adjusted['A'])*Fraction(25,2))
        old={o['security_id']:o for o in before['new_orders']}
        new={o['security_id']:o for o in after['new_orders']}
        self.assertEqual(set(old),set(new))
        self.assertIn('A',old)
        for sid in old:
            ratio=8 if sid=='A' else 1
            self.assertEqual(new[sid]['side'],old[sid]['side'])
            self.assertGreaterEqual(new[sid]['quantity'],old[sid]['quantity']*ratio)
            self.assertLess(new[sid]['quantity'],(old[sid]['quantity']+1)*ratio)
        self.assertLessEqual(-sum(Fraction(o['estimated_cash_change']) for o in new.values()),1000)
        self.assertEqual(self.store.read(),self.after)

    def test_risk_has_no_artificial_exit_and_transition_remains_nonexecutable(self):
        risk=MonthlyPeakExitStore(self.base.directory/'risk.sqlite3').read(self.after['account_id'])
        self.assertEqual(risk['exited'],[])
        self.assertEqual(Fraction(risk['peaks']['A']),Fraction(25,2))
        self.assertEqual(risk['unit_ids']['A'],'new')
        self.assertFalse(self.transition['payload']['executable'])
        self.assertFalse(self.manifest['production_activated'])

    def test_current_production_preview_cannot_yet_consume_split_ledger(self):
        state=deepcopy(self.after)
        arguments=self.arguments('12.5');arguments.pop('pending_orders')
        with self.assertRaisesRegex(ValueError,'EVENT_FIELDS'):
            preview_scoped_account(state=state,
                target_quantities=self.transition['payload']['risk_projection']['target_quantities'],**arguments)
