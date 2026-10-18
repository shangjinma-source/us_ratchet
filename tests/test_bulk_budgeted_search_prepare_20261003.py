import importlib.util
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta
from copy import deepcopy

path = Path(__file__).resolve().parents[1] / 'scripts/ndx_bulk_budgeted_search_prepare_20261003.py'
spec = importlib.util.spec_from_file_location('bulk_budget_prepare', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def panel_fixture():
    universe = [[f's{i:03}', f'T{76-i:03}', f'i{min(i,75):03}', 'R'] for i in range(77)]
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(126)]
    flags = dict.fromkeys(('point_in_time_verified', 'legal_training_input_admitted',
        'promotion_allowed', 'execution_authorized', 'fit_performed'), False)
    inner = dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1', cutoff=days[-1],
        panel_content_sha256='a'*64,
        universe=dict(type='dataframe', index_kind='RangeIndex', columns=['security_id', 'ticker', 'issuer_id', 'risk_chain'],
            dtypes=['object']*4, index=list(range(77)), data=universe),
        returns=dict(type='dataframe', index_kind='DatetimeIndex', columns=[f'T{i:03}' for i in range(77)],
            dtypes=['float64']*77, index=[day+'T00:00:00' for day in days],
            data=[[i/10000. for i in range(77)] for _ in days]), **flags)
    return dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1', panel=inner, **flags)


class PreparationTests(unittest.TestCase):
    def test_full_ticker_projection_without_reordering_saved_values(self):
        document = panel_fixture()
        before = deepcopy(document)
        result = module.project_panel(document, dict(path='/panel', sha256='b'*64))
        self.assertEqual(document, before)
        self.assertEqual(result['universe'][0]['ticker'], 'T076')
        self.assertEqual(result['returns'][0][-1], .0076)
        self.assertEqual(len(result['dates']), 126)

    def test_date_dtype_and_authority_fail_closed(self):
        for mutate in (
            lambda d: d['panel']['returns']['index'].__setitem__(0, '2025-01-01junkT00:00:00'),
            lambda d: d['panel']['returns']['data'][0].__setitem__(0, True),
            lambda d: d['panel']['returns']['dtypes'].__setitem__(0, 'object'),
            lambda d: d.__setitem__('point_in_time_verified', True),
            lambda d: d['panel']['universe']['index'].__setitem__(0, -1),
        ):
            document = panel_fixture()
            mutate(document)
            with self.assertRaises(ValueError):
                module.project_panel(document, dict(path='/panel', sha256='b'*64))

    def test_duplicate_json_nonfinite_and_source_conflict(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError):
                module.strict_json(raw)
        with self.assertRaises(ValueError):
            module.merge_sources({'x':'a'*64}, {'x':'b'*64})

    def test_create_only_and_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            reference = module.write_new(path, {'old': True})
            with self.assertRaises(FileExistsError):
                module.write_new(path, {'replacement': True})
            self.assertEqual(module.strict_json(path.read_bytes()), {'old':True})
            path.write_text('{}')
            with self.assertRaises(ValueError):
                module.guard({str(path): reference['sha256']})


if __name__ == '__main__':
    unittest.main()
