"""Real temporary store -> service -> admitted range; no production writes."""
import json
import unittest
from unittest.mock import patch

import test_current_research_observation_registry as fixtures
from data.current_research_observation_registry import DEFAULT_REGISTRY
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_paper_store import ResearchPaperStore


class ObservationServiceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        plan = self.fixture.state['plan']
        self.account_id = 'paper-' + plan['plan_id'][:24]
        self.directory = self.root / 'paper'
        self.store = ResearchPaperStore(self.directory)
        self.state = self.store.create(self.account_id, plan)
        self.fixture.bundle['account_id'] = self.account_id
        self.fixture.save()
        self.registry = self.root / DEFAULT_REGISTRY
        self.registry.parent.mkdir(parents=True)
        self.registry.write_bytes((self.root / 'registry.json').read_bytes())
        self.service = CurrentResearchPaperService(
            root=self.root, directory=self.directory, clock=lambda: self.fixture.now)

    def test_registered_complete_bar_reaches_service_without_inferred_fill(self):
        database = self.directory / 'research_paper.sqlite3'
        before = database.read_bytes()
        response = self.service.review(self.account_id)
        self.assertEqual(response['market_review']['orders'][0]['observed_touch'], 'YES')
        self.assertEqual(response['market_review']['generated_fill_count'], 0)
        self.assertTrue(response['market_review']['additional_observation_admission_verified_by_helper'])
        self.assertEqual(response['market_review']['revision'], response['review']['revision'])
        self.assertEqual(database.read_bytes(), before)

    def test_invalid_admission_never_falls_back_to_unknown(self):
        registry = json.loads(self.registry.read_bytes())
        registry['entries'][0]['sha256'] = '0' * 64
        self.registry.write_text(json.dumps(registry))
        with patch('data.current_research_paper_service.review_plan_bound_observations',
                   side_effect=AssertionError('invalid admission must not fall back')):
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
                self.service.review(self.account_id)

    def test_absent_registry_retains_explicit_unknown(self):
        self.registry.unlink()
        response = self.service.review(self.account_id)
        self.assertEqual(response['market_review']['orders'][0]['observed_touch'], 'UNKNOWN')
        self.assertEqual(response['market_review']['generated_fill_count'], 0)


if __name__ == '__main__':
    unittest.main()
