from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

import test_current_research_intraday_monthly_selection as monthly
import test_current_research_intraday_monthly_sources as monthly_sources
from test_current_research_intraday_execution import payload
from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection
from data.current_research_intraday_execution_reference import read_intraday_execution_reference
from data.current_research_intraday_monthly_sources import review_saved_intraday_monthly_selection
from data.current_research_intraday_retarget_sources import review_saved_intraday_retarget, review_saved_monthly_retarget


class RetargetSourcesTests(unittest.TestCase):
    def fixture(self, root):
        state, selection_inputs = monthly.BridgeTests().fixture(root)
        selected = build_intraday_monthly_top1_selection(state, **selection_inputs)
        now = selection_inputs.pop('now')
        pins = dict(selection_inputs['source_hashes'])
        base = Path(root)
        (base / 'units.json').write_text('{"synthetic_review":true}', encoding='utf-8')
        pins['units.json'] = sha256((base / 'units.json').read_bytes()).hexdigest()
        inputs, units = {}, {}
        for sid, ticker, price, low in [('sndk', 'SNDK', 1500, 1499), ('new', 'NEW', 40.008, 39.995)]:
            data = payload()
            row = data['chart']['result'][0]
            stamp = int(now.timestamp())
            row['meta'].update(symbol=ticker, regularMarketPrice=price, regularMarketTime=stamp,
                currentTradingPeriod={'regular': dict(start=int(now.replace(hour=9, minute=30).timestamp()),
                    end=int(now.replace(hour=16, minute=0).timestamp()))})
            row['timestamp'] = [stamp-60, stamp, stamp+1]
            quote = row['indicators']['quote'][0]
            for key, value in [('open', price), ('high', price+1), ('low', low), ('close', price)]:
                quote[key][0] = value
            raw_path, receipt_path = sid+'.raw.json', sid+'.receipt.json'
            (base / raw_path).write_text(json.dumps(data), encoding='utf-8')
            pins[raw_path] = sha256((base / raw_path).read_bytes()).hexdigest()
            scope = state['account_id'] + ':2026-11'
            receipt = dict(schema='INTRADAY_EXECUTION_QUOTE_RECEIPT_V1', scope_id=scope,
                security_id=sid, ticker=ticker, session='2026-11-02', sequence=1,
                previous_receipt_sha256=None, captured_at=now.isoformat(), raw_path=raw_path, raw_sha256=pins[raw_path])
            (base / receipt_path).write_text(json.dumps(receipt), encoding='utf-8')
            pins[receipt_path] = sha256((base / receipt_path).read_bytes()).hexdigest()
            source_pins = {p: pins[p] for p in (raw_path, receipt_path)}
            inputs[sid] = dict(security_id=sid, ticker=ticker, session='2026-11-02', scope_id=scope,
                receipt_paths=[receipt_path], source_hashes=source_pins, expected_tip_sha256=pins[receipt_path])
            ref = read_intraday_execution_reference(root=root, now=now, **inputs[sid])
            units[sid] = dict(security_id=sid, selection_decision_id=selected['decision_id'],
                status='NO_UNPROCESSED_ACTIONS', reference_source_hashes=ref['source_hashes'],
                price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS', source_references=['units.json'],
                covered_from=now.isoformat(), covered_through=now.isoformat(), reviewed_asof=now.isoformat())
        return state, dict(root=root, selection=selected, selection_inputs=selection_inputs,
            execution_inputs=inputs, execution_unit_continuity=units, source_hashes=pins, now=now)

    def test_fresh_integer_differences_never_spend_expected_sell(self):
        with tempfile.TemporaryDirectory() as root:
            state, args = self.fixture(root)
            result = review_saved_intraday_retarget(state, **args)
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(result['target_quantities'], {'new': 505})
            orders = {row['side']: row for row in result['orders']}
            self.assertEqual(orders['SELL']['quantity'], 2)
            self.assertEqual(orders['BUY']['quantity'], 430)
            self.assertEqual(result['wait_cash'][0]['remaining_deficit'], 75)
            self.assertEqual(result['unfilled_sell_proceeds_available'], '0')
            self.assertFalse(result['activated'])
            self.assertTrue(result['execution_source_bytes_verified'])

    def test_changed_units_and_missing_held_quote_reject(self):
        with tempfile.TemporaryDirectory() as root:
            state, args = self.fixture(root)
            missing = dict(args, execution_inputs={'new': args['execution_inputs']['new']})
            with self.assertRaisesRegex(ValueError, 'EXECUTION_UNIT_DOMAIN_MISMATCH'):
                review_saved_intraday_retarget(state, **missing)
            (Path(root) / 'units.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'UNIT_SOURCE_HASH_MISMATCH'):
                review_saved_intraday_retarget(state, **args)

    def test_full_monthly_source_to_execution_preserves_attestation_envelope(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            state, monthly_args = monthly_sources.MonthlySourcesTests().fixture(root)
            enriched = review_saved_intraday_monthly_selection(state, **monthly_args)
            self.assertTrue(enriched['source_bytes_verified'])
            _, execution = self.fixture(other)
            execution_pins = {}
            for inputs in execution['execution_inputs'].values():
                self.assertEqual(inputs['scope_id'], state['account_id']+':2026-11')
                execution_pins.update(inputs['source_hashes'])
            execution_pins['units.json'] = execution['source_hashes']['units.json']
            for name in execution_pins:
                (Path(root) / name).write_bytes((Path(other) / name).read_bytes())
            selected_at = monthly_args.pop('now')
            monthly_args.pop('root')
            for unit in execution['execution_unit_continuity'].values():
                unit['selection_decision_id'] = enriched['decision_id']
                unit['covered_from'] = selected_at.isoformat()
            result = review_saved_monthly_retarget(state, root=root, monthly_inputs=monthly_args,
                selection_at=selected_at, execution_inputs=execution['execution_inputs'],
                execution_unit_continuity=execution['execution_unit_continuity'],
                execution_source_hashes=execution_pins, now=execution['now'])
            self.assertEqual(result['status'], 'READY', result)
            self.assertTrue(result['selection_source_attestation']['source_bytes_verified'])
            self.assertEqual(result['selection_source_attestation']['training_bundle_sha256'], enriched['training_bundle_sha256'])
            self.assertNotIn('source_bytes_verified', result['binding']['selection'])
            self.assertEqual(result['reserved_buy_cash'], '171957/10')
            self.assertEqual(result['unfilled_sell_proceeds_available'], '0')


if __name__ == '__main__':
    unittest.main()
