"""Explicit test approvals only; no production approval or account writes."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.strategy_dynamic_source_gate import DYNAMIC_SOURCE_PATHS, validate_dynamic_sources, bind_dynamic_source_gate


class DynamicSourceGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pins = {}
        executing = Path(__file__).resolve().parents[1]
        for name in DYNAMIC_SOURCE_PATHS:
            raw = (executing/name).read_bytes()
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            self.pins[name] = sha256(raw).hexdigest()

    def validate(self, pins=None):
        validate_dynamic_sources(root=self.root, source_pins=self.pins if pins is None else pins)

    def test_real_sources_and_self_pin_read_only(self):
        self.assertIn('data/strategy_dynamic_source_gate.py', self.pins)
        before = {name:(self.root/name).read_bytes() for name in self.pins}
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.validate()
        self.assertEqual(before, {name:(self.root/name).read_bytes() for name in self.pins})
        self.assertFalse((self.root/'data/strategy_account').exists())

    def test_missing_scope_and_bad_hash(self):
        pins = dict(self.pins)
        del pins['data/strategy_dynamic_source_gate.py']
        with self.assertRaisesRegex(ValueError, 'DYNAMIC_SOURCE_SCOPE_REQUIRED'):
            self.validate(pins)
        pins = dict(self.pins)
        pins['data/strategy_dynamic_source_gate.py'] = 'unapproved'
        with self.assertRaisesRegex(ValueError, 'DYNAMIC_SOURCE_HASH_REQUIRED'):
            self.validate(pins)

    def test_bound_gate_keeps_approved_pins_and_rechecks_files(self):
        gate = bind_dynamic_source_gate(root=self.root, source_pins=self.pins)
        self.pins.clear()
        gate()
        (self.root/'data/strategy_dynamic_source_gate.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'DYNAMIC_SOURCE_CHANGED'):
            gate()

    def test_data_source_drift(self):
        (self.root/'data/strategy_dynamic_source_gate.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'DYNAMIC_SOURCE_CHANGED'):
            self.validate()

    def test_separate_execution_root_drift(self):
        name = 'data/strategy_dynamic_source_gate.py'
        with TemporaryDirectory() as directory:
            executing = Path(directory)
            for path in self.pins:
                target = executing/path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((self.root/path).read_bytes())
            (executing/name).write_bytes(b'changed')
            with patch('data.strategy_dynamic_source_gate._executing_root', return_value=executing):
                with self.assertRaisesRegex(ValueError, 'DYNAMIC_EXECUTING_SOURCE_CHANGED'):
                    self.validate()

    def test_unsafe_extra_paths(self):
        for path in ('../bad.py','/bad.py','C:/bad.py','a\\bad.py','a//bad.py'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError,'DYNAMIC_SOURCE_PATH_INVALID'):
                self.validate(dict(self.pins, **{path:'0'*64}))

    def test_links_junctions_and_size(self):
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'DYNAMIC_SOURCE_LINK_REFUSED'):
                self.validate()
        original = Path.lstat
        def junction(path):
            value = original(path)
            return SimpleNamespace(st_file_attributes=0x400, st_mode=value.st_mode) if path == self.root else value
        with patch.object(Path,'lstat',junction):
            with self.assertRaisesRegex(ValueError,'DYNAMIC_SOURCE_LINK_REFUSED'):
                self.validate()
        with patch('data.strategy_dynamic_source_gate.MAXIMUM_SOURCE_BYTES',1):
            with self.assertRaisesRegex(ValueError,'DYNAMIC_SOURCE_TOO_LARGE'):
                self.validate()


if __name__ == '__main__':
    unittest.main()
