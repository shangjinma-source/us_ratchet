"""Exercise existing publication cases against the candidate resolver."""
from datetime import datetime
import test_strategy_account_monthly_release as original_tests
from data import strategy_account_monthly_release_replayed_v1 as candidate


class ReplayedMonthlyTests(original_tests.MonthlyReleaseTests):
    def setUp(self):
        super().setUp()
        candidate._REPLAY_CACHE.entries.clear()

    def resolve(self, now='2026-12-01T15:00:00+00:00', account_state=None):
        digest = self.put('registry.json', self.registry)
        arguments = dict(root=self.root, registry_path='registry.json',
            registry_sha256=digest, clock=lambda: datetime.fromisoformat(now),
            account_state=account_state)
        cold = candidate.resolve_monthly_runtime(**arguments)
        self.assertEqual(candidate.resolve_monthly_runtime(**arguments), cold)
        return cold

    def coverage(self, state):
        return candidate.validate_account_identity_coverage(self.root, self.entry, state)

    def test_source_mutation_after_successful_cached_resolution(self):
        self.resolve()
        (self.root / 'published/manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            self.resolve()
