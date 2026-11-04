"""Split-aware account UI candidate, no active account or runtime migration."""
from copy import deepcopy
from fractions import Fraction
import importlib.util
from pathlib import Path
import unittest

from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_split_bundle_v1 import prepare_split_bundle
import test_strategy_split_bundle_v1 as fixtures

spec=importlib.util.spec_from_file_location('split_account_projection',
    Path(__file__).resolve().parents[1]/'docs/candidates/strategy_account_split_cost_projection.py')
candidate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class SplitAccountCostProjectionTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.SplitBundleTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        prepare_split_bundle(**self.base.arguments)
        self.store=SplitStrategyAccountStore(self.base.directory/'account.sqlite3',clock=self.base.clock)
        self.service=candidate.StrategyAccountService(database_path=self.base.source.path,
            account_id='synthetic-account',resolver=lambda ticker:None)

    def project(self):
        before=self.store.read()
        result=self.service.project(before)['account']
        self.assertEqual(self.store.read(),before)
        return result

    def sell(self, event_id, quantity):
        state=self.store.read()
        self.store.append(dict(event_id=event_id,kind='DIRECT_FILL',security_id='A',side='SELL',
            quantity=quantity,price='13',fees='0',executed_at=self.base.clock().isoformat()),
            expected_revision=state['revision'])

    def test_split_changes_per_share_cost_not_total_cost_or_historical_fill(self):
        result=self.project()
        cost=result['holding_costs'][0]
        self.assertEqual((cost['quantity'],cost['total_cost'],cost['average_cost']),(112,'1400','25/2'))
        self.assertEqual(result['fills'][0]['quantity'],14)
        self.assertEqual(result['fills'][0]['price'],'100')
        self.assertEqual(len(result['fills']),1)
        self.assertFalse(result['cash_confirmation_valid'])

    def test_sales_crossing_pre_split_quantity_keep_remaining_cost_correct(self):
        self.sell('sell-first-14',14)
        self.sell('sell-next-14',14)
        result=self.project();cost=result['holding_costs'][0]
        self.assertEqual(cost['quantity'],84)
        self.assertEqual(Fraction(cost['total_cost']),1050)
        self.assertEqual(Fraction(cost['average_cost']),Fraction(25,2))
        self.assertEqual(len(result['fills']),3)
        self.sell('sell-remainder',84)
        self.assertEqual(self.project()['holding_costs'],[])

    def test_mismatched_share_state_is_rejected(self):
        state=deepcopy(self.store.read());state['shares']['A']+=1
        with self.assertRaisesRegex(ValueError,'PROJECTED_COST_QUANTITIES_MISMATCH'):
            self.service.project(state)
