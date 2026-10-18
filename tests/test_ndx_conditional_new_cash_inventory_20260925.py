"""Synthetic source structures only; never builds the saved 24-lane inventory."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cash_inventory_owner', Path(__file__).resolve().parents[1] / 'scripts/ndx_conditional_new_cash_inventory_20260925.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    days = []
    day = date(2023, 3, 31)
    while day <= date(2023, 9, 1):
        if day.weekday() < 5 and day.isoformat() not in {'2023-04-07', '2023-05-29', '2023-06-19', '2023-07-04'}:
            days.append(day.isoformat())
        day += timedelta(days=1)
    target = {'A': dict(ticker='AAA', issuer_id='issuer:A', target_weight=1.0)}
    original_target = dict(target, TSM=dict(ticker='TSM', issuer_id='saved:overlay', target_weight=.2))
    schedules = [dict(decision_date=d, execution_date=e, targets=deepcopy(target)) for d, e in module.CLOCK]
    originals = [dict(decision_date=d, execution_date=e, targets=deepcopy(original_target)) for d, e in module.CLOCK]
    daily = [dict(session=d, cash_usd=1478.4820750045776, shares={'A': 1, 'TSM': 2},
                  tickers={'A': 'AAA', 'TSM': 'TSM'}, prices={'A': 10.0, 'TSM': 20.0},
                  risk={'checks': {'MIN_SINGLE_WEIGHT': False}}, risk_chains={'A': 'chain', 'TSM': 'foundry'},
                  risk_chain_observation_dates={'A': d, 'TSM': d}) for d in days]
    matrices = {'open': {d: {'AAA': '11'} for d in days}, 'close': {d: {'AAA': '10'} for d in days}}
    identities = [dict(security_id='A', issuer_id='issuer:A', ticker='AAA', continuous_interval_verified=False)]
    refs = {key: {'path': key + '.json', 'sha256': str(index).zfill(64)} for index, key in enumerate(module.BOUND)}
    docs = {'benchmark': dict(calendar=days, decision_clock=[list(pair) for pair in module.CLOCK], incumbent={'daily': deepcopy(daily)}),
            'control': dict(execution={'daily': deepcopy(daily)},
                            original_fixed_schedule={'schedule': originals, 'risk_chains_by_decision': {d: {'A': 'chain', 'TSM': 'foundry'} for d, _ in module.CLOCK}},
                            nominal_quotes={'by_ticker': {ticker: {'rows': [dict(session=d, currency='USD', nominal_open=price) for d in days]} for ticker, price in [('AAA', 11.0), ('TSM', 21.0)]}})}
    for lane in module.LANES:
        docs[lane + '_schedule'] = dict(schedule=deepcopy(schedules), risk_chains_by_decision={d: {'A': 'chain'} for d, _ in module.CLOCK})
        docs[lane + '_account'] = dict(schedule=deepcopy(schedules), calendar=days, additional_cash_flows_supported=False)
        docs[lane + '_comparison'] = dict(calendar=days, additional_cash_flows_supported=False, candidate_reference=refs[lane + '_account'])
        if lane in ('BAD_TAIL', 'DRAWDOWN'):
            role = lane + ('_projection' if lane == 'BAD_TAIL' else '_assembly')
            docs[role] = dict(price_projection={'matrices': deepcopy(matrices)}, identity_projection={'rows': deepcopy(identities)})
        else:
            docs[lane + '_price'] = {'matrices': deepcopy(matrices)}
            docs[lane + '_identity'] = {'rows': deepcopy(identities)}
    return docs, refs


class InventoryTests(unittest.TestCase):
    def test_36_branches_same_baseline_open_not_close_no_cash_guess(self):
        docs, refs = fixture()
        before = deepcopy(docs)
        result = module.assemble(docs, refs)
        self.assertEqual(docs, before)
        self.assertEqual(result['branch_coordinate_count'], 36)
        self.assertEqual(result['control_coordinate_count'], 12)
        row = result['rows'][1]
        self.assertEqual(row['baseline_cash_encoding']['decimal_literal'], '1478.4820750045776')
        self.assertFalse(row['baseline']['risk']['checks']['MIN_SINGLE_WEIGHT'])
        self.assertIsNone(row['cash_event_amount_usd'])
        self.assertEqual({value['decimal_literal'] for value in row['securities'][0]['execution_open_observations']}, {'11', '11.0'})
        self.assertTrue(any(gap['reason'] == 'DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE' for gap in row['gaps']))
        self.assertEqual(result['rows'][-1]['forward_window']['available_after_execution_sessions'], 0)
        self.assertEqual(result['rows'][-1]['lane_target']['targets'], {})

    def test_missing_price_and_source_conflict_are_preserved_gaps(self):
        docs, refs = fixture()
        day = module.CLOCK[0][1]
        docs['RETURN_price']['matrices']['open'][day]['AAA'] = '12'
        result = module.assemble(docs, refs)
        self.assertIn('EXECUTION_OPEN_SOURCE_CONFLICT', [gap['reason'] for gap in result['rows'][0]['gaps']])
        del docs['RETURN_price']['matrices']['open'][day]['AAA']
        docs['control']['nominal_quotes']['by_ticker']['AAA']['rows'] = []
        result = module.assemble(docs, refs)
        self.assertIn('EXECUTION_OPEN_MISSING', [gap['reason'] for gap in result['rows'][0]['gaps']])

    def test_no_overlay_upgrade_and_late_risk_rejected_as_gap(self):
        docs, refs = fixture()
        result = module.assemble(docs, refs)
        row = next(item for item in result['rows'][0]['securities'] if item['security_id'] == 'TSM')
        self.assertEqual(row['saved_coordinates'][0]['value']['issuer_id'], 'saved:overlay')
        self.assertEqual(row['dated_identity_evidence'], [])
        docs['benchmark']['incumbent']['daily'][0]['risk_chain_observation_dates']['TSM'] = '2099-01-01'
        docs['control']['execution']['daily'][0] = deepcopy(docs['benchmark']['incumbent']['daily'][0])
        result = module.assemble(docs, refs)
        self.assertIn('HISTORICAL_RISK_OBSERVATION_MISSING_OR_FUTURE', [gap['reason'] for gap in result['rows'][0]['gaps']])

    def test_same_ticker_different_security_not_price_joined(self):
        docs, refs = fixture()
        alternate = dict(ticker='AAA', issuer_id='other', target_weight=1.0)
        docs['RETURN_schedule']['schedule'][0]['targets'] = {'OTHER': alternate}
        docs['RETURN_account']['schedule'][0]['targets'] = {'OTHER': deepcopy(alternate)}
        docs['RETURN_schedule']['risk_chains_by_decision'][module.CLOCK[0][0]] = {'OTHER': 'chain'}
        result = module.assemble(docs, refs)
        row = next(item for item in result['rows'][0]['securities'] if item['security_id'] == 'OTHER')
        self.assertIn('SAME_TICKER_DIFFERENT_SID_NO_AUTOMATIC_PRICE_JOIN', row['gaps'])
        self.assertEqual(row['execution_open_observations'], [])

    def test_mutated_clock_account_or_bool_cash_fail(self):
        for attack in ('clock', 'account', 'cash'):
            docs, refs = fixture()
            if attack == 'clock':
                docs['benchmark']['decision_clock'][0][1] = '2023-04-04'
            elif attack == 'account':
                docs['RETURN_account']['schedule'][0]['targets']['A']['target_weight'] = .5
            else:
                docs['benchmark']['incumbent']['daily'][0]['cash_usd'] = True
                docs['control']['execution']['daily'][0]['cash_usd'] = True
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                module.assemble(docs, refs)

    def test_source_drift_after_inventory_preserves_failed_marker_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.write_text('sealed')
            output = root / 'new'
            result = {'source_hashes': {str(source): module.digest(source)}}
            original = module.durable
            def drift(path, raw):
                original(path, raw)
                if path.name == 'inventory.json':
                    source.write_text('changed')
            with patch.object(module, 'OUTPUT', output), patch.object(module, 'build', return_value=result), patch.object(module, 'durable', side_effect=drift):
                with self.assertRaises(ValueError):
                    module.publish()
                self.assertTrue((output / 'failure.json').exists())
                self.assertFalse((output / 'publication.json').exists())
                with self.assertRaises(ValueError):
                    module.publish()


if __name__ == '__main__':
    unittest.main()
