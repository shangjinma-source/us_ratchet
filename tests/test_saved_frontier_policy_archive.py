"""Isolated archive lifecycle and failure tests; no optimizer or real account."""
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_ledger import canonical
import data.saved_frontier_policy_archive as archive
from test_saved_monthly_frontier_proposal import native_fixture, sign


def fixture():
    target = native_fixture(held=True)
    binding = target['payload']['decision']['payload']['input_binding']
    files = {name: ('synthetic exact bytes: ' + name).encode() for name in binding['source_hashes']}
    binding['source_hashes'] = {name: sha256(raw).hexdigest() for name, raw in files.items()}
    for mark in binding['marks'].values():
        mark['source_hashes'] = {name: binding['source_hashes'][name] for name in mark['source_references']}
    files['runtime-only.py'] = b'# synthetic retained runtime source\n'
    target['payload']['runtime_pins'] = {name: sha256(raw).hexdigest() for name, raw in files.items()}
    sign(target)
    return target, build_frontier_proposal(target=target), files


class SavedFrontierPolicyArchiveTests(unittest.TestCase):
    def setUp(self):
        self.allowed = Path(archive.__file__).resolve().parents[1] / 'tmp'
        self.allowed.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='frontier-archive-test-', dir=self.allowed)
        self.root = Path(self.temporary.name)
        self.target, self.proposal, self.files = fixture()

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, **overrides):
        arguments = dict(research_root=self.root, target=self.target, proposal=self.proposal,
                         source_files=self.files, enabled=True)
        arguments.update(overrides)
        return archive.archive_saved_frontier_policy(**arguments)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_default_disabled_does_not_validate_or_touch_filesystem(self):
        missing = self.root / 'missing'
        result = archive.archive_saved_frontier_policy(research_root=missing,
            target=None, proposal=None, source_files=None)
        self.assertEqual(result['status'], 'ISOLATED_ARCHIVE_DISABLED')
        self.assertFalse(missing.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_roundtrip_complete_union_idempotency_and_original_immutable(self):
        original = deepcopy((self.target, self.proposal, self.files))
        first = self.write()
        before = self.snapshot()
        second = self.write()
        self.assertEqual(first, second)
        self.assertEqual(before, self.snapshot())
        loaded = archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
        self.assertEqual(loaded['target'], self.target)
        self.assertEqual(loaded['proposal'], self.proposal)
        self.assertEqual(loaded['receipt']['source_sha256']['runtime-only.py'], sha256(self.files['runtime-only.py']).hexdigest())
        self.assertEqual(loaded['source_count'], 4)
        self.assertTrue(loaded['source_bytes_verified'])
        self.assertFalse(loaded['proposal']['source_bytes_verified'])
        for field in ('production_admitted', 'policy_execution_enabled', 'account_mutated',
                      'target_mutated', 'source_authenticity_verified', 'original_runtime_admitted'):
            self.assertFalse(loaded[field])
        self.assertEqual((self.target, self.proposal, self.files), original)

    def test_caller_source_mapping_change_cannot_replace_verified_snapshot_bytes(self):
        original_bytes = self.files['runtime-only.py']
        real_digest = archive.sha256
        changed = False
        def change_caller_mapping(raw):
            nonlocal changed
            result = real_digest(raw)
            if raw == original_bytes and not changed:
                self.files['runtime-only.py'] = b'concurrent unverified replacement'
                changed = True
            return result
        with patch.object(archive, 'sha256', side_effect=change_caller_mapping):
            result = self.write()
        self.assertTrue(changed)
        loaded = archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
        digest = loaded['receipt']['source_sha256']['runtime-only.py']
        self.assertEqual((Path(result['archive_path']) / 'sources' / (digest + '.bin')).read_bytes(), original_bytes)

    def test_missing_extra_changed_sources_and_runtime_pin_conflict_rejected_without_writes(self):
        variants = []
        for name in ('synthetic-prices.json', 'runtime-only.py'):
            changed = dict(self.files)
            changed.pop(name)
            variants.append(changed)
        variants += [dict(self.files, unexpected=b'new'), dict(self.files, **{'runtime-only.py': b'changed'})]
        for index, files in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.write(source_files=files)
            self.assertEqual(list(self.root.iterdir()), [])
        target = deepcopy(self.target)
        target['payload']['runtime_pins']['synthetic-prices.json'] = 'f' * 64
        sign(target)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SOURCE_PIN_CONFLICT'):
            self.write(target=target, proposal=build_frontier_proposal(target=target))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_proposal_resigning_and_each_native_identity_tamper_fail(self):
        for index in range(4):
            target, proposal = deepcopy(self.target), deepcopy(self.proposal)
            if index == 0:
                target['target_id'] = 'f' * 64
            elif index == 1:
                target['payload']['decision']['decision_id'] = 'f' * 64
                target['target_id'] = sha256(canonical(target['payload'])).hexdigest()
            elif index == 2:
                target['payload']['decision']['payload']['input_id'] = 'f' * 64
                target['payload']['decision']['decision_id'] = sha256(canonical(target['payload']['decision']['payload'])).hexdigest()
                target['target_id'] = sha256(canonical(target['payload'])).hexdigest()
            else:
                proposal['payload']['proposed_target_quantities']['B'] += 1
                proposal['proposal_id'] = sha256(canonical(proposal['payload'])).hexdigest()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.write(target=target, proposal=proposal)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_root_escape_logical_alias_and_target_id_path_rejected(self):
        for root in (self.allowed, self.allowed.parent, Path('tmp/relative'), self.root / '..' / self.root.name):
            with self.subTest(root=str(root)), self.assertRaises(ValueError):
                self.write(research_root=root)
        for name in ('../escape', '/absolute', 'a//b', 'A/../b', 'C:\\escape', 'SYNTHETIC-PRICES.JSON'):
            target = deepcopy(self.target)
            target['payload']['runtime_pins'][name] = sha256(b'extra').hexdigest()
            sign(target)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.write(target=target, proposal=build_frontier_proposal(target=target),
                           source_files=dict(self.files, **{name: b'extra'}))
        with self.assertRaises(ValueError):
            archive.read_saved_frontier_policy(research_root=self.root, target_id='../escape')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_root_or_blob_and_busy_writer_refused(self):
        link = self.root / 'alias'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not permit symlinks: ' + str(error))
        try:
            with self.assertRaises(ValueError):
                self.write(research_root=link)
        finally:
            link.unlink()
        lock = self.root / ('.lock-' + self.target['target_id'])
        lock.write_bytes(b'another writer')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_TARGET_BUSY'):
            self.write()
        self.assertEqual(lock.read_bytes(), b'another writer')
        lock.unlink()
        result = self.write()
        blob = next((Path(result['archive_path']) / 'sources').iterdir())
        original = blob.read_bytes()
        destination = self.root / 'external.bin'
        destination.write_bytes(original)
        blob.unlink()
        blob.symlink_to(destination)
        with self.assertRaises(ValueError):
            archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
        blob.unlink()
        blob.write_bytes(original)

    def test_existing_incomplete_or_changed_archive_never_repaired_or_overwritten(self):
        folder = self.root / self.target['target_id']
        folder.mkdir()
        (folder / 'incomplete').write_bytes(b'preserve me')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_UNEXPECTED_FILE'):
            self.write()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(any(self.root.glob('.lock-*')))

    def test_read_cumulative_source_budget_and_extra_directory_fail_early(self):
        folder = Path(self.write()['archive_path'])
        names = sorted(self.target['payload']['decision']['payload']['input_binding']['source_hashes'])
        first, second = (self.files[name] for name in names[:2])
        limit = len(first) + len(second) - 1
        self.assertLess(max(len(first), len(second)), limit)
        attempted = []
        real_read = archive._read
        def observe_read(path, **kwargs):
            if path.parent.name == 'sources':
                attempted.append(path.name)
            return real_read(path, **kwargs)
        with patch.object(archive, 'MAXIMUM_SOURCE_BYTES', limit), patch.object(
                archive, '_read', side_effect=observe_read), self.assertRaisesRegex(
                ValueError, 'ARCHIVE_FILE_BUDGET_OR_ALIAS'):
            archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
        self.assertEqual(attempted, [sha256(raw).hexdigest() + '.bin' for raw in (first, second)])
        (folder / 'unexpected').mkdir()
        (folder / 'unexpected' / 'junk').write_bytes(b'unexpected')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_UNEXPECTED_DIRECTORY'):
            archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])

    def test_write_and_publish_failures_leave_only_unreadable_pending(self):
        real_write = archive._write
        def failure(path, raw):
            if path.name == 'proposal.json':
                raise OSError('injected write failure')
            real_write(path, raw)
        with patch.object(archive, '_write', side_effect=failure), self.assertRaises(OSError):
            self.write()
        self.assertFalse((self.root / self.target['target_id']).exists())
        self.assertTrue(any(self.root.glob('.pending-*')))
        self.assertFalse(any(self.root.glob('.lock-*')))
        with self.assertRaises(ValueError):
            archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
        with patch.object(Path, 'rename', side_effect=OSError('injected publish failure')), self.assertRaises(OSError):
            self.write()
        self.assertFalse((self.root / self.target['target_id']).exists())
        self.assertFalse(any(self.root.glob('.lock-*')))
        # A fresh explicit retry may publish, without treating failed pending as valid.
        self.write()
        self.assertTrue(any(self.root.glob('.pending-*')))

    def test_each_saved_artifact_tamper_rejected_and_existing_bytes_preserved(self):
        folder = Path(self.write()['archive_path'])
        names = ['target.json', 'proposal.json', 'receipt.json', 'complete.json',
                 next((folder / 'sources').iterdir()).relative_to(folder).as_posix(),
                 next((folder / 'implementation').iterdir()).relative_to(folder).as_posix()]
        for name in names:
            path = folder / name
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            before = self.snapshot()
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive.read_saved_frontier_policy(research_root=self.root, target_id=self.target['target_id'])
            with self.subTest(write=name), self.assertRaises(ValueError):
                self.write()
            self.assertEqual(before, self.snapshot())
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
