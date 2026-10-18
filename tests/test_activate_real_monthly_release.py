"""CLI integration uses a synthetic future fixture; no production writes."""
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

import test_review_prepare_real_monthly_release as fixtures
from core.strategy_account_ledger import canonical
from scripts.review_prepare_real_monthly_release import run
from scripts.activate_real_monthly_release import activate, SCRIPT_PATH
from data.strategy_account_release_activation import MonthlyReleaseActivation


class ActivateCommandTests(unittest.TestCase):
    def setUp(self):
        from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
        self.fixture = fixtures.ReviewPrepareTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        run(**self.fixture.arguments)
        source = Path(__file__).resolve().parents[1]
        pins = {}
        for name in ROLLING_SOURCE_PATHS | {SCRIPT_PATH}:
            raw = (source/name).read_bytes()
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        descriptor = {key:self.fixture.arguments[key] for key in
            ('registry_path','registry_sha256','archive_path','archive_sha256')}
        descriptor['source_pins'] = pins
        raw = canonical(descriptor)
        (self.root/'deployment.json').write_bytes(raw)
        self.arguments = dict(root=self.root,descriptor_path='deployment.json',
            descriptor_sha256=sha256(raw).hexdigest(),receipt_path='reviewed-package/ready.json',
            receipt_sha256=sha256((self.root/'reviewed-package/ready.json').read_bytes()).hexdigest(),
            expected_release_revision=0)

    def test_fixed_descriptor_actual_adoption_and_retry(self):
        now = self.fixture.now
        before = self.fixture.store.path.read_bytes()
        def fixture_service(**kwargs):
            return MonthlyReleaseActivation(**kwargs, clock=lambda:now)
        with patch('scripts.activate_real_monthly_release.MonthlyReleaseActivation', fixture_service):
            result = activate(**self.arguments)
            self.assertEqual(activate(**self.arguments), result)
        self.assertEqual(result['status'], 'MONTHLY_DATA_RELEASE_ADOPTED')
        self.assertEqual(result['release_revision'], 1)
        self.assertFalse(result['target_created'])
        self.assertEqual(self.fixture.store.path.read_bytes(), before)

    def test_descriptor_or_source_drift_blocks(self):
        (self.root/SCRIPT_PATH).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'DYNAMIC_SOURCE_CHANGED'):
            activate(**self.arguments)
        self.assertFalse((self.root/'data/strategy_account/active_monthly_releases.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
