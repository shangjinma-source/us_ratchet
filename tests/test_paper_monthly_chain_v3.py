"""Actual producer/successor validation; network is forbidden after fixture setup."""
from datetime import datetime
from hashlib import sha256
import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from scripts.run_paper_monthly_chain_v3 import run, load_published_month
import test_materialize_paper_monthly_successor_v3 as successor_fixture


class MonthlyChainTests(unittest.TestCase):
    def setup_case(self, folder):
        root, args = successor_fixture.PaperSuccessorTests().setup_case(folder)
        complete = json.loads((root/args['complete_path']).read_bytes())
        binding = complete['binding']
        def reference(digest):
            matches = [p for p in root.rglob('*.json') if sha256(p.read_bytes()).hexdigest() == digest]
            self.assertEqual(len(matches), 1)
            return dict(path=matches[0].relative_to(root).as_posix(), sha256=digest)
        slot = dict(complete_path=args['complete_path'], expected_binding=binding,
            producer_inputs=dict(coordinator=reference(binding['coordinator_sha256']),
                bootstrap=reference(binding['bootstrap_sha256']),
                policy=dict(path=binding['policy_path'], sha256=binding['policy_sha256'])),
            runtime_descriptor=dict(path=args['descriptor_path'], sha256=args['descriptor_sha256']))
        policy = dict(schema='PAPER_MONTHLY_CHAIN_V3', authorization='SHARED_SEED_READ_ONLY_PAPER_SUCCESSORS',
                      first_month='2026-12', terminal_month='2027-01', seed=slot, output_root='paper-chain')
        raw = canonical(policy)
        (root/'chain-policy.json').write_bytes(raw)
        return root, dict(root=root, policy_reference=dict(path='chain-policy.json', sha256=sha256(raw).hexdigest()),
                          clock=args['clock'])

    def test_successor_wait_and_read_only_resolution(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                self.assertEqual(run(**args, target_month='2026-12')['status'], 'MONTHLY_PUBLICATION_VERIFIED')
                self.assertFalse((root/'paper-chain').exists())
                self.assertEqual(run(**args)['status'], 'SUCCESSOR_PLAN_PREFLIGHT')
                self.assertFalse((root/'paper-chain').exists())
                result = run(**args, execute=True)
                self.assertEqual(result['status'], 'WAITING_SESSION_CLOSE')
                self.assertEqual(result['target_month'], '2027-01')
                self.assertFalse((root/'paper-chain/2027-01/market').exists())
                self.assertEqual(run(**args, execute=True), result)
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(run(**args, target_month='2027-01', execute=True)['status'], 'WAIT_MONTHLY_PUBLICATION')
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                with self.assertRaisesRegex(ValueError, 'TARGET_OUTSIDE_STUDY'):
                    run(**args, target_month='2027-02')
                self.assertFalse((root/'data/strategy_account').exists())

    def test_missed_window_and_partial_output_do_not_recapture(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                run(**args, execute=True)
                args['clock'] = lambda:datetime.fromisoformat('2027-01-01T16:00:00+00:00')
                with self.assertRaisesRegex(ValueError, 'MARKET_PREPARATION_WINDOW_ELAPSED'):
                    run(**args, execute=True)
                market = root/'paper-chain/2027-01/market'
                self.assertFalse(market.exists())
                market.mkdir()
                (market/'started.json').write_bytes(b'{}')
                with self.assertRaisesRegex(ValueError, 'PARTIAL_OUTPUT_RECOVERY_REQUIRED'):
                    run(**args, execute=True)
                self.assertEqual((market/'started.json').read_bytes(), b'{}')

    def test_seed_and_derived_plan_tamper_rejected(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            run(**args, execute=True)
            (root/'paper-chain/2027-01/plan/boundary.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'SUCCESSOR_OUTPUT_CHANGED'):
                run(**args, execute=True)
            (root/'real-market/failed.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'FAILED_PRESERVED'):
                run(**args, target_month='2026-12')

    def test_missing_shared_seed_never_launches_duplicate_producer(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            policy_path = root/'chain-policy.json'
            policy = json.loads(policy_path.read_bytes())
            policy['seed']['complete_path'] = 'not-produced/complete.json'
            policy['seed']['expected_binding']['output_directory'] = 'not-produced'
            body = canonical(policy)
            policy_path.write_bytes(body)
            args['policy_reference']['sha256'] = sha256(body).hexdigest()
            args['clock'] = lambda:datetime.fromisoformat('2026-11-20T16:00:00+00:00')
            with patch('scripts.run_paper_monthly_chain_v3.produce', side_effect=AssertionError('DUPLICATE_PRODUCER')):
                self.assertEqual(run(**args, execute=True)['status'], 'WAIT_SHARED_SEED_COMPLETION')
                args['clock'] = lambda:datetime.fromisoformat('2026-12-01T16:00:00+00:00')
                with self.assertRaisesRegex(ValueError, 'SHARED_SEED_RECOVERY_REQUIRED'):
                    run(**args, execute=True)
            self.assertFalse((root/'not-produced').exists())

    def test_current_month_training_and_no_previous_month_fallback(self):
        from data.strategy_account_evidence_provider import REQUIRED_PINS
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            pins = {}
            for name in REQUIRED_PINS:
                body = (Path(__file__).resolve().parents[1]/name).read_bytes()
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                pins[name] = sha256(body).hexdigest()
            request = dict(args, runtime_pins=pins, output_root=root/'loaded-training')
            with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                loaded = load_published_month(**request)
                self.assertEqual(loaded['target_month'], '2026-12')
                self.assertEqual(load_published_month(**request)['registry_reference'], loaded['registry_reference'])
                run(**args, execute=True)
                request['clock'] = lambda:datetime.fromisoformat('2027-01-01T15:00:00+00:00')
                with self.assertRaisesRegex(ValueError, 'TRAINING_WAIT_MONTHLY_PUBLICATION'):
                    load_published_month(**request)
                self.assertFalse((root/'data/strategy_account').exists())

    def test_actual_successor_capture_publication_and_terminal_replay(self):
        from test_current_quantity_v2_monthly_known_source_review import evidence
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            run(**args, execute=True)
            chart = json.loads((root/'new/BBB.response.bin').read_bytes())
            item = chart['chart']['result'][0]
            item['meta']['longName'] = 'Beta Business Corporation'
            schedule = json.loads((root/'schedule.json').read_bytes())
            for row in schedule['sessions']:
                timestamp = int(datetime.fromisoformat(row['close_at']).timestamp())
                if item['timestamp'][-1] < timestamp and row['date'] <= '2026-12-31':
                    item['timestamp'].append(timestamp)
                    for values in item['indicators']['quote'][0].values():
                        values.append(values[-1] + 1)
            body = json.dumps(chart).encode()
            calls = []
            def fetch(url, **kwargs):
                calls.append('market')
                return dict(raw=body, http_status=200, final_url=url, response_headers={})
            def rss():
                calls.append('rss')
                return dict(status=200, headers={'Content-Type':'application/xml'},
                            body=evidence(date='Thu, 31 Dec 2026 21:30:00 GMT')['feed_raw'])
            args['clock'] = lambda:datetime.fromisoformat('2026-12-31T22:00:00+00:00')
            with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                result = run(**args, execute=True, transports=dict(fetch=fetch, rss_fetch=rss))
                self.assertEqual(result['status'], 'MARKET_PUBLICATION_READY_NOT_ACTIVATED')
                self.assertEqual(calls, ['market', 'rss'])
                args['clock'] = lambda:datetime.fromisoformat('2027-01-01T16:00:00+00:00')
                self.assertEqual(run(**args, execute=True)['status'], 'PAPER_MONTHLY_CHAIN_COMPLETE')
                self.assertEqual(run(**args, target_month='2027-01')['status'], 'MONTHLY_PUBLICATION_VERIFIED')
                self.assertEqual(calls, ['market', 'rss'])
                self.assertFalse((root/'data/strategy_account').exists())


if __name__ == '__main__':
    unittest.main()
