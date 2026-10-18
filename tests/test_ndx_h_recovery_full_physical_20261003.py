"""Complete physical synthetic recovery, actual independent ZIP+graph code."""
import contextlib,copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from h_recovery_physical_fixture_20261003 import physical,encode
from scripts import ndx_h_failed_export_recovery_independent_readback_20261003 as r

class PhysicalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.args,cls.manifest=physical(cls.root)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 @contextlib.contextmanager
 def configured(self,suffix):
  with contextlib.ExitStack()as stack:
   for k,v in self.args.items():stack.enter_context(patch.object(r,k,v if k!='OUTPUT'else self.root/suffix))
   yield
 def rebind(self,m):
  root=self.args['RECOVERY'];raw=encode(m);(root/'export_manifest.json').write_bytes(raw)
  bound=copy.deepcopy(self.args['BOUND']);bound['manifest']=(str(root/'export_manifest.json'),r.sha(raw))
  p=json.loads((root/'publication.json').read_bytes());p['manifest_reference']=r.reference(*bound['manifest']);raw=encode(p);(root/'publication.json').write_bytes(raw);bound['recovery_publication']=(str(root/'publication.json'),r.sha(raw));return bound
 def test_01_full277_packages_44real_graph_repairs_233copies_and_1632_native_links(self):
  with self.configured('success'):
   result=r.readback(execute=True);report=json.loads(Path(result['path']).read_bytes())
  self.assertEqual(report['verified_package_count'],277);self.assertEqual(report['verified_task_count'],1632)
  self.assertEqual(sum(p['action'].startswith('REBUILD')for p in report['packages']),44)
  self.assertEqual(report['navigation_links_verified'],1632);self.assertEqual(report['machine']['verified_records'],1632)
  self.assertTrue(report['parent_remains_failed']);self.assertFalse(report['visual_acceptance_passed']);self.assertFalse(report['workbook_delivered'])
  with self.configured('success'),self.assertRaisesRegex(ValueError,'Create only'):r.readback(execute=True)
 def test_02_last_copy_package_resigned_new_manifest_cannot_replace_original_bytes(self):
  root=self.args['RECOVERY'];target=root/'package-0277.xlsx';original=target.read_bytes();manifest_bytes=(root/'export_manifest.json').read_bytes();pub_bytes=(root/'publication.json').read_bytes()
  try:
   raw=original+b'changed';target.write_bytes(raw);m=copy.deepcopy(self.manifest);p=m['packages'][-1];p['sha256']=r.sha(raw);p['workbook_reference']['sha256']=r.sha(raw);p['byte_count']=len(raw)
   for row in m['output_inventory']:
    if row['path']==target.name:row.update(sha256=r.sha(raw),byte_count=len(raw))
   bound=self.rebind(m)
   with self.configured('bad-last'),patch.object(r,'BOUND',bound),self.assertRaisesRegex(ValueError,'Copy hash'):r.readback(execute=True)
  finally:target.write_bytes(original);(root/'export_manifest.json').write_bytes(manifest_bytes);(root/'publication.json').write_bytes(pub_bytes)
 def test_03_resigned_last_navigation_target_rejected_after_all277_independent_checks(self):
  root=self.args['RECOVERY'];target=root/'路径与风险导航.xlsx';original=target.read_bytes();manifest_bytes=(root/'export_manifest.json').read_bytes();pub_bytes=(root/'publication.json').read_bytes()
  try:
   with zipfile.ZipFile(io.BytesIO(original))as archive:parts={n:archive.read(n)for n in archive.namelist()}
   n='xl/worksheets/sheet1.xml';needle=b'ref="H1633"';start=parts[n].index(needle);end=parts[n].index(b'/>',start);segment=parts[n][start:end]
   self.assertIn(b'A7',segment);parts[n]=parts[n][:start]+segment.replace(b'A7',b'A999')+parts[n][end:]
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED)as archive:
    for name,b in parts.items():archive.writestr(name,b)
   raw=out.getvalue();target.write_bytes(raw);m=copy.deepcopy(self.manifest);m['navigation']['workbook_reference']['sha256']=r.sha(raw)
   for row in m['output_inventory']:
    if row['path']==target.name:row.update(sha256=r.sha(raw),byte_count=len(raw))
   bound=self.rebind(m)
   with self.configured('bad-navigation'),patch.object(r,'BOUND',bound),self.assertRaisesRegex(ValueError,'Exact evidence'):r.readback(execute=True)
   failure=json.loads((self.root/'bad-navigation/failure.json').read_bytes());self.assertEqual(failure['completed_package_count'],277);self.assertEqual(failure['status'],'FAILED_NO_RETRY')
   self.assertFalse((self.root/'bad-navigation/independent_readback.json').exists())
   with self.configured('bad-navigation'),patch.object(r,'BOUND',bound),self.assertRaisesRegex(ValueError,'Create only'):r.readback(execute=True)
  finally:target.write_bytes(original);(root/'export_manifest.json').write_bytes(manifest_bytes);(root/'publication.json').write_bytes(pub_bytes)

if __name__=='__main__':unittest.main()
