from copy import deepcopy
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import moment
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_split_account_preview_v1 import preview_split_account
from test_split_bundle_decision_handoff import SplitBundleDecisionHandoffTests


class SplitPreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = SplitBundleDecisionHandoffTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.state, _ = f.store.append(dict(event_id='cash-after-split', kind='CASH_CONFIRM',
            amount='1000', cash_basis='TOTAL_UNINVESTED'), expected_revision=f.after['revision'])
        prices = f.arguments('12.5')
        units = f.transition['payload']['risk_projection']['risk_state']['unit_ids']
        for sid in prices['marks']:
            prices['marks'][sid]['unit_id'] = units[sid]
            prices['limits'][sid]['unit_id'] = units[sid]
        self.arguments = {key: value for key, value in prices.items() if key not in ('legacy_shares','pending_orders')}
        self.arguments.update(state=self.state, action_id=f.base.arguments['action']['action_id'],
            target=f.base.arguments['target'], expected_proposal_id=f.base.arguments['expected_proposal_id'],
            risk_before=f.base.arguments['risk_before'])
        securities={sid:dict(ticker=sid) for sid in prices['marks']}
        at=int(moment(f.base.arguments['action']['effective_at']).timestamp())
        def daily(ticker,start,end):
            events={'splits':{str(at):dict(date=at,numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='A' else {}
            return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))))
        rss=b'<rss><channel><title>Nasdaq</title></channel></rss>'
        source=PaperActionEvidenceSources(fetch=daily,rss_fetch=lambda:dict(status=200,body=rss),clock=f.base.clock)
        package=source.capture(dict(account_id=self.state['account_id'],state_revision=self.state['revision'],
            window_start='2026-10-19T20:00:00Z',observed_floor='2026-10-19T20:00:00Z',
            securities=securities,current_target_quantities={}))
        self.arguments.update(securities=securities,action_package=package)

    def test_real_split_ledger_reaches_cash_limited_difference_without_mutation(self):
        before = self.fixture.store.read()
        result = preview_split_account(**self.arguments)
        difference = result['candidate_difference']
        self.assertEqual(difference['strategy_equity'], '2400')
        self.assertEqual(difference['binding']['strategy_shares']['A'],112)
        self.assertFalse(result['executable'])
        self.assertEqual(result['action_review']['matches'][0]['action_id'],self.arguments['action_id'])
        self.assertEqual(self.fixture.store.read(),before)

    def test_old_unit_and_pre_action_quote_rejected(self):
        args=deepcopy(self.arguments);args['marks']['A']['unit_id']='old'
        with self.assertRaisesRegex(ValueError,'UNIT_MISMATCH'):preview_split_account(**args)
        args=deepcopy(self.arguments);args['marks']['A']['observed_at']='2026-10-20T15:00:00Z'
        with self.assertRaisesRegex(ValueError,'PRE_ACTION_QUOTE'):preview_split_account(**args)

    def test_cash_and_replay_are_not_bypassed(self):
        args=deepcopy(self.arguments);args['state']=self.fixture.after
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION'):preview_split_account(**args)
        args=deepcopy(self.arguments);args['state']['shares']['A']=14
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):preview_split_account(**args)

    def test_stale_proposal_cannot_supply_split_target(self):
        args=deepcopy(self.arguments);args['expected_proposal_id']='stale'
        with self.assertRaisesRegex(ValueError,'STALE_PROPOSAL'):preview_split_account(**args)
