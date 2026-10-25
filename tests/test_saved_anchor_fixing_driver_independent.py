import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backtest import quantity_saved_anchor_coordinate_fixing as fixing
from test_quantity_saved_anchor_coordinate_fixing import sources

ROOT = Path(__file__).resolve().parents[1]

def driver():
    spec = importlib.util.spec_from_file_location('fixing_driver_test', ROOT/'tmp/run_saved_anchor_coordinate_fixing_20261019_v1.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def prepared():
    source, _ = sources()
    plans = [dict(source, id='open-'+str(i)) for i in range(2)]
    closed = [dict(id='closed-'+str(i), upper_product='1', empty=False) for i in range(3)]
    return SimpleNamespace(PINS={}, check=lambda value: None), dict(lower_product='1', selected={}), plans, closed, {}, {}


class IndependentFixingDriver(unittest.TestCase):
    def test_default_no_fixing_and_success_preserves_five_regions(self):
        module = driver()
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)), patch.object(module, 'OUTPUT', 'result'), patch.object(module, 'prepare', return_value=prepared()), patch.object(module, 'check'), patch.object(module, 'read', return_value=b'{"upper_product":"100"}'):
            with patch('sys.argv', ['driver']), patch.object(fixing, 'build', side_effect=AssertionError('DEFAULT MUST NOT BUILD')), redirect_stdout(io.StringIO()):
                module.main()
            self.assertFalse((Path(tmp)/module.OUTPUT).exists())
            with patch('sys.argv', ['driver', '--execute']), redirect_stdout(io.StringIO()):
                module.main()
            out = Path(tmp)/module.OUTPUT
            report = json.loads((out/'report.json').read_text())
            self.assertEqual(len(report['inherited_closed_rows']), 3)
            self.assertEqual(len(report['new_rows']), 2)
            self.assertEqual(report['inherited_closed_rows'], prepared()[3])
            for row in report['new_rows']:
                self.assertTrue((out/row['certificate_path']).is_file())
            with patch('sys.argv', ['driver', '--execute']), patch.object(fixing, 'build', side_effect=AssertionError('NO RETRY')):
                with self.assertRaises(FileExistsError): module.main()

    def test_failure_retains_started_and_blocks_retry(self):
        module = driver()
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)), patch.object(module, 'OUTPUT', 'result'), patch.object(module, 'prepare', return_value=prepared()), patch('sys.argv', ['driver', '--execute']), patch.object(fixing, 'build', side_effect=ValueError('SYNTHETIC_FAILURE')) as build:
            with self.assertRaisesRegex(ValueError, 'SYNTHETIC_FAILURE'): module.main()
            out = Path(tmp)/module.OUTPUT
            for name in ['started.json', 'failed.json', 'box-0/started.json', 'box-0/failed.json']:
                self.assertTrue((out/name).is_file())
            self.assertFalse((out/'terminal.json').exists())
            self.assertFalse((out/'report.json').exists())
            with self.assertRaises(FileExistsError): module.main()
            self.assertEqual(build.call_count, 1)


if __name__ == '__main__': unittest.main()

