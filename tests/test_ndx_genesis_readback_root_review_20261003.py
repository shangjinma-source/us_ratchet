"""Independent adverse cases for the new genesis receipt; no actual publication."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from scripts import ndx_gap_monthly_policy_history_input_readback_20261003 as reader

spec = importlib.util.spec_from_file_location('genesis_fixture', Path(__file__).with_name('test_ndx_gap_monthly_policy_history_input_readback_20261003.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class IndependentReview(unittest.TestCase):
    def test_observed_flag_and_october_coordinate_cannot_be_promoted(self):
        for attack in ('observed_eligibility', 'observed_index', 'october_first', 'october_count_bool'):
            docs, refs, raw = fixture.fixture()
            if attack == 'observed_eligibility':
                docs['frontier']['known_accounted_rows'][0]['eligibility_reverified'] = True
            elif attack == 'observed_index':
                docs['frontier']['known_accounted_rows'][0]['parent_session_index'] = False
            elif attack == 'october_first':
                docs['policy']['projection']['months'][-1]['first_observed_session'] = '2026-10-01'
            else:
                docs['policy']['projection']['months'][-1]['observed_count'] = False
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                reader.inspect(docs, refs, raw)

    def test_extra_parent_failure_and_source_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            refs = {}
            for role, names in (('policy', ('started.json', 'policy.json', 'publication.json')), ('frontier', ('started.json', 'frontier.json', 'publication.json'))):
                folder = base / role
                folder.mkdir()
                for name in names:
                    (folder / name).write_bytes(b'{}')
                refs[role] = {'path': str(folder / (role + '.json')), 'sha256': reader.sha(b'{}')}
            reader.namespaces(refs)
            (base / 'policy' / 'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                reader.namespaces(refs)
            source = base / 'raw.csv'
            source.write_bytes(b'original')
            sources = {str(source): reader.sha(b'original')}
            reader.guard(sources)
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                reader.guard(sources)

    def test_full_raw_scope_and_original_row_numbers_are_retained(self):
        docs, refs, raw = fixture.fixture()
        original = copy.deepcopy((docs, refs, raw))
        result = reader.inspect(docs, refs, raw)
        self.assertEqual((docs, refs, raw), original)
        self.assertIsNone(result['first_actual_observed_session_by_month']['2026-10'])
        for ticker in ('QQQ', 'SPY'):
            detail = result['baseline_details'][ticker]
            self.assertEqual(detail['full_csv_sha256'], reader.sha(raw[ticker]))
            self.assertEqual([r['original_data_row_index'] for r in detail['required_rows']], list(range(1, 66)))
            self.assertFalse(detail['price_values_validated'])
        for flag in reader.FLAGS:
            self.assertIs(result[flag], False)


if __name__ == '__main__':
    unittest.main()
