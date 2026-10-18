"""Read existing immutable evidence; never replay fitting or account economics."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_modern_new_cash_inputs_research as module


class ModernInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((module.ROOT / module.BOUND['inputs'][0]).read_bytes())
        cls.publication = json.loads((module.ROOT / module.BOUND['publication'][0]).read_bytes())
        cls.audit = json.loads((module.ROOT / module.BOUND['readback'][0]).read_bytes())
        cls.refs = {k: dict(path=str(module.ROOT / p), sha256=h) for k, (p, h) in module.BOUND.items()}
        cls.result = module.load_historical_frozen_states()

    def test_full_original_coordinates_targets_and_identity_pointers(self):
        result = self.result
        self.assertEqual(result['counts'], dict(coordinates=48, lanes=8, tracks=16, blocked_tracks=8, prepared_tracks=8))
        self.assertEqual(result['coordinates_preserved'], self.document['inputs']['outer_coordinate_rows_preserved'])
        ks = set()
        for lane in result['lanes']:
            original = self.document['inputs']['rows'][lane['lane_index']]
            self.assertEqual(lane['source_slots'], original['source_slots'])
            self.assertEqual(lane['exact_quote_conversion_evidence'], original['exact_quote_conversion_evidence'])
            for decision in lane['decisions']:
                targets = module.pointer(self.document, decision['targets_pointer'])
                self.assertEqual(len(targets), decision['target_count'])
                ks.add(len(targets))
                for security in decision['securities']:
                    sid = security['security_id']
                    identity = module.pointer(self.document, security['identity_pointer'])
                    self.assertEqual({k: security[k] for k in ('ticker', 'issuer_id', 'target_weight')}, targets[sid])
                    self.assertEqual(security['risk_chain'], identity['risk_chain'])
                for price in decision['prices']:
                    self.assertEqual(price['value'], module.pointer(self.document, price['account_matrix_pointer']))
                    quote = module.pointer(self.document, price['quote_projection_pointer'])
                    self.assertEqual(quote['json_pointer'], price['source_json_pointer'])
                    self.assertEqual(quote['exact'], price['exact'])
                    self.assertIsNone(price['price_available_at'])
        self.assertGreater(len(ks), 1)

    def test_original_raw_state_and_exact_session_no_later_replacement(self):
        for track in self.result['historical_execution_tracks']:
            self.assertEqual(len(track['historical_decision_states']), 0 if track['track_index'] < 8 else 6)
            for state in track['historical_decision_states']:
                raw = json.loads(Path(state['raw_reference']['path']).read_bytes())
                original = module.pointer(raw, state['state_pointer'])
                self.assertEqual(original, state['original_state_preserved'])
                self.assertEqual(original['session'], state['session'])
                if track['track'] == 'CONTINUOUS':
                    self.assertIsNone(state['risk_chains'])
                    self.assertIsNone(state['saved_account_marks'])
                    self.assertIsNone(state['conditional_original_risk_recheck'])

    def test_risk_original_math_matches_saved_whole_states(self):
        for track in self.result['historical_execution_tracks']:
            for state in track['historical_decision_states']:
                recheck = state['conditional_original_risk_recheck']
                if recheck is not None:
                    original = state['original_state_preserved']['risk']
                    self.assertEqual(recheck['result'], original)
        with self.assertRaises(ValueError):
            module.recheck_conditional_whole_lot_risk(shares={'SID': 1.5}, marks={'SID': 20.}, chains={'SID': 'same'})

    def test_no_admission_or_current_cash_from_positive_research(self):
        for key in module.FLAGS:
            self.assertIs(self.result[key], False)
        self.assertIsNone(self.result['current_account'])
        self.assertIsNone(self.result['current_new_money'])
        self.assertEqual(self.result['plan_rows'], [])
        self.assertTrue(self.result['blockers'])
        self.assertEqual(self.result['historical_execution_counts'], {'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK': 8, 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT': 8})

    def test_fixed_io_only_and_source_hash_failure_no_fallback(self):
        allowed = {str(module.ROOT / p) for p, _ in (*module.BOUND.values(), *module.EXECUTION_BOUND.values())}
        allowed.add(str(module.ROOT / module.RISK_PATH))
        allowed.update(str(module.ROOT / f'data/cache/research/multidecision_account_execution_20261003_v1/tracks/{i:02d}/raw_result.json') for i in range(8, 16))
        original_read = Path.read_bytes
        calls = []
        def read(path):
            calls.append(str(path))
            self.assertIn(str(path), allowed)
            return original_read(path)
        with patch.object(Path, 'read_bytes', read):
            module.load_historical_frozen_states()
        self.assertTrue(calls)
        def corrupted(path):
            raw = original_read(path)
            return raw + b' ' if str(path) == self.refs['inputs']['path'] else raw
        with patch.object(Path, 'read_bytes', corrupted), self.assertRaisesRegex(ValueError, 'Pinned source'):
            module.load_modern_new_cash_inputs()

    def test_original_blocked_coordinate_and_pointer_identity_cannot_be_repaired(self):
        for mode in ('blocked', 'identity', 'truncated'):
            document = deepcopy(self.document)
            if mode == 'blocked':
                document['inputs']['outer_coordinate_rows_preserved'][4]['evidence'] = None
            elif mode == 'identity':
                target = next(iter(document['inputs']['rows'][4]['original_targets_schedule'][0]['targets'].values()))
                target['ticker'] = 'NOT_THE_ORIGINAL_TICKER'
            else:
                document['inputs']['rows'][4]['original_targets_schedule'].pop(0)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module._project(document, self.publication, self.audit, self.refs)

    def test_failure_and_namespace_drift_rechecked_no_success_cache(self):
        original_namespace = module._namespace
        calls = []
        def namespace(folder, expected):
            calls.append(folder)
            if len(calls) == 3:
                raise ValueError('Concurrent namespace drift')
            original_namespace(folder, expected)
        with patch.object(module, '_namespace', namespace), self.assertRaisesRegex(ValueError, 'Concurrent namespace'):
            module.load_modern_new_cash_inputs()
        original_exists = Path.exists
        failure = Path(self.refs['inputs']['path']).parent / 'failure.json'
        with patch.object(Path, 'exists', lambda p: True if p == failure else original_exists(p)), self.assertRaisesRegex(ValueError, 'Failed saved'):
            module.load_modern_new_cash_inputs()
        original_read = Path.read_bytes
        risk_path = module.ROOT / module.RISK_PATH
        input_path = Path(self.refs['inputs']['path'])
        input_reads = 0
        def late_risk_drift(path):
            nonlocal input_reads
            raw = original_read(path)
            if path == input_path:
                input_reads += 1
            if path == risk_path and input_reads >= 3:
                return raw + b' '
            return raw
        with patch.object(Path, 'read_bytes', late_risk_drift), self.assertRaisesRegex(ValueError, 'Pinned source bytes changed'):
            module.load_historical_frozen_states()

    def test_duplicate_json_and_strict_authority(self):
        with self.assertRaises(ValueError):
            module.decode(b'{"a":1,"a":2}')
        for value in (0, True, None):
            document = deepcopy(self.document)
            document['execution_authorized'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                module._project(document, self.publication, self.audit, self.refs)


if __name__ == '__main__':
    unittest.main()
