import unittest
from copy import deepcopy
from scripts.research.run_news_ai_action_local_v1 import replay, prepare


class LocalReplayTests(unittest.TestCase):
    def fixture(self):
        days=['2021-11-04','2021-11-05','2021-11-08','2021-11-09']
        case=dict(initialization_requires_entitlement_reconstruction=False,
            monthly_reset_dates=['2021-11-10'],session_dates=days,corporate_action_inputs={},
            initial_baseline_ledger={'cash':'100','shares':{'A':1}},
            initial_risk_state_before_close=None,
            initial_close_baseline_audit={'monthly_ceiling':{'A':3},'target_decision_date':'2021-10-29'},
            security_id='A',metadata_availability='2021-11-04T22:00:00Z',
            close_prices={'A':{d:'10' for d in days}},
            ohlc={'A':{d:dict(open='10',high='11',low='9',close='10') for d in days}},dividend_events=[])
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        risk=MonthlyExitCoreResearchAdapter()
        risk.apply(day='2021-10-29',month='2021-10-29',target={'A':3},closes={'A':'10'})
        case['initial_risk_state_before_close']=risk.state
        return case,{d:d+'T21:00:00Z' for d in days}

    def test_after_close_only_next_decision_and_exit_never_rebuys(self):
        case,clock=self.fixture()
        result=replay(case,'EXIT',clock)
        trace=result['decision_trace']
        self.assertFalse(trace[0]['news_active'])
        self.assertTrue(trace[1]['news_active'])
        self.assertEqual(trace[1]['orders'][0]['active_date'],'2021-11-08')
        self.assertEqual(trace[1]['orders'][0]['side'],'SELL')
        self.assertEqual(result['book']['daily_ledger'][-1]['shares'].get('A',0),0)
        self.assertFalse(trace[2]['orders'])

    def test_buy_block_preserves_original_stop(self):
        case,clock=self.fixture()
        case['close_prices']['A']['2021-11-05']='7'
        result=replay(case,'BLOCK_NEW_BUYS',clock)
        trace=result['decision_trace'][1]
        self.assertEqual(trace['original_risk_target']['A'],0)
        self.assertEqual(trace['orders'][0]['side'],'SELL')

    def test_calendar_boundary_exclusive_and_entitlement_refused(self):
        case,_=self.fixture()
        case['monthly_reset_dates']=['2021-11-08']
        self.assertEqual(prepare(case),['2021-11-04','2021-11-05'])
        case['initial_baseline_ledger']['dividend_receivable']='1'
        with self.assertRaisesRegex(ValueError,'ENTITLEMENTS'):prepare(case)

    def test_action_refused_and_no_change_keeps_original_buy(self):
        case,clock=self.fixture()
        result=replay(case,'NO_CHANGE',clock)
        self.assertEqual(result['book']['daily_ledger'][-1]['shares']['A'],3)
        case['corporate_action_inputs']['actions']=[{'date':'2021-11-08','type':'split'}]
        with self.assertRaisesRegex(ValueError,'CORPORATE_ACTION'):replay(case,'EXIT',clock)

    def test_review_requires_all_cases_and_bound_source(self):
        import tempfile
        from hashlib import sha256
        from pathlib import Path
        from scripts.research.run_news_ai_action_local_v1 import validate_actions, CASES
        case,_=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'review.txt').write_text('independent review')
            digest=sha256((root/'review.txt').read_bytes()).hexdigest()
            cases={name:(case,'casehash') for name in CASES}
            review=dict(schema='NEWS_AI_LOCAL_ACTION_REVIEW_V1',source_hashes={'review.txt':digest},
                records=[dict(case=name,action='NO_CHANGE',case_sha256='casehash',
                    available_at=case['metadata_availability'],review_reference='review.txt') for name in CASES])
            self.assertEqual(len(validate_actions(root,review,cases)),5)
            review['records'][0]['available_at']='2021-11-04T20:00:00Z'
            with self.assertRaisesRegex(ValueError,'PROXY_BINDING'):validate_actions(root,review,cases)
            review['records'].pop()
            with self.assertRaisesRegex(ValueError,'FIVE'):validate_actions(root,review,cases)

if __name__=='__main__':unittest.main()
