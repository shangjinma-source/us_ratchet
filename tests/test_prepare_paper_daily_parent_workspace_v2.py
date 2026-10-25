import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from scripts.prepare_paper_daily_parent_workspace_v2 import prepare


class ParentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.files = {
            'normalized.json': canonical(dict(histories={'S': dict(
                units={'currency': 'USD'}, source_reference='raw.json')})),
            'raw.json': canonical(dict(chart=dict(result=[dict(meta=dict(
                symbol='ABC', currency='USD', exchangeName='NMS', instrumentType='EQUITY'))]))),
        }

    def fixture(self):
        def save(name, raw):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return dict(path=name, sha256=sha256(raw).hexdigest())
        manifest = {name: save('archive/'+str(i)+'.bin', raw)
                    for i, (name, raw) in enumerate(self.files.items())}
        receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1', normalization_reviewed=True,
            unresolved_units=[], pending_rights=[], execution_session={'date': '2026-10-23'},
            normalized_inputs_path='normalized.json',
            source_sha256={name: sha256(raw).hexdigest() for name, raw in self.files.items()})
        packet = dict(receipt_reference=save('receipt.json', canonical(receipt)),
            manifest_reference=save('manifest.json', canonical(manifest)))
        return save('terminal.json', canonical(dict(status='DYNAMIC_DOMAIN_PACKET_SAVED',
            session='2026-10-23', packets={'S': packet})))

    def test_preserves_bytes_derives_identity_and_refuses_overwrite(self):
        terminal = self.fixture()
        result = prepare(root=self.root, terminal_reference=terminal, output='isolated')
        for name, raw in self.files.items():
            self.assertEqual((self.root/'isolated'/name).read_bytes(), raw)
        identity = json.loads((self.root/'isolated'/result['identities']['S']['path']).read_bytes())
        self.assertEqual(identity['review_status'], 'DERIVED_FROM_REVIEWED_PARENT')
        self.assertFalse(identity['new_identity_approval'])
        with self.assertRaisesRegex(ValueError, 'OUTPUT_MUST_BE_NEW'):
            prepare(root=self.root, terminal_reference=terminal, output='isolated')

    def test_tampered_archive_rejected_before_output(self):
        terminal = self.fixture()
        (self.root/'archive/0.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_CHANGED'):
            prepare(root=self.root, terminal_reference=terminal, output='isolated')
        self.assertFalse((self.root/'isolated').exists())

    def test_escaping_logical_name_rejected_before_output(self):
        self.files['../escaped.json'] = b'{}'
        terminal = self.fixture()
        with self.assertRaisesRegex(ValueError, 'LOGICAL_PATH'):
            prepare(root=self.root, terminal_reference=terminal, output='isolated')
        self.assertFalse((self.root/'isolated').exists())


if __name__ == '__main__':
    unittest.main()
