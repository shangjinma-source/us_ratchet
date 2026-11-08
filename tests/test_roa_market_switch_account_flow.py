"""Real temporary account + HTTP suggestions: risk ON -> OFF -> ON."""
import unittest,tempfile
from pathlib import Path
from datetime import datetime,timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService

class MarketSwitchAccountFlowTests(unittest.TestCase):
    def test_off_sells_only_remainder_and_on_respects_stopped_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[datetime.fromisoformat('2026-11-05T14:31:00+00:00')]
            account=StrategyAccountService(database_path=Path(directory)/'account.db',account_id='A',clock=lambda:now[0],resolver=lambda ticker:dict(ticker=ticker,security_id=ticker,source_references=['synthetic'],source_hashes={'synthetic':'b'*64}))
            account.initialize({'event_id':'init'});counter=[0]
            def append(**event):
                counter[0]+=1;event['event_id']=str(counter[0])
                return account.append(dict(expected_revision=account.store.read()['revision'],event=event))
            def cash(amount):append(kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')
            def fill(sid,side,quantity,price='10'):append(kind='DIRECT_FILL',ticker=sid,side=side,quantity=quantity,price=price,fees='0',executed_at=now[0].isoformat())
            cash('1000');fill('A','BUY',9);fill('B','BUY',9);cash('820')
            lifecycle=RoaExecutionLifecycle(path=Path(directory)/'life.json',account_id='A',strategy_epoch='epoch',contract_sha256='a'*64)
            signal=dict(signal_id='initial',signal_date='2026-11-04',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10','B':'1/10'},execution_not_before_session='2026-11-05',securities=[dict(security_id=s,ticker=s) for s in ('A','B')])
            def calendar(day):return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00')
            unavailable=set()
            def quotes(state,sids,day,phase,clock):
                self.assertTrue(sids, 'Cash-only state must not request fictitious quotes')
                if unavailable.intersection(sids):raise ValueError('HELD_QUOTE_UNAVAILABLE')
                if not signal['risk_on'] and 'A' in sids:
                    raise ValueError('UNHELD_STOCK_QUOTE_UNAVAILABLE')
                return dict(opening_session=day,opening_prices={s:'10' for s in sids},quote_valid_until=(clock+timedelta(seconds=120)).isoformat(),marks={s:dict(security_id=s,currency='USD',price_basis='current',price='10',observed_at=clock.isoformat()) for s in sids},limits={s:dict(security_id=s,price_basis='current',buy='10.00',sell='10.00',observed_at=clock.isoformat()) for s in sids})
            service=RoaStrategyService(account_service=account,lifecycle=lifecycle,signal_provider=lambda:signal,session_provider=calendar,quote_provider=quotes,clock=lambda:now[0],execution_admission=dict(enabled=True,strategy_epoch='epoch',contract_sha256='a'*64,open_window_seconds=300,close_window_seconds=300))
            app=FastAPI();app.include_router(create_router(coordinator=service))
            with TestClient(app) as client:
                def snapshot():
                    before=account.store.read();response=client.get('/api/strategy-roa/snapshot');self.assertEqual(response.status_code,200)
                    self.assertEqual(account.store.read(),before);return response.json()
                self.assertEqual(snapshot()['status'],'READY')
                lifecycle.close_observation(session='2026-11-05',shares={'A':9,'B':9},closing_prices={'A':'7.9','B':'10'})
                signal.update(signal_id='stop',signal_date='2026-11-05',execution_not_before_session='2026-11-06')
                now[0]=datetime.fromisoformat('2026-11-06T20:56:00+00:00')
                stopped=snapshot();orders=stopped['difference']['new_orders']
                self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in orders],[('A','SELL',9)])
                fill('A','SELL',9,'8');cash('892')
                lifecycle.close_observation(session='2026-11-06',shares={'B':9},closing_prices={'B':'10'})
                self.assertIn('A',lifecycle.read()['stopped'])
                signal.update(signal_id='bear',risk_on=False,signal_date='2026-11-06',execution_not_before_session='2026-11-09')
                now[0]=datetime.fromisoformat('2026-11-09T14:31:00+00:00')
                unavailable.add('B')
                blocked=snapshot();self.assertEqual(blocked['status'],'WAIT_FRESH_QUOTE')
                self.assertFalse(blocked['executable']);self.assertIsNone(blocked['target_quantities'])
                unavailable.clear()
                off=snapshot();self.assertEqual(off['target_quantities'],{})
                self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in off['difference']['new_orders']],[('B','SELL',9)])
                # A live pending order stays in the quote domain even without holdings.
                append(kind='ORDER_OPEN',order_id='pending-a',ticker='A',side='BUY',quantity=1,limit_price='10',fee_per_share='0')
                cash('892');pending=snapshot();self.assertEqual(pending['status'],'WAIT_FRESH_QUOTE')
                self.assertFalse(pending['executable'])
                append(kind='CANCEL',order_id='pending-a');cash('892')
                self.assertEqual(snapshot()['status'],'READY')
                fill('B','SELL',4);cash('932')
                remaining=snapshot()
                self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in remaining['difference']['new_orders']],[('B','SELL',5)])
                self.assertFalse(any(o['side']=='BUY' for o in remaining['difference']['new_orders']))
                fill('B','SELL',5);cash('982')
                flat=snapshot();self.assertEqual(flat['status'],'HOLD')
                self.assertFalse(flat['executable']);self.assertEqual(flat['target_quantities'],{})
                lifecycle.close_observation(session='2026-11-09',shares={},closing_prices={})
                signal.update(signal_id='bull',risk_on=True,signal_date='2026-11-09',execution_not_before_session='2026-11-10')
                now[0]=datetime.fromisoformat('2026-11-10T14:31:00+00:00')
                on=snapshot()
                self.assertEqual(on['status'],'READY')
                self.assertNotIn('A',on['target_quantities'])
                self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in on['difference']['new_orders']],[('B','BUY',9)])
                self.assertEqual(account.store.read()['shares'],{'A':0,'B':0})
                self.assertIn('A',lifecycle.read()['stopped'])

if __name__=='__main__':unittest.main()
