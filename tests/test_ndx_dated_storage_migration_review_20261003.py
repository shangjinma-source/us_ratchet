"""Independent migration-only tests; no saved research inputs or publication."""
import hashlib, importlib.util, json, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'tmp/dated_storage_migration_20261003'
SNAPSHOTS=ROOT/'tests/fixtures/migration_snapshots_20261008/dated'
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
def load(name):
 p=ROOT/'scripts'/name
 s=importlib.util.spec_from_file_location('migration_'+p.stem,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class MigrationReview(unittest.TestCase):
 def test_eight_hashes_paths_and_future_pins(self):
  before=json.loads((BACKUP/'before.json').read_text());after=json.loads((BACKUP/'after.json').read_text())
  for name,h in before.items():
   self.assertEqual(hashlib.sha256((BACKUP/name).read_bytes()).hexdigest(),h)
   self.assertEqual(hashlib.sha256((SNAPSHOTS/name).read_bytes()).hexdigest(),after[name])
   if name.endswith('.mjs'):continue
   # Historical metadata only; current resources are tested separately below.
   m=load_backup(name,SNAPSHOTS);self.assertEqual(m.ROOT,ROOT);self.assertTrue(m.OUTPUT.is_relative_to(STORAGE))
   old=load_backup(name)
   for table in ('BOUND','INPUT_BOUND','READERS'):
    for k,(p,sha) in getattr(m,table,{}).items():
     op,oh=getattr(old,table,{})[k]
     if oh is None:self.assertIsNone(sha)
     actual=ROOT/p
     if '/scripts/' in actual.as_posix() or '/backtest/' in actual.as_posix():
      self.assertTrue(actual.is_relative_to(ROOT))
      if sha is not None:
       historical=SNAPSHOTS/actual.name
       self.assertEqual(hashlib.sha256((historical if historical.is_file() else actual).read_bytes()).hexdigest(),sha)
   if hasattr(m,'COMPARISON_ROOT'):self.assertTrue(m.COMPARISON_ROOT.is_relative_to(ROOT))
  p=SNAPSHOTS/'ndx_dated_workbook_extension_publish_20261003.mjs'
  code="const m=await import("+json.dumps(p.as_uri())+");console.log(JSON.stringify({output:m.OUTPUT,bound:m.BOUND}));"
  d=json.loads(subprocess.check_output(['node','--input-type=module','-e',code],text=True))
  self.assertTrue(Path(d['output']).is_relative_to(STORAGE))
  for k in ('index','publication','audit','tasks','shared','classification'):
   self.assertTrue(Path(d['bound'][k]['path']).is_relative_to(STORAGE));self.assertIsNone(d['bound'][k]['sha256'])
 def test_target_volume_and_exact_reserve_boundary(self):
  for name in PRODUCERS:
   m=load(name)
   with patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES+13)) as disk:
    m.resource_gate(13);disk.assert_called_with(Path('D:/'))
    with self.assertRaises(ValueError):m.resource_gate(14)
    for bad in (True,1.0,-1):
     with self.assertRaises(ValueError):m.resource_gate(bad)
 def test_no_normal_save_when_low_but_failure_durable(self):
  for name in PRODUCERS:
   m=load(name)
   with tempfile.TemporaryDirectory() as td,patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
    root=Path(td);normal=root/'index.json'
    with self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):m.save(normal,{'x':1})
    self.assertFalse(normal.exists())
    failure=root/'failure.json';m.save(failure,{'status':'FAILED_DO_NOT_CONSUME'})
    self.assertEqual(json.loads(failure.read_bytes())['status'],'FAILED_DO_NOT_CONSUME')
    with self.assertRaises(FileExistsError):m.save(failure,{})
 def test_mkdir_and_each_record_have_prewrite_gate(self):
  import ast
  for name in PRODUCERS:
   tree=ast.parse((ROOT/'scripts'/name).read_text(encoding='utf8'))
   run=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run')
   # Every successful mkdir is directly preceded by a gate, also inside semicolon lines.
   for node in ast.walk(run):
    for field in ('body','orelse','finalbody'):
     seq=getattr(node,field,None)
     if not isinstance(seq,list):continue
     for i,v in enumerate(seq):
      if isinstance(v,ast.Expr) and isinstance(v.value,ast.Call) and isinstance(v.value.func,ast.Attribute) and v.value.func.attr=='mkdir':
       self.assertGreater(i,0);self.assertIn('resource_gate()',ast.unparse(seq[i-1]))
   nested=[x for x in ast.walk(run) if isinstance(x,ast.FunctionDef) and x is not run]
   emit=next(x for x in nested if x.name in ('write_row','emit'))
   source=ast.unparse(emit);self.assertLess(source.index('resource_gate('),source.index('.write('))
PRODUCERS=['ndx_dated_path_risk_display_20261003.py','ndx_dated_risk_chain_display_20261003.py','ndx_dated_workbook_extension_data_20261003.py']
def load_backup(name,directory=BACKUP):
 # Preserve original __file__ location for ROOT while interpreting only backed-up bytes.
 import types
 m=types.ModuleType('old_'+name);m.__file__=str(ROOT/'scripts'/name);exec(compile((directory/name).read_bytes(),m.__file__,'exec'),m.__dict__);return m
if __name__=='__main__':unittest.main()
