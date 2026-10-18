"""Independent adversarial checks against recorded primary/provider inputs."""
import copy
import json
from pathlib import Path
import unittest

from backtest import ndx_nominal_quote_reconstruction_research as nominal
from scripts import ndx_preference_nominal_quote_research as cli

ROOT = Path(__file__).resolve().parents[1]


class IndependentNominalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1'
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        cls.probe = next(row for row in manifest['probes'] if row['name'] == 'yahoo_avgo_through_received_daily_events')
        cls.raw = Path(cls.probe['response_path']).read_bytes()
        cls.data = json.loads(cls.raw)

    def run_probe(self, *, probe=None, raw=None):
        probe = self.probe if probe is None else probe
        return nominal.reconstruct_nominal_quote_ticker(raw=self.raw if raw is None else raw,
            ticker='AVGO', calendar=['2023-03-31', '2024-06-03'], request=probe['request'],
            received_at_utc=probe['received_at_utc'], quote_field_basis=nominal.BASIS)

    def test_old_324_session_request_received_in_2026_rejected(self):
        directory = ROOT / 'data/cache/research/preference_price_action_source_probe_20260912_v1'
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        probe = next(row for row in manifest['probes'] if row['name'] == 'yahoo_avgo_daily_and_events')
        with self.assertRaises(ValueError):
            self.run_probe(probe=probe, raw=Path(probe['response_path']).read_bytes())

    def test_blank_duplicate_period2_rejected(self):
        probe = copy.deepcopy(self.probe)
        probe['request']['url'] += '&period2='
        with self.assertRaises(ValueError):
            self.run_probe(probe=probe)

    def test_future_quote_rejected(self):
        value = copy.deepcopy(self.data)
        value['chart']['result'][0]['timestamp'][-1] = 4102444800
        with self.assertRaises(ValueError):
            self.run_probe(raw=json.dumps(value).encode())

    def test_future_split_rejected(self):
        value = copy.deepcopy(self.data)
        events = value['chart']['result'][0]['events']['splits']
        events['4102444800'] = dict(events['1721050200'], date=4102444800)
        with self.assertRaises(ValueError):
            self.run_probe(raw=json.dumps(value).encode())

    def test_ratio_conflict_and_duplicate_split_day_rejected(self):
        for duplicate in (False, True):
            value = copy.deepcopy(self.data)
            events = value['chart']['result'][0]['events']['splits']
            if duplicate:
                events['1721050201'] = dict(events['1721050200'], date=1721050201)
            else:
                events['1721050200']['splitRatio'] = '100:1'
            with self.assertRaises(ValueError):
                self.run_probe(raw=json.dumps(value).encode())

    def test_raw_duplicate_json_keys_rejected(self):
        raw = self.raw.replace(b'"chart":', b'"chart":{},"chart":', 1)
        with self.assertRaises(ValueError):
            self.run_probe(raw=raw)

    def test_adjclose_changes_cannot_change_output(self):
        value = copy.deepcopy(self.data)
        rows = value['chart']['result'][0]['indicators']['adjclose'][0]['adjclose']
        value['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'] = [99999] * len(rows)
        baseline = self.run_probe()
        mutated = self.run_probe(raw=json.dumps(value).encode())
        self.assertEqual(baseline['rows'], mutated['rows'])
        self.assertEqual([r['split_factor'] for r in mutated['rows']], [10., 10.])

    def test_real_four_times_295_and_exact_field_arithmetic(self):
        report = cli.build_report()
        self.assertEqual(report['total_rows'], 1180)
        for ticker, data in report['by_ticker'].items():
            expected = 10. if ticker == 'AVGO' else 1.
            self.assertEqual(len(data['rows']), 295)
            for row in data['rows']:
                self.assertEqual(row['split_factor'], expected)
                self.assertEqual(row['nominal_open'], row['quote_open'] * expected)
                self.assertEqual(row['nominal_close'], row['quote_close'] * expected)
            self.assertFalse(data['point_in_time_verified'])
            self.assertFalse(data['provider_price_identity_verified'])
        nominal.verify(report['source_hashes'])

    def test_conflicting_raw_source_binding_rejected(self):
        path = str(Path(self.probe['response_path']).resolve())
        with self.assertRaises(ValueError):
            nominal.build_nominal_quote_research(calendar=['2023-03-31'], probes={'AVGO': self.probe},
                quote_field_basis=nominal.BASIS, source_hashes={path: '0' * 64})


if __name__ == '__main__':
    unittest.main()
