"""Actual native search/proposal/daily chain; all accounts and evidence synthetic."""
from datetime import timedelta
from contextlib import closing
from functools import partial
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.saved_frontier_monthly_view_v1 import SavedFrontierProposalStore, SavedFrontierMonthlyView
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_account_live_pullback_runtime import LazyPullbackCapStore
from docs.candidates.strategy_account_split_execution_limits import build_execution_limits
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from docs.candidates.split_runtime_integration_20261105 import SplitRuntime
from docs.candidates.split_continuous32_integration_20261105 import (
    RUNTIME_PATHS, SplitContinuous32TargetService, SplitContinuous32MonthlyService,
)
import test_split_monthly_publication_v1 as fixtures


class ContinuousSplitIntegration(unittest.TestCase):
    def test_native_search_persisted_frontier_drives_actual_split_daily(self):
        with TemporaryDirectory() as folder:
            old, provider, accounts, state, _ = fixtures.SplitMonthlyPublicationTests().case(folder)
            state, _ = accounts.append(dict(event_id='cancel',kind='CANCEL',order_id='buy'),expected_revision=state['revision'])
            state, _ = accounts.append(dict(event_id='native-cash',kind='CASH_CONFIRM',amount='100',
                cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
            root=Path(__file__).resolve().parents[1];pins={}
            for name in RUNTIME_PATHS:
                raw=(root/name).read_bytes();path=provider.root/name
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                pins[name]=sha256(raw).hexdigest()
            selection=SplitContinuous32TargetService(store=accounts,evidence_provider=provider.selection,
                runtime_root=provider.root,runtime_pins=pins,maximum_mark_age_seconds=900,
                execution_fee_bps='0',clock=provider.clock)
            monthly=SplitContinuous32MonthlyService(selection_service=selection,target_store=old.targets,
                execution_provider=provider.execution,clock=provider.clock)
            proposals=SavedFrontierProposalStore(Path(folder)/'frontier.sqlite3')
            view=SavedFrontierMonthlyView(monthly=monthly,proposals=proposals,validate_sources=selection._pins)
            request=dict(event_id='native',reason='INITIAL',expected_revision=state['revision'],previous_target_id=None)
            target=view.generate(**request)
            self.assertEqual(target,view.current())
            self.assertEqual(target,view.generate(**request))
            raw_target=monthly.current()
            self.assertEqual(target['frontier_proposal'],build_frontier_proposal(target=raw_target))
            self.assertNotEqual(raw_target['payload']['target_quantities'],target['risk_monthly_targets'])
            self.assertEqual(target['payload']['decision']['payload']['schema'],'REAL_STRATEGY_CONTINUOUS32_TARGET_DECISION_V1')
            self.assertEqual(target['payload']['decision']['core_calls'],1)
            self.assertIn('continuous_comparison',target['payload']['decision']['payload']['search_result'])
            self.assertEqual(accounts.read(),state)
            now=provider.clock()
            class Identity:
                def __call__(self,ticker):
                    return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
                def _read(self,path,digest):return b'id'
            def fetch(ticker):
                opening=int(now.replace(hour=14,minute=30).timestamp())
                return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
                    exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=int(now.timestamp()),
                    currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=[opening+60*i for i in range(30)],
                    indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
            provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=fetch,clock=lambda:now)
            provider.limits=partial(build_execution_limits,cap_store=LazyPullbackCapStore(Path(folder)/'caps.sqlite3',
                clock=lambda:now.isoformat(),max_history_rows=32,max_history_bytes=8*1024*1024))
            risk=MonthlyPeakExitStore(Path(folder)/'risk.sqlite3')
            observation=dict(decision_date='2026-10-30',session_date='2026-10-30',closes={'A':'10','B':'10'},unit_ids={'A':'new','B':'base'})
            risk.advance(account_id=state['account_id'],expected_previous_session=None,
                observations=[dict(observation,evidence_sha256=sha256(canonical(observation)).hexdigest())],
                baseline_targets=target['risk_monthly_targets'],target_month='2026-11')
            def signal(snapshot,at):
                account,goal,r=(snapshot[k] for k in ('account','target','risk'))
                baseline=goal['risk_monthly_targets']
                return dict(account_id=account['account_id'],account_revision=account['revision'],target_id=goal['target_id'],proposal_id=goal['proposal_id'],
                    policy_id='synthetic-risk-evidence',evidence_id=sha256(canonical(r)).hexdigest(),
                    observed_at=(at-timedelta(minutes=1)).isoformat(),available_at=(at-timedelta(seconds=30)).isoformat(),
                    valid_from=at.isoformat(),valid_until=(at+timedelta(seconds=60)).isoformat(),
                    effective_target_quantities={sid:0 if sid in r['exited'] else baseline.get(sid,0) for sid in set(account['shares'])|set(baseline)})
            runtime=SplitRuntime(monthly=monthly,provider=provider,risk_store=risk,signal_builder=signal,
                clock=lambda:now,frontier_view=view)
            preview=runtime.preview()
            self.assertEqual(preview['status'],'CONDITIONAL_PREVIEW_READY')
            self.assertEqual(preview['effective_target_quantities']['B'],target['risk_monthly_targets']['B'])
            self.assertNotEqual(preview['effective_target_quantities']['B'],raw_target['payload']['target_quantities']['B'])
            self.assertTrue(any(row['side']=='SELL' and row['security_id']=='A' and row['quantity']==16 for row in preview['new_orders']))
            self.assertTrue(any(row['side']=='BUY' and row['security_id']=='B' for row in preview['new_orders']))
            self.assertEqual(runtime.context()['target']['proposal_id'],target['proposal_id'])
            self.assertEqual(monthly.current(),raw_target)
            self.assertEqual(accounts.read(),state)
            runtime.signal_builder=lambda snapshot,at:dict(signal(snapshot,at),proposal_id='0'*64)
            with self.assertRaisesRegex(ValueError,'RUNTIME_SIGNAL_PROPOSAL_MISMATCH'):
                runtime.preview()
            # Saved bytes, not an attached invented identifier, are authoritative.
            import sqlite3
            with closing(sqlite3.connect(proposals.path)) as connection, connection:
                connection.execute('UPDATE frontier_proposals SET document=?',(b'{}',))
            with self.assertRaisesRegex(ValueError,'FRONTIER_PROPOSAL_CHANGED'):
                runtime.context()


if __name__=='__main__':unittest.main()
