"""Late evidence is not a claim of contemporaneous simulated execution."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import json

from backtest.current_quantity_v2_daily_settlement_simulation import (
    prepare_daily_settlement, apply_daily_settlement)
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_monthly_simulation import observe_monthly
from test_current_quantity_v2_daily_settlement_simulation import setup as daily_setup, reviews
from test_current_quantity_v2_monthly_simulation import setup as monthly_setup


class DelayedSettlementMonthlyTests(unittest.TestCase):
    def test_saved_minutes_settle_late_then_real_monthly_worker(self):
        # First case is next-session collection. Second deliberately collects
        # after the November decision close, before December's real acceptance.
        # Neither changes the model event's October timestamp to collection time.
        for captured_at in ('2026-10-16T09:00:00-04:00', '2026-12-01T09:59:00-05:00'):
            with self.subTest(captured_at=captured_at), TemporaryDirectory() as folder:
                helper = Path(folder)/'transport'; helper.mkdir()
                _, _, transport, calls = daily_setup(helper)
                captured = []

                def delayed_daily(state, unused_evidence):
                    self.assertTrue(any(not o['closed'] for o in state['chain']['ledger']['orders'].values()))
                    store = SimulationStore(Path(folder)/'delayed.db')
                    current = store.create(state)
                    prepared = prepare_daily_settlement(
                        store=store, simulation_id=state['simulation_id'],
                        expected_revision=current['revision'], session='2026-10-15',
                        fees={oid:'0' for oid in state['chain']['ledger']['orders']},
                        calendar_source_reference='synthetic-calendar', directory=Path(folder)/'minutes',
                        fetch=transport['fetch'], clock=lambda:datetime.fromisoformat(captured_at))
                    receipts = {p:p.read_bytes() for p in (Path(folder)/'minutes').glob('*/receipt.json')}
                    self.assertEqual(len(receipts),2)
                    for raw in receipts.values():
                        self.assertEqual(datetime.fromisoformat(json.loads(raw)['captured_at']),
                                         datetime.fromisoformat(captured_at))
                    proof = reviews(prepared,state)
                    proof['evaluated_at'] = captured_at
                    result = apply_daily_settlement(store=store,prepared=prepared,**proof)['simulation']
                    captured.append(result)
                    self.assertTrue(all(o['closed']=='FILLED' for o in result['chain']['ledger']['orders'].values()))
                    self.assertEqual(datetime.fromisoformat(result['batches'][-1]['request']['evaluated_at']),datetime.fromisoformat(captured_at))
                    self.assertEqual(datetime.fromisoformat(result['chain']['ledger']['last_recorded_at']),datetime.fromisoformat('2026-10-15T12:02:00-04:00'))
                    self.assertEqual(SimulationStore(store.path).read(state['simulation_id'])['simulation'],result)
                    self.assertEqual({p:p.read_bytes() for p in receipts},receipts)
                    self.assertLess(datetime.fromisoformat(result['chain']['ledger']['last_recorded_at']),
                                    datetime.fromisoformat('2026-11-02T16:00:00-05:00'))
                    return result

                with patch('test_current_quantity_v2_monthly_simulation.run',side_effect=delayed_daily):
                    args, _, _ = monthly_setup(folder)
                result = observe_monthly(**args)
                self.assertEqual(result['status'],'SIMULATED_MONTHLY_ACCEPTED')
                self.assertEqual(result['simulation']['chain']['ledger']['shares'],
                                 captured[0]['chain']['ledger']['shares'])
                self.assertEqual(len(calls),2)
                self.assertGreater(datetime.fromisoformat(result['accepted_at']),datetime.fromisoformat(captured_at))


if __name__=='__main__': unittest.main()

