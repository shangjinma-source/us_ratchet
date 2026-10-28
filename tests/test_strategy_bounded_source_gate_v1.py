from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest,os,stat
from types import SimpleNamespace
import data.strategy_bounded_source_gate_v1 as module
ROOT=Path(__file__).resolve().parents[1]
class BoundedGateTests(unittest.TestCase):
 def fixture(self,folder):
  root=Path(folder);pins={}
  for name in module.DYNAMIC_SOURCE_PATHS:
   raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  raw=b'{"fixture":true}';(root/'config.json').write_bytes(raw)
  return root,pins,{'config.json':sha256(raw).hexdigest()}
 def test_no_cache_source_and_configuration_changes_detected(self):
  with TemporaryDirectory() as folder:
   root,pins,refs=self.fixture(folder);gate=module.BoundedSourceGateV1(root=root,source_pins=pins,configuration_pins=refs)
   path=root/next(iter(pins));original=path.read_bytes();path.write_bytes(original+b' ')
   with self.assertRaisesRegex(ValueError,'BOUNDED_SOURCE_CHANGED'):gate()
   path.write_bytes(original);gate();(root/'config.json').write_bytes(b'{"fixture":null}')
   with self.assertRaisesRegex(ValueError,'BOUNDED_SOURCE_CHANGED'):gate()
 def test_identical_data_executing_path_read_once_per_call_only(self):
  pins={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in module.DYNAMIC_SOURCE_PATHS}
  original=module._read_digest
  with patch.object(module,'_read_digest',wraps=original) as read:
   gate=module.BoundedSourceGateV1(root=ROOT,source_pins=pins)
   self.assertEqual(read.call_count,len(pins));gate();self.assertEqual(read.call_count,2*len(pins))
 def test_reparse_and_stream_race_are_refused(self):
  with TemporaryDirectory() as folder:
   root,pins,refs=self.fixture(folder);gate=module.BoundedSourceGateV1(root=root,source_pins=pins,configuration_pins=refs)
   path=root/next(iter(pins));original=Path.lstat
   with patch.object(Path,'lstat',lambda p:SimpleNamespace(st_mode=stat.S_IFLNK,st_file_attributes=0) if p==path else original(p)):
    with self.assertRaisesRegex(ValueError,'BOUNDED_SOURCE_LINK_REFUSED'):gate()
   original_fstat=os.fstat;calls=[]
   def mutated(fd):
    result=original_fstat(fd);calls.append(fd)
    if len(calls)==1:path.write_bytes(path.read_bytes()+b' ')
    return result
   with patch.object(module.os,'fstat',mutated):
    with self.assertRaisesRegex(ValueError,'BOUNDED_SOURCE_READ_RACE'):module._read_digest(path,module.MAXIMUM_SOURCE_BYTES)
 def test_config_scope_and_budget(self):
  with TemporaryDirectory() as folder:
   root,pins,refs=self.fixture(folder);gate=module.BoundedSourceGateV1(root=root,source_pins=pins,configuration_pins=refs)
   with self.assertRaisesRegex(ValueError,'BOUNDED_GATE_SCOPE_MISMATCH'):gate.require_scope({'missing.py':'0'*64})
   with self.assertRaises(TypeError):gate.sources['new']='x'
   with self.assertRaisesRegex(ValueError,'BOUNDED_SOURCE_TOO_LARGE'):module._read_digest(root/'config.json',2)
