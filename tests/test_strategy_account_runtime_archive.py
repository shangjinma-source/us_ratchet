"""Synthetic configuration lookup only; no production files or account IO."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import RUNTIME_PATHS
from data.strategy_account_runtime_archive import configuration_for_target


class RuntimeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.configuration = dict(schema='REAL_STRATEGY_RUNTIME_V1', target_month='2026-10',
            training_manifest='old-training.json', training_sha256='1'*64,
            training_closed_at='2026-09-30T16:00:00-04:00', identity_manifest='identity.json',
            identity_sha256='2'*64, runtime_pins={name:'3'*64 for name in RUNTIME_PATHS})
        binding = dict(documents={'training_manifest':'old-training.json'},
                       source_hashes={'old-training.json':'1'*64, 'identity.json':'2'*64})
        decision_payload = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest())
        payload = dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1', target_month='2026-10',
            decision=dict(payload=decision_payload, decision_id=sha256(canonical(decision_payload)).hexdigest()),
            runtime_pins=deepcopy(self.configuration['runtime_pins']))
        self.target = dict(payload=payload, target_id=sha256(canonical(payload)).hexdigest())
        self.archive = dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1', entries=[])
        self.add('old.json', self.configuration)

    def put(self, path, value):
        raw = canonical(value)
        (self.root/path).write_bytes(raw)
        return sha256(raw).hexdigest()

    def add(self, path, configuration):
        self.archive['entries'].append(dict(configuration_path=path,
            configuration_sha256=self.put(path,configuration)))

    def resolve(self):
        digest = self.put('archive.json', self.archive)
        return configuration_for_target(root=self.root,archive_path='archive.json',
                                        archive_sha256=digest,target=self.target)

    def test_old_target_uses_original_despite_same_month_and_later_releases(self):
        self.add('same-month.json',dict(self.configuration,training_sha256='4'*64))
        self.add('next-month.json',dict(self.configuration,target_month='2026-11'))
        self.put('archive.json',self.archive)
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        target_before = deepcopy(self.target)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            result = self.resolve()
        self.assertEqual(result,self.configuration)
        self.assertEqual(self.target,target_before)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertFalse((self.root/'data').exists())
        result['runtime_pins'].clear()
        self.assertEqual(self.resolve(),self.configuration)

    def test_each_binding_component_is_required(self):
        for field,value in [('target_month','2026-11'),('training_manifest','other.json'),
                            ('training_sha256','4'*64),('runtime_pins',{p:'4'*64 for p in RUNTIME_PATHS})]:
            with self.subTest(field=field):
                self.archive['entries'] = []
                self.add('changed.json',dict(self.configuration,**{field:value}))
                with self.assertRaisesRegex(ValueError,'TARGET_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
                    self.resolve()

    def test_duplicate_matching_entries_are_refused_even_identical(self):
        self.add('duplicate.json',self.configuration)
        with self.assertRaisesRegex(ValueError,'TARGET_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.resolve()

    def test_changed_identity_configuration_does_not_replace_original(self):
        self.add('changed-identity.json',dict(self.configuration,identity_sha256='5'*64))
        self.assertEqual(self.resolve(),self.configuration)

    def test_only_replacement_identity_configuration_is_refused(self):
        for changed in (dict(identity_sha256='5'*64),
                        dict(identity_manifest='replacement-identity.json')):
            with self.subTest(changed=changed):
                self.archive['entries'] = []
                self.add('changed-identity.json',dict(self.configuration,**changed))
                with self.assertRaisesRegex(ValueError,'TARGET_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
                    self.resolve()

    def test_archive_and_configuration_hash_changes_refused(self):
        digest = self.put('archive.json',self.archive)
        with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
            configuration_for_target(root=self.root,archive_path='archive.json',archive_sha256='0'*64,target=self.target)
        (self.root/'old.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
            self.resolve()

    def test_unsafe_descriptor_path_rejected(self):
        for path in ('../escape.json','C:/escape.json','a\\bad.json'):
            self.archive['entries'][0]['configuration_path'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.resolve()

    def test_current_registry_cannot_substitute_for_archive(self):
        self.archive['schema'] = 'REAL_STRATEGY_MONTHLY_RELEASES_V1'
        with self.assertRaisesRegex(ValueError,'INVALID_RUNTIME_ARCHIVE'):
            self.resolve()

    def test_target_hash_layers_verified(self):
        original = deepcopy(self.target)
        for layer in ('target','decision','input'):
            self.target = deepcopy(original)
            self.target['payload']['decision']['payload']['input_binding']['changed'] = True
            if layer in ('decision','input'):
                if layer == 'input':
                    decision = self.target['payload']['decision']
                    decision['decision_id'] = sha256(canonical(decision['payload'])).hexdigest()
                self.target['target_id'] = sha256(canonical(self.target['payload'])).hexdigest()
            with self.subTest(layer=layer), self.assertRaisesRegex(ValueError, 'TARGET_.*MISMATCH'):
                self.resolve()

    def test_malformed_configuration_pins_refused(self):
        self.archive['entries'] = []
        self.add('bad.json',dict(self.configuration,runtime_pins={}))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_RUNTIME_PINS_REQUIRED'):
            self.resolve()

    def test_link_and_duplicate_json_rejected(self):
        digest = self.put('archive.json',self.archive)
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'ARCHIVE_LINK_REFUSED'):
                configuration_for_target(root=self.root,archive_path='archive.json',archive_sha256=digest,target=self.target)
        raw = b'{"schema":"a","schema":"b","entries":[]}'
        (self.root/'archive.json').write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_DUPLICATE_JSON_FIELD'):
            configuration_for_target(root=self.root,archive_path='archive.json',archive_sha256=sha256(raw).hexdigest(),target=self.target)


if __name__ == '__main__':
    unittest.main()
