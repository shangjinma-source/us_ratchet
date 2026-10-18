import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_current_research_intraday_mark_sources as marks
import test_current_research_intraday_monthly_selection as selection
from data.current_research_intraday_monthly_sources import review_saved_intraday_monthly_selection


class MonthlySourcesTests(unittest.TestCase):
    def fixture(self, root):
        state, inputs = marks.JournalCapitalTests().fixture(root, days=18)
        with tempfile.TemporaryDirectory() as other:
            _, training = selection.BridgeTests().fixture(other)
        base = Path(root)
        (base / 'training').write_text('Explicit synthetic training admission; not actual market evidence.', encoding='utf-8')
        selector = 'backtest/return_priority_monthly_top1_selector.py'
        (base / selector).parent.mkdir(parents=True, exist_ok=True)
        (base / selector).write_bytes((Path(__file__).resolve().parents[1] / selector).read_bytes())
        pins = {name: sha256((base / name).read_bytes()).hexdigest() for name in ('training', selector)}
        data = training['training_input']
        data['source_hashes']['training'] = pins['training']
        bundle = dict(schema='SAVED_INTRADAY_MONTHLY_TOP1_INPUT_V1', training_input=data,
            selection_calendar=training['selection_calendar'], target_month=training['target_month'], source_hashes=pins)
        raw = json.dumps(bundle).encode()
        (base / 'bundle.json').write_bytes(raw)
        now = inputs.pop('now')
        inputs.pop('root')
        return state, dict(root=root, holding_inputs=inputs, training_path='bundle.json',
            training_sha256=sha256(raw).hexdigest(), now=now)

    def test_saved_training_and_journal_capital_compose(self):
        with tempfile.TemporaryDirectory() as root:
            state, args = self.fixture(root)
            result = review_saved_intraday_monthly_selection(state, **args)
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(result['investable_equity'], '10012349/500')
            self.assertEqual(result['buy_cash_limit'], '17200')
            self.assertEqual(result['historical_reference_target_quantities'], {'new': 400})
            self.assertEqual(result['selected_capital_allocation'], {'new': '1'})
            self.assertTrue(result['source_bytes_verified'])
            self.assertFalse(result['universe_completeness_authenticated'])
            self.assertFalse(result['activated'])

    def test_changed_training_bytes_reject_before_selector(self):
        with tempfile.TemporaryDirectory() as root:
            state, args = self.fixture(root)
            (Path(root) / 'training').write_text('changed', encoding='utf-8')
            with patch('data.current_research_intraday_monthly_selection.select_top1_quantities', side_effect=AssertionError('must not select')):
                with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
                    review_saved_intraday_monthly_selection(state, **args)

    def test_duplicate_bundle_field_and_wrong_revision_reject(self):
        with tempfile.TemporaryDirectory() as root:
            state, args = self.fixture(root)
            args['holding_inputs']['expected_revision'] = 'old'
            with self.assertRaisesRegex(ValueError, 'STALE_ACCOUNT_REVISION'):
                review_saved_intraday_monthly_selection(state, **args)
            raw = b'{"schema":"one","schema":"two"}'
            (Path(root) / 'bundle.json').write_bytes(raw)
            args['training_sha256'] = sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_FIELD'):
                review_saved_intraday_monthly_selection(state, **args)


if __name__ == '__main__':
    unittest.main()
