"""Independent offline runner boundaries; transport declarations are not real77 arithmetic."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
import contextlib,hashlib,importlib.util,json,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'tmp/first_full_exact_matrix_runner_20261009_v1.py'
assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='50e1d35adaf8f9dc721e28d36093377a708eaea7f74f2a87f26c0cb3bdf1481f'
def load(p,name):
 sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
s=load(PATH,'c_full_subject')
# Shared transport builder only; none of the author test methods are run.
a=load(ROOT/'tests/test_first_full_exact_matrix_runner_offline_20261009_v1.py','c_transport_shapes')
OBS={}
class Independent(unittest.TestCase):
 def test_01_fixed_metadata_closure_and_no_claim_read(self):
  cat=json.loads(s.HOST_FILES[1][0].read_bytes());supp=json.loads(s.HOST_FILES[3][0].read_bytes())
  for ref in (s.HOST_FILES[1],s.HOST_FILES[3]):self.assertEqual(hashlib.sha256(ref[0].read_bytes()).hexdigest(),ref[1])
  with patch.object(Path,'read_bytes',side_effect=AssertionError('Derived IO forbidden')):
   sources,ns=s.derive_closure(cat,supp,s.HOST_FILES)
   self.assertEqual((len(sources),len(ns)),(262,7));self.assertEqual(s.sha(s.encoded(sources)),s.CLOSED_MAP_SHA);self.assertEqual(s.sha(s.encoded(ns)),s.NAMESPACE_MAP_SHA)
   snap=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',source_facts=dict(consumed_source_hashes=deepcopy(sources),namespace_snapshots=deepcopy(ns)))
   s.associate_snapshot(snap,sources,ns)
   snap['source_facts']['consumed_source_hashes'][str(ROOT/'UNREAD_C_TRAP')]='0'*64
   with self.assertRaisesRegex(ValueError,'CORE source closure'):s.associate_snapshot(snap,sources,ns)
   legal=[x for k,x in cat['roles'].items() if x['profile']=='CORE_PRESERVED_FAILED_EVIDENCE_ONLY'];self.assertTrue(legal)
   for x in legal:self.assertIn(x['reference']['path'],sources)
  OBS['closure']='Fixed2 metadata reads only;262/7 hash identities exact, registeredfailed evidence retained, no CORE guard or serialized claim read.'
 def test_02_runtime_and_temp_drift_guards(self):
  for effective,flag in ((0,8192),(8192,0),(8192,4300),(4300,8192)):
   with patch.object(s.sys,'get_int_max_str_digits',return_value=effective),patch.object(s.sys,'flags',SimpleNamespace(int_max_str_digits=flag)),patch.object(Path,'lstat',side_effect=AssertionError('PreIO')):
    with self.assertRaisesRegex(ValueError,'runtime'):s.run(execute=True)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);files=[]
   for name in ('own','helper','host','plan'):
    p=root/name;p.write_bytes(name.encode());files.append(p)
   pins={str(p):s.sha(p.read_bytes()) for p in files};ns={str(root):s.namespace(root)}
   self.assertEqual(s.guard(pins,ns)['files'],4)
   real=Path.read_bytes
   for target in files:
    def altered(p):return b'READVIEW_DRIFT' if p==target else real(p)
    with patch.object(Path,'read_bytes',altered):
     with self.assertRaisesRegex(ValueError,'Fixed source bytes'):s.guard(pins,ns)
   (root/'unregistered_failure.json').write_bytes(b'{}')
   with self.assertRaisesRegex(ValueError,'Namespace changed'):s.guard(pins,ns)
   self.assertEqual([p.read_bytes() for p in files],[p.name.encode() for p in files])
 def test_03_actual_windows_output_junctions_and_safe_failure(self):
  observations=[]
  for mode in ('parent','ancestor','existing','postmkdir','save'):
   with tempfile.TemporaryDirectory() as td:
    base=Path(td);target=base/'target';target.mkdir();link=base/'link'
    def junction():
     p=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
    out=base/'out';realmkdir=Path.mkdir
    if mode in ('parent','ancestor','existing'):
     junction();out={'parent':link/'out','ancestor':link/'inner'/'out','existing':link}[mode]
     if mode=='ancestor':(target/'inner').mkdir()
    def mkdir(p,*args,**kw):
     result=realmkdir(p,*args,**kw)
     if mode=='postmkdir' and p==out:os.rmdir(out);junction();os.rename(link,out)
     return result
    def take(ref):
     if mode=='save':
      os.rmdir(out) if not list(out.iterdir()) else None
      # START already exists; preserve it outside redirected namespace.
      if out.exists():out.rename(base/'saved_safe_start')
      junction();os.rename(link,out)
     raise ValueError('C_FIXED_READ_FAILURE')
    try:
     with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=take) as reads,patch.object(Path,'mkdir',mkdir):
      with self.assertRaisesRegex(ValueError,'reparse|already exists'):s.run(execute=True)
     self.assertFalse(any(p.is_file() for p in target.rglob('*')));observations.append(dict(mode=mode,unsafe_files=0,reads=reads.call_count))
    finally:
     for p in (link,out):
      if p.exists() and p.is_junction():os.rmdir(p)
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/'safe'
   with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=ValueError('C_SAFE_FAIL')):
    with self.assertRaisesRegex(ValueError,'C_SAFE_FAIL'):s.run(execute=True)
    self.assertEqual(sorted(p.name for p in out.iterdir()),['START.json','exception.json'])
    failure=json.loads((out/'exception.json').read_bytes());self.assertFalse(failure['numerical_file_exists'])
    with self.assertRaisesRegex(ValueError,'already exists'):s.run(execute=True)
  OBS['junctions']=observations
 def test_04_complete_transport_ledger_bits_and_failure_artifact(self):
  out=a.controlled_result();report=s.validate_complete(out,dict(max_bits=[0,1]));self.assertFalse(report['arithmetic_certificate_recomputed'])
  self.assertEqual(sum(s.expected_primitives().values()),77*127+3003*508);self.assertEqual(s.BUDGET,1535303)
  for mutate in (lambda r:r['arithmetic_ledger'][-1].update(stop=s.BUDGET-1),lambda r:r['work'].update(output_max_fraction_bits=[1,1]),lambda r:r['work']['actual_primitive_counts'].update(pair_products=378377),lambda r:r['full_covariance'][0].__setitem__(1,'1')):
   bad=deepcopy(out);mutate(bad)
   with self.assertRaises(ValueError):s.validate_complete(bad,dict(max_bits=[0,1]))
  with tempfile.TemporaryDirectory() as td:
   folder=Path(td);sources={str(folder/str(i)):'0'*64 for i in range(262)};ns={str(folder/f'n{i}'):[] for i in range(7)}
   snap=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',source_facts=dict(consumed_source_hashes=sources,namespace_snapshots=ns))
   raw=json.dumps(snap).encode();partial=deepcopy(out);partial['status']='PARTIAL_PENDING_BUDGET';calls=[]
   fake=SimpleNamespace(prepare_exact_training_moments=lambda **kw:(calls.append(kw['work_budget']) or partial))
   blobs={str(s.SNAPSHOT[0]):raw,str(s.HOST_FILES[1][0]):b'{}',str(s.HOST_FILES[3][0]):b'{}'}
   with patch.object(s,'OUT',folder/'measurement'),patch.object(s,'take',side_effect=lambda ref:blobs.get(str(ref[0]),b'pass')),patch.object(s,'derive_closure',return_value=(sources,ns)),patch.object(s,'CLOSED_MAP_SHA',s.sha(s.encoded(sources))),patch.object(s,'NAMESPACE_MAP_SHA',s.sha(s.encoded(ns))),patch.object(s,'choose_matrix',return_value=(a.matrix(),[])),patch.object(s,'guard',return_value={'scope':'C_MOCK_NO_REAL_GUARD'}),patch.object(s.types,'ModuleType',return_value=fake):
    with self.assertRaisesRegex(ValueError,'Expected complete'):s.run(execute=True)
   path=folder/'measurement';self.assertEqual(calls,[1535303]);self.assertEqual(sorted(p.name for p in path.iterdir()),['START.json','exception.json','full_moments.json']);self.assertEqual(json.loads((path/'full_moments.json').read_bytes())['status'],'PARTIAL_PENDING_BUDGET')
  OBS['transport']='Only mock77 result+zeros shape; no helper compiled/executed: bpass module body and explicit transport stub. Not independent covariance arithmetic.'
