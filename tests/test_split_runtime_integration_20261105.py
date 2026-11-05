from datetime import datetime,timedelta
from fractions import Fraction as F
from functools import partial
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_account_live_pullback_runtime import LazyPullbackCapStore
from docs.candidates.strategy_account_split_execution_limits import build_execution_limits
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from docs.candidates.split_runtime_integration_20261105 import SplitRuntime
import test_split_monthly_publication_v1 as monthly_fixture


class RuntimeIntegration(unittest.TestCase):
    def test_sale_cash_daily_ui_ai_same_runtime_and_stale_jobs(self):
        with TemporaryDirectory() as folder:
            monthly,provider,accounts,state,clock=monthly_fixture.SplitMonthlyPublicationTests().case(folder)
            # Real UI purchase-power convention with a genuine open reservation.
            reserved=F(state['reserved_cash']);self.assertGreater(reserved,0)
            state,_=accounts.append(dict(event_id='cash-ui',kind='CASH_CONFIRM',amount='100',
                                         cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
            self.assertEqual(F(state['available_cash']),100)
            self.assertEqual(F(state['total_uninvested_cash']),100+reserved)
            state,_=accounts.append(dict(event_id='cancel',kind='CANCEL',order_id='buy'),expected_revision=state['revision'])
            state,_=accounts.append(dict(event_id='cash-clean',kind='CASH_CONFIRM',amount='100',
                                         cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
            target=monthly.generate(event_id='initial',reason='INITIAL',expected_revision=state['revision'],previous_target_id=None)
            risk=MonthlyPeakExitStore(Path(folder)/'risk.sqlite3')
            def observation(day,value):
                row=dict(decision_date='2026-10-30',session_date=day,closes={'A':'10','B':value},unit_ids={'A':'new','B':'base'})
                return dict(row,evidence_sha256=sha256(canonical(row)).hexdigest())
            risk.advance(account_id=state['account_id'],expected_previous_session=None,
                         observations=[observation('2026-10-30','10'),observation('2026-11-02','8')],
                         baseline_targets=target['payload']['target_quantities'],target_month='2026-11')
            now=provider.clock()
            class Identity:
                def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
                def _read(self,path,digest):return b'id'
            def fetch(ticker):
                opening=int(now.replace(hour=14,minute=30).timestamp())
                return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
                    exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=int(now.timestamp()),
                    currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=[int(now.timestamp())-60],
                    indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
            provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=fetch,clock=lambda:now)
            provider.limits=partial(build_execution_limits,cap_store=LazyPullbackCapStore(Path(folder)/'caps.sqlite3',clock=lambda:now.isoformat(),max_history_rows=32,max_history_bytes=8*1024*1024))
            def signal(snapshot,at):
                account,goal,r=(snapshot[k] for k in ('account','target','risk'))
                baseline=goal['payload']['target_quantities']
                return dict(account_id=account['account_id'],account_revision=account['revision'],target_id=goal['target_id'],
                    policy_id='synthetic-risk-evidence',evidence_id=sha256(canonical(r)).hexdigest(),
                    observed_at=(at-timedelta(minutes=1)).isoformat(),available_at=(at-timedelta(seconds=30)).isoformat(),
                    valid_from=at.isoformat(),valid_until=(at+timedelta(seconds=60)).isoformat(),
                    effective_target_quantities={s:0 if s in r['exited'] else baseline.get(s,0) for s in set(account['shares'])|set(baseline)})
            runtime=SplitRuntime(monthly=monthly,provider=provider,risk_store=risk,signal_builder=signal,clock=lambda:now)
            self.assertIs(runtime.ui,runtime.ai);self.assertIs(runtime.daily_observer,runtime.ui)
            first=runtime.ui.preview();order=first['new_orders'][0]
            self.assertEqual((order['security_id'],order['side'],order['quantity']),('A','SELL',16))
            # Capture actual returned quote deadlines, never a guessed lifetime.
            controlled=[now];runtime.clock=lambda:controlled[0]
            for offset,accepted in [(-1,True),(0,False),(1,False)]:
                controlled[0]=now
                timed=runtime.ai.start_ai();validity=timed['preview']['ai_validity']
                actual=[datetime.fromisoformat(v['reference_valid_until']) for v in timed['preview']['reference_quotes'].values()]
                self.assertTrue(actual)
                expected=min(actual+[datetime.fromisoformat(validity['signal_valid_until'])])
                self.assertEqual(datetime.fromisoformat(validity['valid_until']),expected)
                controlled[0]=expected+timedelta(microseconds=offset)
                if accepted:self.assertEqual(runtime.ai.complete_ai(timed['job_id'],{'model_stub':'timed'})['status'],'BOUND_REVIEW_ONLY')
                else:
                    with self.assertRaisesRegex(ValueError,'AI_QUOTE_OR_SIGNAL_EXPIRED'):
                        runtime.ai.complete_ai(timed['job_id'],{'model_stub':'late'})
            controlled[0]=now
            old_job=runtime.ai.start_ai()
            fill=dict(event_id='simulated-fill',kind='DIRECT_FILL',security_id='A',side='SELL',quantity=16,
                      price=order['limit_price'],fees='0',executed_at=now.isoformat())
            sold,_=runtime.append(fill,expected_revision=state['revision'])
            self.assertFalse(sold['cash_confirmation_valid'])
            with self.assertRaisesRegex(ValueError,'AI_ACCOUNT_TARGET_RISK_GENERATION_CHANGED'):
                runtime.ai.complete_ai(old_job['job_id'],{'model_stub':'stale'})
            # Keep a pending order while confirming actual AVAILABLE cash.
            pending,_=runtime.append(dict(event_id='reserve',kind='ORDER_OPEN',order_id='pending',security_id='B',
                side='BUY',quantity=2,limit_price='10',fee_per_share='0'),expected_revision=sold['revision'])
            amount=F(sold['total_uninvested_cash'])-20
            confirmed,_=runtime.append(dict(event_id='after-fill-cash',kind='CASH_CONFIRM',amount=str(amount),
                 cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=pending['revision'])
            self.assertEqual(F(confirmed['available_cash']),amount)
            self.assertEqual(F(confirmed['total_uninvested_cash']),amount+20)
            confirmed,_=runtime.append(dict(event_id='cancel-pending',kind='CANCEL',order_id='pending'),expected_revision=confirmed['revision'])
            fresh=runtime.ui.preview();job=runtime.ai.start_ai()
            self.assertEqual(fresh['reference_quotes'],{})
            self.assertEqual(datetime.fromisoformat(fresh['ai_validity']['valid_until']),
                             datetime.fromisoformat(fresh['ai_validity']['signal_valid_until']))
            self.assertEqual(job['context']['account'],accounts.read())
            self.assertEqual(job['context']['target'],monthly.targets.current())
            self.assertEqual(job['preview'],fresh)
            self.assertFalse(any(o['security_id']=='A' for o in fresh['new_orders']))
            self.assertFalse(any(o['security_id']=='B' and o['side']=='BUY' for o in fresh['new_orders']))
            self.assertIn('B',risk.read(state['account_id'])['exited'])
            self.assertEqual(runtime.ai.complete_ai(job['job_id'],{'model_stub':'review'})['status'],'BOUND_REVIEW_ONLY')
            old_target_job=runtime.ai.start_ai()
            monthly.generate(event_id='reconfigure',reason='EXPLICIT_RECONFIGURE',expected_revision=confirmed['revision'],previous_target_id=target['target_id'])
            with self.assertRaisesRegex(ValueError,'AI_ACCOUNT_TARGET_RISK_GENERATION_CHANGED'):
                runtime.ai.complete_ai(old_target_job['job_id'],{'model_stub':'stale-target'})


if __name__=='__main__':unittest.main()
