"""Read-only independent regression evidence; no live registration or accounts."""
from tempfile import TemporaryDirectory
from pathlib import Path
import json
from datetime import datetime
from fractions import Fraction
from copy import deepcopy
import unittest
import test_registered_quantity_v2_paper_protocol as fixtures
from data.registered_quantity_v2_paper_protocol import validate_start_receipt


class IndependentProtocolBoundaries(unittest.TestCase):
    def test_nonzero_modeled_fee_evidence_not_charged_on_expiry(self):
        from test_current_quantity_v2_continuation_simulation import expire_all
        from backtest.current_quantity_v2_simulated_settlement import settle
        with TemporaryDirectory() as folder:
            validated, receipt, state, now, save, _ = fixtures.ProtocolStoreTests().prepare(folder)
            template = expire_all(state)['batches'][-1]['request']
            evidence = deepcopy(template['evidence'])
            for oid, row in evidence.items():
                order = state['chain']['ledger']['orders'][oid]
                row['fees'] = str(Fraction(1) + Fraction('0.001') * order['quantity'] * Fraction(order['limit_price']))
            fees = save('fees.json', dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',
                status='MODELLED_FEES_NOT_BROKER_FEES', fixed_per_order='1', notional_rate='0.001'))
            validated['documents']['daily']['fees_sha256'] = fees['sha256']
            settled = settle(simulation=state, evidence=evidence,
                observed_through=template['observed_through'], evaluated_at=template['evaluated_at'])
            checked_at = datetime.fromisoformat('2026-10-16T17:00:00-04:00')
            self.assertEqual(validate_start_receipt(validated=validated, receipt=receipt,
                simulation=settled, now=checked_at)['status'], 'START_AND_REPLAY_BOUND')
            self.assertEqual(settled['chain']['ledger']['cash'], state['chain']['ledger']['cash'])
            self.assertEqual(Fraction(settled['chain']['ledger']['recorded_fees']), 0)
            wrong = save('fees.json', dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',
                status='MODELLED_FEES_NOT_BROKER_FEES', fixed_per_order='2', notional_rate='0.001'))
            validated['documents']['daily']['fees_sha256'] = wrong['sha256']
            with self.assertRaisesRegex(ValueError, 'SETTLEMENT_FEE_POLICY_MISMATCH'):
                validate_start_receipt(validated=validated, receipt=receipt,
                    simulation=settled, now=checked_at)

    def test_two_real_acceptances_keep_old_fee_binding(self):
        from test_current_quantity_v2_continuation_simulation import expire_all, daily_arguments, cash_review
        from backtest.current_quantity_v2_continuation_simulation import apply_continuation
        from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
        with TemporaryDirectory() as folder:
            validated, receipt, state, now, _, _ = fixtures.ProtocolStoreTests().prepare(folder)
            validated['request']['evaluation']['end_session'] = '2026-10-16'
            expired = expire_all(state)
            old_ids = set(expired['chain']['ledger']['orders'])
            args, _, _ = daily_arguments(folder, expired, '2026-10-16')
            args.update(root=Path(folder)/'bootstrap-fixture', unit_review_reader=cash_review)
            boot = json.loads((args['root']/'config.json').read_bytes())
            original_fetch = args['fetch']
            def complete_minutes(ticker):
                raw = json.loads(original_fetch(ticker)); chart = raw['chart']['result'][0]
                chart['timestamp'] = list(range(chart['meta']['currentTradingPeriod']['regular']['start'],
                                               int(args['clock']().timestamp())//60*60, 60))
                n = len(chart['timestamp'])
                chart['indicators']['quote'] = [{k: [v[0]]*n for k, v in chart['indicators']['quote'][0].items()}]
                return json.dumps(raw).encode()
            args['fetch'] = complete_minutes
            args['pullback_policy'] = boot['pullback']['policy']
            args['pullback_cap_store'] = LazyPullbackCapStore(boot['pullback']['database_path'],
                clock=lambda: args['clock']().isoformat(), max_history_rows=512, max_history_bytes=128*1024*1024)
            (args['root']/'daily-schedule.json').write_bytes((Path(folder)/'daily-schedule.json').read_bytes())
            accepted = apply_continuation(**args)['simulation']
            self.assertTrue(old_ids)
            self.assertFalse(old_ids.intersection(accepted['chain']['ledger']['orders']))
            settled = expire_all(accepted)
            result = validate_start_receipt(validated=validated, receipt=receipt, simulation=settled,
                                           now=datetime.fromisoformat('2026-10-16T17:00:00-04:00'))
            self.assertEqual(result['status'], 'START_AND_REPLAY_BOUND')

    def test_actual_calendar_must_match_approved_calendar(self):
        with TemporaryDirectory() as folder:
            validated, receipt, state, now, _, _ = fixtures.ProtocolStoreTests().prepare(folder)
            validated['calendar']['calendar'] = ['2026-10-15']
            validated['calendar']['sessions'] = [r for r in validated['calendar']['sessions']
                                                  if r['date'] == '2026-10-15']
            actual = state['valuation']['registration']['calendar']['session_dates']
            approved = validated['calendar']['calendar']
            self.assertNotEqual(actual, approved)
            self.assertEqual(actual, ['2026-10-15', '2026-10-16'])
            self.assertEqual(approved, ['2026-10-15'])
            with self.assertRaisesRegex(ValueError, 'VALUATION_CALENDAR_MISMATCH'):
                validate_start_receipt(validated=validated, receipt=receipt,
                                       simulation=state, now=now)


if __name__ == '__main__':
    unittest.main()
