import os,stat,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import data.strategy_v27_source_digest_v1 as m
class LinkTests(unittest.TestCase):
 def test_missing_skipped_by_links_but_read_rejects(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'absent';m._no_links(p)
   with self.assertRaisesRegex(ValueError,'SOURCE_MISSING'):m._read_digest(p,100)
 def test_symlink_and_reparse_rejected(self):
  p=Path('synthetic')
  for mode,attrs in [(stat.S_IFLNK,0),(stat.S_IFREG,0x400)]:
   with self.subTest(mode=mode,attrs=attrs),patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=mode,st_file_attributes=attrs)):
    with self.assertRaisesRegex(ValueError,'LINK_REFUSED'):m._no_links(p)
 def test_permission_and_other_errors_propagate(self):
  for error in [PermissionError('denied'),OSError('unexpected')]:
   with self.subTest(error=type(error).__name__),patch.object(Path,'lstat',side_effect=error):
    with self.assertRaises(type(error)):m._no_links(Path('synthetic'))
 def test_exactly_one_lstat_per_path_each_call(self):
  p=Path('synthetic/child')
  with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0)) as mocked:
   m._no_links(p);m._no_links(p)
   self.assertEqual(mocked.call_count,2*(1+len(p.parents)))
 def test_read_boundary_mutation_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source';p.write_bytes(b'abc');old=m._no_links;calls=[]
   def check(path):
    calls.append(path)
    if len(calls)==2:p.write_bytes(b'changed-size')
    old(path)
   with patch.object(m,'_no_links',side_effect=check):
    with self.assertRaisesRegex(ValueError,'READ_RACE'):m._read_digest(p,100)
   self.assertEqual(len(calls),2)
 def test_read_midstream_signature_change_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source';p.write_bytes(b'abc');real=os.fstat;calls=[]
   def changed(fd):
    row=real(fd);calls.append(fd)
    return row if len(calls)==1 else SimpleNamespace(st_dev=row.st_dev,st_ino=row.st_ino,st_size=row.st_size+1,st_mtime_ns=row.st_mtime_ns)
   with patch.object(m.os,'fstat',side_effect=changed):
    with self.assertRaisesRegex(ValueError,'READ_RACE'):m._read_digest(p,100)
 def test_valid_hash_unchanged(self):
  from hashlib import sha256
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source';p.write_bytes(b'abc');self.assertEqual(m._read_digest(p,100),sha256(b'abc').hexdigest())
if __name__=='__main__':unittest.main()
