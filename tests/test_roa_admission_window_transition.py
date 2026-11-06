import unittest,tempfile
from pathlib import Path
from datetime import datetime,timedelta
from api.strategy_account import StrategyAccountService
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService

class AdmissionWindowTests(unittest.TestCase):
    def test_old_unadmitted_open_does_not_revive_after_new_window(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[datetime.fromisoformat('2026-11-06T14:31:00+00:00')]
            account=StrategyAccountService(database_path=Path(directory)/'a.db',account_id='A',resolver=lambda _:None,clock=lambda:now[0]);account.initialize({'event_id':'init'})
            account.append(dict(expected_revision=account.store.read()['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')))
            life=RoaExecutionLifecycle(path=Path(directory)/'life.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            signal=dict(signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10'},signal_id='s',execution_not_before_session='2026-11-06',securities=[dict(security_id='A',ticker='A')])
            def session(day):return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00')
            calls=[]
            def quotes(state,sids,day,phase,clock):
                calls.append(clock)
                return dict(opening_session=day,opening_prices={'A':'10'},quote_valid_until=(clock+timedelta(seconds=120)).isoformat(),marks={'A':dict(security_id='A',currency='USD',price_basis='current',price='10',observed_at=clock.isoformat())},limits={'A':dict(security_id='A',price_basis='current',buy='10',sell='10',observed_at=clock.isoformat())})
            service=RoaStrategyService(account_service=account,lifecycle=life,signal_provider=lambda:signal,session_provider=session,quote_provider=quotes,clock=lambda:now[0])
            self.assertEqual(service.snapshot()['status'],'WAIT_EXECUTION_ADMISSION')
            old_id=life.read()['events'][0]['event_id']
            service.admission=dict(enabled=True,strategy_epoch='E',contract_sha256='a'*64,open_window_seconds=900,close_window_seconds=300)
            now[0]=datetime.fromisoformat('2026-11-06T14:44:59+00:00')
            ready=service.snapshot();self.assertTrue(ready['executable'])
            count=len(calls)
            now[0]=datetime.fromisoformat('2026-11-06T14:45:00+00:00')
            expired=service.snapshot()
            self.assertFalse(expired['executable'])
            self.assertEqual(expired['status'],'MISSED')
            self.assertEqual(len(calls),count)
            self.assertIsNone(next(e for e in life.read()['events'] if e['event_id']==old_id)['materialized_revision'])
            self.assertEqual(sum(bool(e['materialized_revision']) for e in life.read()['events']),1)

    def test_half_day_close_uses_authoritative_close(self):
        with tempfile.TemporaryDirectory() as directory:
            life=RoaExecutionLifecycle(path=Path(directory)/'life.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
            life.close_observation(session='2026-11-24',shares={'A':9},closing_prices={'A':'100'})
            life.close_observation(session='2026-11-25',shares={'A':9},closing_prices={'A':'75'})
            # Synthetic session sequence here only exercises supplied half-day phase times.
            signal=dict(signal_date='2026-11-25',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10'},signal_id='s')
            life.plan(signal=signal,session='2026-11-27',open_at='2026-11-27T14:30:00Z',open_until='2026-11-27T14:45:00Z',close_at='2026-11-27T17:55:00Z',close_until='2026-11-27T18:00:00.000001Z')
            self.assertEqual(life.event_view(now='2026-11-27T17:54:59Z')['status'],'PENDING_CLOSE')
            at=life.event_view(now='2026-11-27T17:55:00Z');self.assertEqual((at['status'],at['phase']),('WINDOW_OPEN','CLOSE'))
            self.assertEqual(life.event_view(now='2026-11-27T18:00:00.000001Z')['status'],'MISSED')

if __name__=='__main__':unittest.main()
