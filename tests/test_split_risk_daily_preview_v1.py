"""Persisted risk to daily difference with synthetic reviewed history/quotes."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from hashlib import sha256
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates.strategy_split_frontier_preview_service import SavedFrontierPreviewService
import test_split_monthly_publication_v1 as monthly_fixture


class SplitRiskDailyPreviewTests(unittest.TestCase):
    def test_persisted_exit_blocks_rebuy_after_rebound_and_cash_change(self):
        with TemporaryDirectory() as folder:
            monthly, provider, accounts, state, _ = monthly_fixture.SplitMonthlyPublicationTests().case(folder)
            state, _ = accounts.append(dict(event_id='cancel', kind='CANCEL', order_id='buy'), expected_revision=state['revision'])
            state, _ = accounts.append(dict(event_id='confirmed', kind='CASH_CONFIRM', amount='100',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=state['revision'])
            target = monthly.generate(event_id='initial', reason='INITIAL', expected_revision=state['revision'], previous_target_id=None)
            baseline = target['payload']['target_quantities']
            risk = MonthlyPeakExitStore(Path(folder)/'risk.sqlite3')
            def observation(day, price):
                row = dict(decision_date='2026-10-30', session_date=day,
                    closes={'A':'10', 'B':price}, unit_ids={'A':'new','B':'base'})
                return dict(row, evidence_sha256=sha256(canonical(row)).hexdigest())
            result = risk.advance(account_id=state['account_id'], expected_previous_session=None,
                observations=[observation('2026-10-30','10'), observation('2026-11-02','8')],
                baseline_targets=baseline, target_month='2026-11')
            self.assertIn('B', result['state']['exited'])
            # New cash and a rebound must not create a new monthly risk epoch.
            state, _ = accounts.append(dict(event_id='more-cash', kind='CASH_CONFIRM', amount='300',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=state['revision'])
            result = risk.advance(account_id=state['account_id'], expected_previous_session='2026-11-02',
                observations=[observation('2026-11-03','11')], baseline_targets=baseline, target_month='2026-11')
            self.assertEqual(MonthlyPeakExitStore(risk.path).read(state['account_id']), result['state'])
            now = datetime.fromisoformat('2026-11-04T15:00:00+00:00')
            effective = {sid:result['effective_target_quantities'].get(sid,0) for sid in set(state['shares'])|set(baseline)}
            signal = dict(account_id=state['account_id'], account_revision=state['revision'], target_id=target['target_id'],
                policy_id='synthetic-reviewed-risk', evidence_id='synthetic-risk-history',
                observed_at='2026-11-03T21:00:00+00:00', available_at='2026-11-03T21:01:00+00:00',
                valid_from=now.isoformat(), valid_until=(now+timedelta(seconds=60)).isoformat(),
                effective_target_quantities=effective)
            seen=[]
            def execution(snapshot, quantities, at):
                seen.append(deepcopy(quantities))
                self.assertEqual(quantities['B'],0)
                mark=dict(security_id='A',currency='USD',price='10',price_basis='CURRENT_UNIT',
                    observed_at=now.isoformat(),unit_id='new')
                limit=dict(security_id='A',buy='10',sell='10',price_basis='CURRENT_UNIT',unit_id='new',
                    observed_at=now.isoformat(),reference_valid_until=(now+timedelta(seconds=60)).isoformat())
                return dict(marks={'A':mark},limits={'A':limit})
            service=SavedFrontierPreviewService(account_store=accounts,target_store=monthly.targets,
                signal_verifier=lambda *args:deepcopy(signal),execution_provider=execution,
                policy_id=signal['policy_id'],clock=lambda:now,fee_bps='0',maximum_mark_age_seconds=120,
                monthly_quantities=baseline)
            output=service.preview()
            self.assertEqual([(row['security_id'],row['side'],row['quantity']) for row in output['new_orders']], [('A','SELL',16)])
            self.assertEqual(accounts.read(),state)
            signal['valid_until']=now.isoformat()
            signal['valid_from']=(now-timedelta(seconds=60)).isoformat()
            self.assertEqual(service.preview()['status'],'WAIT_FRESH_SIGNAL')
            self.assertEqual(len(seen),1)


if __name__=='__main__':
    unittest.main()
