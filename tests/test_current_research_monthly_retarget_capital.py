import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
import test_current_research_intraday_continuation as fixtures
from test_current_research_intraday_execution import NOW
from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital

class CapitalTests(unittest.TestCase):
    def fixture(self,root):
        _,state,old=fixtures.ContinuationTests().setup(root)
        proposal=state['acceptance']['proposal'];causal=proposal['causal_inputs']
        identity=dict(account_id=state['account_id'],initial_acceptance_id=state['acceptance_id'],initial_proposal_id=proposal['proposal_id'],initial_research_id=proposal['research_id'],initial_cash=causal['available_cash'])
        args=dict(expected_revision=state['revision'],initial_capital_identity=identity,
            valuation_quotes=[dict(security_id='sndk',ticker='SNDK',currency='USD',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',price_kind='REGULAR_MARKET_LAST',price='1500',quoted_at=NOW.isoformat(),captured_at=NOW.isoformat(),source_references=['quote'])],
            source_hashes={'quote':'a'*64,'units':'b'*64,'calendar':'c'*64},market_session=old['market_session'],now=NOW,
            unit_continuity={'sndk':dict(security_id='sndk',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',status='NO_UNPROCESSED_ACTIONS',initial_event_sha256=causal['event_sha256'],quote_source_references=['quote'],covered_from=NOW.isoformat(),covered_through=NOW.isoformat(),reviewed_asof=NOW.isoformat(),source_references=['units'])})
        return state,args
    def test_real_assets_equity_cash_separation(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root);before=deepcopy(state)
            result=build_monthly_retarget_capital(state,**args)
            self.assertEqual(result['status'],'READY',result);capital=result['capital']
            self.assertEqual(capital['cash'],'17200');self.assertEqual(capital['stock_value'],'3000')
            self.assertEqual(capital['investable_equity'],'20200');self.assertEqual(capital['buy_cash_limit'],'17200')
            self.assertEqual(capital['unfilled_sell_proceeds_available'],'0');self.assertEqual(state,before)
            self.assertFalse(result['source_authenticated']);self.assertFalse(result['selection_performed'])
    def test_bad_revision_genesis_unit_domain_and_old_close(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            mutations=[lambda a:a.update(expected_revision='old'),lambda a:a['initial_capital_identity'].update(initial_cash='30000'),
                lambda a:a.update(valuation_quotes=[]),lambda a:a['valuation_quotes'][0].update(price_kind='RAW_PROVIDER_CLOSE'),
                lambda a:a['unit_continuity']['sndk'].update(initial_event_sha256='0'*64),lambda a:a['valuation_quotes'][0].update(ticker='OTHER'),
                lambda a:a.update(source_hashes={'calendar':'c'*64})]
            for mutate in mutations:
                value=deepcopy(args);mutate(value)
                self.assertEqual(build_monthly_retarget_capital(state,**value)['status'],'BLOCKED')
    def test_stale_future_tamper_and_hash_change(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            for delta in (-121,-1,1):
                value=deepcopy(args);value['valuation_quotes'][0]['quoted_at']=(NOW+timedelta(seconds=delta)).isoformat()
                self.assertEqual(build_monthly_retarget_capital(state,**value)['status'],'BLOCKED')
            bad=deepcopy(state);bad['shares']['sndk']=20
            self.assertEqual(build_monthly_retarget_capital(bad,**args)['status'],'BLOCKED')
            first=build_monthly_retarget_capital(state,**args);args['valuation_quotes'][0]['price']='1501'
            second=build_monthly_retarget_capital(state,**args)
            self.assertNotEqual(first['capital_binding_id'],second['capital_binding_id'])
            self.assertEqual(second['capital']['buy_cash_limit'],'17200')

if __name__=='__main__':unittest.main()
