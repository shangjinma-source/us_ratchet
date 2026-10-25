from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from scripts.finalize_registered_paper_runtime import run
import test_run_current_quantity_v2_simulation as runtime_fixture


class AdapterTests(unittest.TestCase):
    setUpClass = classmethod(lambda cls: runtime_fixture.RuntimeTests.setUpClass())
    tearDownClass = classmethod(lambda cls: runtime_fixture.RuntimeTests.tearDownClass())

    def prepare(self, folder):
        request, args, transports, calls = runtime_fixture.RuntimeTests.setup(self, folder)
        current = args['store'].read(args['simulation_id'])
        parameters = dict(config_path=request['config_path'], config_sha256=request['config_sha256'],
            account_id=current['simulation']['origin']['ledger']['account_id'],
            expected_revision=current['revision'], evaluation_end='2026-10-15',
            clock=args['clock'], transports=transports)
        return parameters, args, calls

    def test_real_providers_finalize_without_new_decisions(self):
        with TemporaryDirectory() as folder:
            parameters, args, calls = self.prepare(folder)
            before = {str(p): p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
            with patch('urllib.request.urlopen', side_effect=AssertionError('offline preflight')):
                self.assertEqual(run(**parameters)['status'], 'SETTLEMENT_PREFLIGHT_ONLY')
            self.assertEqual(before, {str(p): p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()})
            result = run(**parameters, execute=True)
            self.assertEqual(result['settlement_status'], 'FINALIZED_DECLARED_END')
            self.assertEqual(result['simulation']['valuation']['records'][-1]['status'], 'COMPLETE')
            self.assertEqual(calls[1], [])
            self.assertEqual(result['new_decisions'], 0)
            parameters['expected_revision'] = result['revision']
            counts = tuple(map(len, calls))
            self.assertEqual(run(**parameters, execute=True)['settlement_status'], 'ALREADY_FINALIZED')
            self.assertEqual(counts, tuple(map(len, calls)))

    def test_wrong_account_revision_and_before_close_do_not_capture(self):
        for mode in ('account', 'revision', 'clock'):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                parameters, args, calls = self.prepare(folder)
                before = args['store'].path.read_bytes()
                if mode == 'account': parameters['account_id'] = 'other'
                if mode == 'revision': parameters['expected_revision'] = 'other'
                if mode == 'clock': parameters['clock'] = lambda: datetime.fromisoformat('2026-10-15T15:59:00-04:00')
                with self.assertRaises(ValueError): run(**parameters, execute=True)
                self.assertEqual(before, args['store'].path.read_bytes())
                self.assertEqual(calls, ([], [], []))

    def test_incomplete_minutes_remain_unknown_without_repeat_capture(self):
        with TemporaryDirectory() as folder:
            parameters, args, calls = self.prepare(folder)
            original = parameters['transports']['minutes']
            def incomplete(url):
                value = json.loads(original(url))
                chart = value['chart']['result'][0]
                chart['timestamp'].pop(len(chart['timestamp']) // 2)
                for values in chart['indicators']['quote'][0].values():
                    values.pop(len(values) // 2)
                for field in ('open', 'high', 'low', 'close'):
                    chart['indicators']['quote'][0][field] = [10000] * len(chart['timestamp'])
                return json.dumps(value).encode()
            parameters['transports'] = dict(parameters['transports'], minutes=incomplete)
            result = run(**parameters, execute=True)
            self.assertEqual(result['settlement_status'], 'UNKNOWN_UNRESOLVED_ORDERS')
            self.assertEqual(result['simulation']['valuation']['records'], [])
            self.assertTrue(all(not order['closed'] for order in result['simulation']['chain']['ledger']['orders'].values()))
            parameters['expected_revision'] = result['revision']
            counts = tuple(map(len, calls))
            again = run(**parameters, execute=True)
            self.assertEqual(again['settlement_status'], 'UNKNOWN_UNRESOLVED_ORDERS')
            self.assertEqual(counts, tuple(map(len, calls)))
            self.assertEqual(calls[1], [])

    def test_known_fill_before_gap_is_preserved_but_no_close_nav_is_invented(self):
        with TemporaryDirectory() as folder:
            parameters, args, calls = self.prepare(folder)
            original = parameters['transports']['minutes']
            def later_gap(url):
                value = json.loads(original(url))
                chart = value['chart']['result'][0]
                chart['timestamp'].pop(len(chart['timestamp']) // 2)
                for values in chart['indicators']['quote'][0].values():
                    values.pop(len(values) // 2)
                return json.dumps(value).encode()
            parameters['transports'] = dict(parameters['transports'], minutes=later_gap)
            result = run(**parameters, execute=True)
            self.assertEqual(result['settlement_status'], 'BLOCKED_MISSING_CLOSE_EVIDENCE')
            self.assertEqual(result['simulation']['valuation']['records'], [])
            self.assertTrue(any(order['closed'] == 'FILLED' for order in result['simulation']['chain']['ledger']['orders'].values()))
            stored = args['store'].read(args['simulation_id'])
            self.assertEqual(stored['revision'], result['revision'])
            self.assertEqual(stored['simulation'], result['simulation'])
            self.assertEqual(calls[1], [])


if __name__ == '__main__': unittest.main()
