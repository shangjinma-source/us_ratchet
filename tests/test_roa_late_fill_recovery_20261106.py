import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from core.strategy_account_ledger import create_account,apply_event
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_close_recovery import holdings_at,recover_closes

class LateFillRecoveryTests(unittest.TestCase):
    def account(self):
        state=create_account('A')
        # Received order may differ from actual execution time; only actual fills count.
        for event in [dict(event_id='cash',kind='CASH_CONFIRM',amount='10000',cash_basis='TOTAL_UNINVESTED'),dict(event_id='buy',kind='DIRECT_FILL',security_id='X',side='BUY',quantity=9,price='100',fees='0',executed_at='2026-11-06T14:31:00Z'),dict(event_id='sell',kind='DIRECT_FILL',security_id='X',side='SELL',quantity=5,price='95',fees='0',executed_at='2026-11-09T15:00:00Z')]:
            state,_=apply_event(state,event,expected_revision=state['revision'])
        return state
    def fixture(self):
        with TemporaryDirectory() as directory:
            life=RoaExecutionLifecycle(path=Path(directory)/'x',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            signal=dict(signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'X':'1/10'},signal_id='b'*64)
            state=life.plan(signal=signal,session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:35:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
            life.materialize_open(event_id=state['events'][0]['event_id'],account={'account_id':'A','cash_confirmation_valid':True,'shares':{},'total_uninvested_cash':'10000','revision':'r'},opening_prices={'X':'100'},now='2026-11-06T14:30:00Z')
            checkpoint=life.read()
            # The buy was not entered yet, so original close mistakenly saw zero shares.
            life.close_observation(session='2026-11-06',shares={},closing_prices={})
            return checkpoint,life.read()
    def kwargs(self):
        checkpoint,current=self.fixture()
        return dict(checkpoint=checkpoint,current_lifecycle=current,account=self.account(),sessions=[{'session':'2026-11-06','prices':{'X':'75'}}],calendar=lambda d:{'close_at':d+'T21:00:00Z','previous_session':'2026-11-05'},now='2026-11-09T16:00:00Z')
    def test_late_buy_replays_real_close_not_current_shares(self):
        args=self.kwargs();before=deepcopy(args['account']);result=recover_closes(**args)
        self.assertEqual(result['observations'][0]['shares'],{'X':9})
        self.assertEqual(result['recovered_state']['peaks'],{'X':'100'})
        self.assertEqual(result['recovered_state']['pending'],['X'])
        self.assertEqual(args['account'],before)
        self.assertEqual(args['account']['shares'],{'X':4})
    def test_advice_never_fabricates_execution(self):
        args=self.kwargs();args['account']=create_account('A')
        result=recover_closes(**args)
        self.assertEqual(result['observations'][0]['shares'],{})
        self.assertEqual(result['recovered_state']['pending'],[])
    def test_future_close_and_missing_price_refused(self):
        args=self.kwargs();args['now']='2026-11-06T20:00:00Z';args['account']=create_account('A')
        with self.assertRaisesRegex(ValueError,'FUTURE_CLOSE'):recover_closes(**args)
        args=self.kwargs();args['sessions'][0]['prices']={}
        with self.assertRaisesRegex(ValueError,'PRICES_MISSING'):recover_closes(**args)
    def test_later_materialized_open_refused(self):
        args=self.kwargs();e=deepcopy(args['current_lifecycle']['events'][0]);e['event_id']='new';e['session']='2026-11-09';args['current_lifecycle']['events'].append(e)
        with self.assertRaisesRegex(ValueError,'MATERIALIZED_OPEN'):recover_closes(**args)
    def test_tampered_account_refused(self):
        account=self.account();account['shares']['X']=5
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):holdings_at(account,'2026-11-06T21:00:00Z')

if __name__=='__main__':unittest.main()
