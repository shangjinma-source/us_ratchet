import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from scripts import ndx_single_replacement_selection_20261003 as m
from test_ndx_single_replacement_selection_publisher_20261003 import physical
class Tests(unittest.TestCase):
 def test_preexisting_nested_failure_cannot_be_adopted_as_inventory(self):
  with tempfile.TemporaryDirectory()as tmp,physical(Path(tmp))as rr:
   (m.EXECUTION/'shard-0000'/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.load_inputs(rr)
   self.assertFalse(m.OUTPUT.exists())
 def test_nonserializable_return_preserved_before_validation_failure(self):
  class Hostile:
   def __repr__(self):raise RuntimeError('repr also failed')
  with tempfile.TemporaryDirectory()as tmp,physical(Path(tmp))as rr:
   c=m.load_inputs(rr);c['core']=SimpleNamespace(select_complete_single_replacements=lambda **kw:Hostile())
   with patch.object(m,'load_inputs',return_value=c),self.assertRaises(BaseException):m.run(registration_reference=rr,execute=True)
   self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'raw_selection.json').exists())
   raw=json.loads((m.OUTPUT/'raw_selection.json').read_bytes());self.assertIs(raw['returned'],True)
   self.assertFalse((m.OUTPUT/'publication.json').exists())
 def test_full_physical_eof_before_valid_selection_and_no_evaluation(self):
  with tempfile.TemporaryDirectory()as tmp,physical(Path(tmp))as rr:
   c=m.load_inputs(rr);last=m.EXECUTION/'shard-0001'/'journal.jsonl';last.write_bytes(last.read_bytes()+b'extra')
   with patch.object(m,'load_inputs',return_value=c),self.assertRaises(ValueError):m.run(registration_reference=rr,execute=True)
   self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'selection.json').exists());self.assertFalse((m.OUTPUT/'publication.json').exists())
if __name__=='__main__':unittest.main()
