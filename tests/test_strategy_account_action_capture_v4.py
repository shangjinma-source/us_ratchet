from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.strategy_account_action_capture_v4 import StrategyAccountActionCaptureV4
import test_strategy_account_evidence_provider as fixtures


class CaptureV4Tests(unittest.TestCase):
    def fixture(self, folder):
        provider, state, now, root = fixtures.ProviderTests().fixture(folder)
        old = provider.actions
        def rss():
            response = old.rss_fetch()
            response['body'] = response['body'].replace(
                b'<channel>', b'<channel><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate>')
            return response
        provider.actions = StrategyAccountActionCaptureV4(
            fetch=old.fetch, rss_fetch=rss, clock=old.clock)
        return provider, state, now, root

    def test_actual_provider_and_original_review_timing_closure(self):
        from data.strategy_account_target_inputs import build_target_inputs
        with tempfile.TemporaryDirectory() as folder:
            provider, state, now, root = self.fixture(folder)
            result = provider(state)
            inputs = build_target_inputs(state=state, now=now[0].isoformat(),
                maximum_mark_age_seconds=120,
                **{key: value for key, value in result.items() if key != 'limits'})
            self.assertEqual(inputs['status'], 'INPUTS_READY_NOT_EXECUTED')
            complete = json.loads(next((Path(folder)/'capture').glob('*/actions/complete-v4.json')).read_bytes())
            path = complete['rss_timing_path']
            package = result['source_package']
            raw = package['files'][path]
            self.assertEqual(package['source_hashes'][path], sha256(raw).hexdigest())
            timing = json.loads(raw)
            self.assertEqual(package['source_hashes'][timing['original_rss_receipt_path']],
                             timing['original_rss_receipt_sha256'])
            self.assertFalse(timing['raw_modified'])

    def test_timing_write_failure_or_final_expiry_never_returns(self):
        import os
        original_fsync = os.fsync
        for mode in ('disk', 'expiry'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                provider, state, now, root = self.fixture(folder)
                def fsync(descriptor):
                    original_fsync(descriptor)
                    # Original V3 complete has already been sealed at timing persistence.
                    if list((Path(folder)/'capture').glob('*/actions/complete.json')):
                        if mode == 'disk':
                            raise OSError('isolated disk failure')
                        now[0] += timedelta(seconds=121)
                with patch('data.strategy_account_action_capture_v4.os.fsync', fsync):
                    with self.assertRaises(Exception):
                        provider(state)
                self.assertFalse(list((Path(folder)/'capture').glob('*/actions/complete-v4.json')))

    def test_explicit_transport_configuration_and_source_gate(self):
        from data.strategy_upgrade_action_transport_v4 import (
            SOURCES, materialize_transport_configuration, PinnedUpgradeActionTransportV4)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = Path(__file__).resolve().parents[1]
            for name in SOURCES:
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((workspace/name).read_bytes())
            ref = materialize_transport_configuration(root=root, relative_path='transport.json', authorized=True)
            transport = PinnedUpgradeActionTransportV4(root=root,
                configuration_path=ref['path'], configuration_sha256=ref['sha256'])
            transport.validate()
            (root/'data/strategy_rss_verified_transport_v1.py').write_bytes(b'changed')
            with self.assertRaisesRegex(Exception, 'SOURCE_CHANGED'):
                transport.validate()
