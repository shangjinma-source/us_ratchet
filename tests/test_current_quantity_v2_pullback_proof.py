from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
from data.current_quantity_v2_pullback_entry import digest
from data.current_quantity_v2_pullback_proof import replay_frozen_pullback
from test_current_quantity_v2_pullback_cap_store import arguments


class FrozenPullbackProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        store = PullbackCapStore(Path(self.temp.name) / 'research.sqlite3',
            clock=lambda: '2026-10-15T09:32:30-04:00',
            max_history_rows=100, max_history_bytes=1000000)
        first = store.candidate(**arguments())
        self.initial_raw = arguments()['raw']
        self.initial = first['frozen_proof']
        self.raw = arguments(1, 1450)['raw']
        self.proof = store.candidate(**arguments(1, 1450))['frozen_proof']

    def replay(self, proof=None, now='2026-10-15T09:32:31-04:00'):
        return replay_frozen_pullback(self.raw, self.proof if proof is None else proof, now)

    def test_initial_and_prior_history_local_replay(self):
        first = replay_frozen_pullback(self.initial_raw, self.initial, '2026-10-15T09:32:31-04:00')
        result = self.replay()
        self.assertEqual(first['candidate']['limit_price'], result['candidate']['limit_price'])
        self.assertEqual(result['candidate'], self.proof['result']['candidate'])
        self.assertTrue(result['replay_receipt']['local_replay_verified'])
        self.assertFalse(result['replay_receipt']['prior_history_authenticated'])
        self.assertFalse(result['replay_receipt']['production_enabled'])

    def test_proof_tampering_and_recomputed_outer_digest(self):
        for mutate in (
            lambda p: p['parameters'].update(minimum_discount='1/10'),
            lambda p: p['parameters'].update(ticker='MU'),
            lambda p: p['prior_cap'].update(limit_price='1300'),
            lambda p: p.update(record_hash='0' * 64),
            lambda p: p.update(prior_record_hash='0' * 64),
            lambda p: p.update(candidate_digest='0' * 64),
            lambda p: p.update(raw_sha256='0' * 64),
            lambda p: p.update(kernel_version='other'),
        ):
            changed = deepcopy(self.proof)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.replay(changed)
            # Replay must validate bytes/computation/record, not merely a self-hash.
            changed['proof_digest'] = digest({k: v for k, v in changed.items() if k != 'proof_digest'})
            with self.assertRaises(ValueError):
                self.replay(changed)

    def test_raw_tampering_now_reversal_and_expiry(self):
        with self.assertRaisesRegex(ValueError, 'PROOF_RAW_HASH_MISMATCH'):
            replay_frozen_pullback(b'changed', self.proof, '2026-10-15T09:32:31-04:00')
        with self.assertRaisesRegex(ValueError, 'PROOF_TIME_REVERSED'):
            self.replay(now='2026-10-15T09:32:29-04:00')
        with self.assertRaisesRegex(ValueError, 'PROOF_EXPIRED'):
            self.replay(now='2026-10-15T09:34:00-04:00')
        with self.assertRaisesRegex(ValueError, 'AWARE_TIME_REQUIRED'):
            self.replay(now='2026-10-15T09:32:31')


if __name__ == '__main__':
    unittest.main()
