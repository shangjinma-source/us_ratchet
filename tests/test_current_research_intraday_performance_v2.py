import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
import test_current_research_intraday_continuation as fixtures
import test_current_research_intraday_continuation_ledger as chains
import test_current_research_intraday_performance as pure
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_continuation_ledger import apply_continuation_event,build_continuation_proposal
from data.current_research_intraday_performance import compute_intraday_paper_performance

class V2PerformanceTests(unittest.TestCase):
    def test_two_continuations_cumulative_fees_and_initial_start(self):
        with tempfile.TemporaryDirectory() as root:
            _,state,args=fixtures.ContinuationTests().setup(root)
            helper=chains.ChainTests();state,_=helper.accept(state,args)
            state=apply_continuation_event(state,helper.event(state,fees='1'),now=NOW)
            state=apply_continuation_event(state,helper.event(state,'CANCEL','cancel2'),now=NOW)
            args.update(expected_revision=state['revision'],now=NOW+timedelta(seconds=1))
            state,_=helper.accept(state,args,'second')
            before=deepcopy(state)
            with self.assertRaisesRegex(ValueError,'LEDGER_AFTER'):
                compute_intraday_paper_performance(state,now=NOW)
            quote=pure.PerformanceTests().arguments();quote['marks']['sndk']['observed_at']=NOW.isoformat()
            self.assertEqual(compute_intraday_paper_performance(state,**quote)['status'],'INCOMPLETE')
            e=helper.event(state,event_id='f2',quantity=2,fees='2',executed_at=(NOW+timedelta(seconds=1)).isoformat(),recorded_at=(NOW+timedelta(seconds=1)).isoformat())
            state=apply_continuation_event(state,e,now=NOW+timedelta(seconds=1))
            result=compute_intraday_paper_performance(state,**pure.PerformanceTests().arguments())
            self.assertEqual(result['cash'],'12997');self.assertEqual(result['shares'],{'sndk':5})
            self.assertEqual(result['recorded_fees'],'3');self.assertEqual(result['equity'],'20057')
            self.assertEqual(result['total_return'],'57/20000');self.assertEqual(result['accepted_at'],NOW.isoformat())
            self.assertIsNone(result['annualized_return']);self.assertEqual(before['shares'],{'sndk':3})
    def test_cash_only_v2_and_close_before_new_acceptance(self):
        from data.current_research_intraday_paper_ledger import _initial, apply_intraday_paper_event
        from data.current_research_intraday_performance import ledger_observation_floor
        with tempfile.TemporaryDirectory() as root:
            _,old,args=fixtures.ContinuationTests().setup(root)
            state=_initial(old['acceptance']);helper=chains.ChainTests()
            state=apply_intraday_paper_event(state,helper.event(state,'CANCEL','cancel-empty'),now=NOW)
            args.update(expected_revision=state['revision'],now=NOW+timedelta(seconds=2))
            state,_=helper.accept(state,args,'empty-continuation')
            result=compute_intraday_paper_performance(state,now=NOW+timedelta(seconds=3))
            self.assertEqual(result['equity'],'20000');self.assertEqual(result['shares'],{})
            self.assertIsNone(result['total_return']);self.assertEqual(result['accepted_at'],NOW.isoformat())
            self.assertEqual(ledger_observation_floor(state),NOW+timedelta(seconds=2))
            with self.assertRaisesRegex(ValueError,'LEDGER_AFTER'):
                compute_intraday_paper_performance(state,now=NOW+timedelta(seconds=1))

    def test_no_action_preview_does_not_advance_account_or_start(self):
        with tempfile.TemporaryDirectory() as root:
            _,state,args=fixtures.ContinuationTests().setup(root,fill=14)
            original=deepcopy(state);proposal=build_continuation_proposal(state,**args)
            self.assertEqual(proposal['action'],'NO_ACTION');self.assertEqual(state,original)
            result=compute_intraday_paper_performance(state,**pure.PerformanceTests().arguments())
            self.assertEqual(result['accepted_at'],NOW.isoformat());self.assertIsNone(result['annualized_return'])

if __name__=='__main__':unittest.main()
