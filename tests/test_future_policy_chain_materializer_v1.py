"""Structural preparation only; no production builder or market request."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from data.strategy_future_policy_chain_materializer_v1 import (
    materialize_future_policy_chain, PARENTS)


class FuturePolicyChainTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        workspace = Path(__file__).resolve().parents[1]
        receipt = json.loads((workspace/'tmp/current_upgrade_v3_materialized_20261020_v1.json').read_bytes())
        self.arguments = dict(
            root=self.root, server_reference=receipt['proposed_server_reference'],
            upgrade_reference=receipt['proposed_server_upgrade_reference'],
            application_reference=self.copy(workspace, 'research_contracts/daily_domain_release_20261020_v2_reviewed/application.json'),
            release_reference=self.copy(workspace, 'research_contracts/daily_domain_release_20261020_v2_reviewed/policy-release.json'),
            output_directory='candidate', clock=lambda: datetime(2026, 10, 20, 15, tzinfo=timezone.utc),
            validate_sources=lambda: None)
        reference = self.arguments['server_reference']
        while True:
            self.copy(workspace, reference['path'])
            document = json.loads((self.root/reference['path']).read_bytes())
            for path in document.get('source_pins', {}):
                self.copy(workspace, path)
            if document['schema'] not in PARENTS:
                break
            reference = document[PARENTS[document['schema']]]
        self.copy(workspace, self.arguments['upgrade_reference']['path'])
        self.copy(workspace, document['daily_configuration']['path'])
        daily = json.loads((self.root/document['daily_configuration']['path']).read_bytes())
        self.copy(workspace, daily['evidence']['configuration_path'])
        application = json.loads((self.root/self.arguments['application_reference']['path']).read_bytes())
        self.copy(workspace, application['calendar']['path'])
        for pin in application['code_pins']:
            self.copy(workspace, pin['path'])
        release = json.loads((self.root/self.arguments['release_reference']['path']).read_bytes())
        for field in ('code_sha256', 'research_evidence_sha256'):
            for path in release[field]:
                self.copy(workspace, path)

    def copy(self, source, relative):
        raw = (source/relative).read_bytes()
        destination = self.root/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        return dict(path=relative, sha256=sha256(raw).hexdigest())

    def test_only_daily_and_parent_refs_change(self):
        result = materialize_future_policy_chain(**self.arguments)
        old = self.arguments['server_reference']
        new = result['server_reference']
        for schema, parent in PARENTS.items():
            before = json.loads((self.root/old['path']).read_bytes())
            after = json.loads((self.root/new['path']).read_bytes())
            old, new = before.pop(parent), after.pop(parent)
            self.assertEqual(before, after)
        before = json.loads((self.root/old['path']).read_bytes())
        after = json.loads((self.root/new['path']).read_bytes())
        before.pop('daily_configuration')
        daily = json.loads((self.root/after.pop('daily_configuration')['path']).read_bytes())
        self.assertEqual(before, after)
        self.assertTrue(daily['policy_execution_enabled'])
        self.assertEqual(result['valid_from'], '2026-10-21T13:30:00+00:00')
        with self.assertRaises(Exception):
            materialize_future_policy_chain(**self.arguments)

    def test_binding_and_final_drift_fail_closed(self):
        bad = dict(self.arguments, upgrade_reference=dict(path='wrong', sha256='0'*64))
        with self.assertRaisesRegex(Exception, 'FRESH_UPGRADE'):
            materialize_future_policy_chain(**bad)
        calls = []
        def drift():
            calls.append(1)
            if len(calls) == 2:
                (self.root/self.arguments['release_reference']['path']).write_bytes(b'{}')
        with self.assertRaisesRegex(Exception, 'SOURCE_CHANGED'):
            materialize_future_policy_chain(**dict(self.arguments, validate_sources=drift))
        self.assertFalse((self.root/'candidate').exists())
        self.assertEqual(len(list(self.root.glob('.candidate.preparing-*/failed.json'))), 1)
