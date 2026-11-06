import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from data.roa_execution_lifecycle import RoaExecutionLifecycle

class EntryPeakIndependentTests(unittest.TestCase):
    def test_actual_new_holding_keeps_open_peak_and_triggers_close_stop(self):
        with TemporaryDirectory() as directory:
            lifecycle=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            signal={'signal_date':'2026-11-05','decision_date':'2026-10-30','risk_on':True,'weights':{'X':'1/10'},'signal_id':'b'*64}
            state=lifecycle.plan(signal=signal,session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:35:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
            lifecycle.materialize_open(event_id=state['events'][0]['event_id'],account={'account_id':'A','cash_confirmation_valid':True,'shares':{},'total_uninvested_cash':'10000','revision':'r'},opening_prices={'X':'100'},now='2026-11-06T14:30:00Z')
            state=lifecycle.close_observation(session='2026-11-06',shares={'X':9},closing_prices={'X':'75'})
            self.assertEqual(state['peaks']['X'],'100')
            self.assertEqual(state['pending'],['X'])

    def test_rebound_does_not_cancel_unfilled_scheduled_exit(self):
        with TemporaryDirectory() as directory:
            lifecycle=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            signal={'signal_date':'2026-11-05','decision_date':'2026-10-30','risk_on':True,'weights':{'X':'1/10'},'signal_id':'b'*64}
            state=lifecycle.plan(signal=signal,session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:35:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
            lifecycle.materialize_open(event_id=state['events'][0]['event_id'],account={'account_id':'A','cash_confirmation_valid':True,'shares':{'X':9},'total_uninvested_cash':'9100','revision':'r'},opening_prices={'X':'100'},now='2026-11-06T14:30:00Z')
            lifecycle.close_observation(session='2026-11-06',shares={'X':9},closing_prices={'X':'75'})
            signal=dict(signal,signal_date='2026-11-06',signal_id='c'*64)
            lifecycle.plan(signal=signal,session='2026-11-09',open_at='2026-11-09T14:30:00Z',open_until='2026-11-09T14:35:00Z',close_at='2026-11-09T20:55:00Z',close_until='2026-11-09T21:00:00Z')
            state=lifecycle.close_observation(session='2026-11-09',shares={'X':4},closing_prices={'X':'95'})
            self.assertIn('X',state['pending'])
            self.assertIn('X',state['missed_exits'])
            signal=dict(signal,signal_date='2026-11-09',signal_id='d'*64)
            state=lifecycle.plan(signal=signal,session='2026-11-10',open_at='2026-11-10T14:30:00Z',open_until='2026-11-10T14:35:00Z',close_at='2026-11-10T20:55:00Z',close_until='2026-11-10T21:00:00Z')
            self.assertFalse(any(e['phase']=='CLOSE' and e['session']=='2026-11-10' for e in state['events']))

    def test_completed_exit_does_not_revive_after_new_month_reentry(self):
        with TemporaryDirectory() as directory:
            lifecycle=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            def plan(day, previous, decision):
                return lifecycle.plan(signal={'signal_date':previous,'decision_date':decision,'risk_on':True,'weights':{'X':'1/10'},'signal_id':'b'*64},session=day,open_at=day+'T14:30:00Z',open_until=day+'T14:35:00Z',close_at=day+'T20:55:00Z',close_until=day+'T21:00:00Z')
            state=plan('2026-11-06','2026-11-05','2026-10-30')
            lifecycle.materialize_open(event_id=state['events'][0]['event_id'],account={'account_id':'A','cash_confirmation_valid':True,'shares':{'X':9},'total_uninvested_cash':'9100','revision':'r'},opening_prices={'X':'100'},now='2026-11-06T14:30:00Z')
            lifecycle.close_observation(session='2026-11-06',shares={'X':9},closing_prices={'X':'75'})
            plan('2026-11-09','2026-11-06','2026-10-30')
            exited=lifecycle.close_observation(session='2026-11-09',shares={},closing_prices={})
            self.assertEqual(exited['pending'],[])
            state=plan('2026-12-01','2026-11-30','2026-11-30')
            event=[e for e in state['events'] if e['phase']=='OPEN' and e['session']=='2026-12-01'][0]
            lifecycle.materialize_open(event_id=event['event_id'],account={'account_id':'A','cash_confirmation_valid':True,'shares':{},'total_uninvested_cash':'10000','revision':'s'},opening_prices={'X':'100'},now='2026-12-01T14:30:00Z')
            state=lifecycle.close_observation(session='2026-12-01',shares={'X':9},closing_prices={'X':'105'})
            self.assertEqual(state['missed_exits'],[])
            self.assertEqual(state['pending'],[])

if __name__=='__main__':unittest.main()
