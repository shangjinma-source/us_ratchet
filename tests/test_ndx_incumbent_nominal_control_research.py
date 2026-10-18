from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_incumbent_nominal_control_research as control


class IncumbentNominalInputTests(unittest.TestCase):
    def test_real_eight_basis_and_fixed_control_inputs(self):
        prepared = control.prepare_inputs()
        self.assertEqual(prepared['quotes']['total_rows'], 2360)
        self.assertEqual(prepared['opens'].shape, (295, 8))
        self.assertTrue(prepared['opens'].index.equals(prepared['closes'].index))
        self.assertEqual(len(prepared['schedule']['schedule']), 15)
        for ticker, series in prepared['quotes']['by_ticker'].items():
            self.assertEqual({row['split_factor'] for row in series['rows']}, {10. if ticker == 'NVDA' else 1.})
        self.assertFalse(prepared['schedule']['risk_is_order_gate'])
        self.assertFalse(prepared['quotes']['price_identity_binding_verified'])
        self.assertEqual(prepared['original_risk_parameters']['min_single_weight'], .05)
        self.assertEqual(prepared['basis']['basis_status'], 'CONDITIONAL_RESEARCH_ONLY')

    def test_source_mismatch_rejected_before_preparation(self):
        wrong = dict(control.BOUND)
        wrong[next(iter(wrong))] = '0'*64
        with patch.object(control, 'BOUND', wrong):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                control.prepare_inputs()

    def test_existing_output_does_not_repeat_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(control, 'ROOT', Path(directory)):
                path = Path(directory) / 'data/cache/research/already.json'
                path.parent.mkdir(parents=True)
                path.write_text('existing')
                with patch.object(control, 'run', side_effect=AssertionError('must not execute')):
                    with self.assertRaises(FileExistsError): control.save_report(path)
                self.assertEqual(path.read_text(), 'existing')


if __name__ == '__main__':
    unittest.main()
