"""Same live reader across opening, isolated fixtures only; no production clock edits."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import PROFILE_ID, VERSION
from data.strategy_daily_domain_policy_reader_v2 import ExplicitDomainPolicyReviewReaderV2, REVIEW_SOURCES
import test_strategy_daily_dynamic_factory_v5 as fixtures

ROOT = Path(__file__).resolve().parents[1]


class OpeningTransitionTests(unittest.TestCase):
    def test_premarket_wait_does_not_latch_after_open_or_rewrite_source(self):
        with TemporaryDirectory() as folder:
            c, root, source, run, calls = fixtures.MigrationFactoryTests().setup(folder)
            c.clock[0] = datetime.fromisoformat('2026-11-03T14:29:00+00:00')
            self.assertEqual(run()['status'], 'DYNAMIC_DOMAIN_PACKET_SAVED')
            source_raw = canonical(source)
            (root/'source-reader.json').write_bytes(source_raw)
            source_ref = dict(path='source-reader.json', sha256=sha256(source_raw).hexdigest())
            pins = []
            for name in sorted(REVIEW_SOURCES):
                body = (ROOT/name).read_bytes()
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                pins.append(dict(path=name, sha256=sha256(body).hexdigest()))
            release_document = json.loads((root/'release.json').read_bytes())
            self.assertTrue(release_document['fixture_only'])
            # The source fixture extends its one-session calendar for rolling
            # capture; its isolated policy must bind that extended calendar too.
            release_document['calendar_sha256'] = source['calendar']['sha256']
            release = canonical(release_document)
            (root/'release.json').write_bytes(release)
            config = dict(schema='SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1', authorized=True,
                scope='COMPLETE_CURRENT_SESSION_DOMAIN', account_id=c.store.read()['account_id'],
                selector_profile=PROFILE_ID, selection_method=VERSION, continuous_iterations=32,
                authorization_id='FIXTURE_ONLY_OPEN_TRANSITION', authorization_source='ISOLATED_TEST',
                rule_selection_role='IMPLEMENTER_RECOMMENDATION_REVIEWED',
                authorized_at='2026-11-02T14:00:00Z', valid_from='2026-11-02T14:00:00Z',
                valid_until='2026-11-04T21:00:00Z', source_configuration=source_ref,
                calendar=source['calendar'], release=dict(path='release.json',sha256=sha256(release).hexdigest()),
                code_pins=pins, archive_root='policy-archive', fixture_only=True)
            raw = canonical(config)
            (root/'policy-review.json').write_bytes(raw)
            reader = ExplicitDomainPolicyReviewReaderV2(root=root, configuration_path=source_ref['path'],
                configuration_sha256=source_ref['sha256'], archive_root=None,
                review_configuration_path='policy-review.json', review_configuration_sha256=sha256(raw).hexdigest(),
                clock=lambda:c.clock[0])
            before = c.store.path.read_bytes()
            terminal = root/source['runs_root']/'2026-11-03'/'terminal.json'
            terminal_before = terminal.read_bytes()
            wait = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(wait['reason'], 'WAIT_POLICY_REVIEW_SESSION')
            self.assertIsNone(wait['signal'])
            self.assertFalse((root/'policy-archive').exists())
            c.clock[0] = datetime.fromisoformat('2026-11-03T14:30:00+00:00')
            opened = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(opened['status'], 'DAILY_SIGNAL_READY')
            self.assertTrue(Path(opened['evidence_archive']['complete_path']).is_file())
            c.clock[0] = datetime.fromisoformat('2026-11-03T21:00:00+00:00')
            closed = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(closed['reason'], 'WAIT_NEXT_SESSION')
            self.assertIsNone(closed['signal'])
            self.assertEqual(calls, ['BBB'])
            self.assertEqual(c.store.path.read_bytes(), before)
            self.assertEqual(terminal.read_bytes(), terminal_before)


if __name__ == '__main__':
    unittest.main()
