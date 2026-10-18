"""Independent tiny centered oracle vs raw-cross verifier. No real files/source matrices."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch
import ast,hashlib,importlib.util,json,unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'backtest/ndx_full_pool_training_identity_readback_research.py'
assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='a46a6137457a83b64d6fb35a2fa32c57033cd780c153964557fd85b360074f7e'
def load(p,name):
 sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
s=load(PATH,'c_identity');transport=load(ROOT/'tests/test_ndx_full_pool_training_identity_readback_research.py','c_transport')
OBS={}
def case(m=2):
 rows=[['1/7','2/7','0'],['2/7','1/7','1/7'],['3/7','0','2/7']];rows=[row[:m] for row in rows];mat=transport.matrix(rows,m=m,n=3);values=[[F(x) for x in row] for row in rows];means=[sum((row[i] for row in values),F())/3 for i in range(m)];samples=[];entries=[]
 # Independent CENTERED formula, not subject rawcross identity.
 for i in range(m):
  for j in range(i,m):
   sample=sum(((row[i]-means[i])*(row[j]-means[j]) for row in values),F())/2
   samples.append(sample);entries.append(sample if i==j else sample*F(13,20))
 doc=transport.declared_producer(mat,means=list(map(str,means)),samples=list(map(str,samples)),entries=list(map(str,entries)))
 return mat,doc,means,samples,entries
class Tracked(F):
 operations={}
 def op(self,name,value):self.operations[name]=self.operations.get(name,0)+1;return Tracked(value)
 def __add__(self,x):return self.op('add',super().__add__(x))
 def __sub__(self,x):return self.op('sub',super().__sub__(x))
 def __mul__(self,x):return self.op('mul',super().__mul__(x))
 def __truediv__(self,x):return self.op('div',super().__truediv__(x))
def call(mat,doc,budget):
 with patch('builtins.open',side_effect=AssertionError('SourceIO')),patch.object(Path,'read_bytes',side_effect=AssertionError('SourceIO')):
  return s.verify_raw_cross_moment_identity(matrix=mat,numerical_result=doc,work_budget=budget)
def update_bits(doc):
 values=[F(x['value']) for x in doc['mean_tasks']]+[F(x[k]) for x in doc['pair_tasks'] for k in ('sample','value')]
 doc['work']['output_max_fraction_bits']=[max(abs(x.numerator).bit_length() for x in values),max(x.denominator.bit_length() for x in values)];doc['work']['intermediate_max_fraction_bits']=[14245,14138]
class Independent(unittest.TestCase):
 def test_01_actual47_fraction_calls_and_centered_equality(self):
  mat,doc,means,samples,entries=case();before=deepcopy((mat,doc));Tracked.operations={}
  with patch.object(s,'Fraction',Tracked):out=call(mat,doc,47)
  self.assertEqual(Tracked.operations,dict(add=18,div=5,mul=21,sub=3));self.assertEqual(sum(Tracked.operations.values()),47);self.assertEqual(out['work']['spent'],47)
  self.assertEqual([F(x['value']) for x in out['mean_tasks']],means);self.assertEqual([F(x['sample']) for x in out['pair_tasks']],samples);self.assertEqual([F(x['value']) for x in out['pair_tasks']],entries);self.assertLess(samples[1],0);self.assertNotEqual(means[0],0);self.assertEqual((mat,doc),before)
  self.assertEqual(out['work']['full_coordinates_independently_compared'],4);self.assertFalse(out['producer_declarations']['intermediate_maxima_independently_replayed']);out['mean_tasks'].clear();self.assertEqual((mat,doc),before)
  OBS['actual_operator_calls']=Tracked.operations
 def test_02_rank_deficient_three_columns_all_coordinates(self):
  mat,doc,means,samples,entries=case(3);out=call(mat,doc,90);self.assertEqual([F(x['sample']) for x in out['pair_tasks']],samples);self.assertEqual(out['work']['full_coordinates_independently_compared'],9)
  # x+ y constant and x-z constant => exact centered Gram rank1, not a positive-definite assumption.
  self.assertEqual(samples,[F(1,49),-F(1,49),F(1,49),F(1,49),-F(1,49),F(1,49)]);self.assertEqual(out['work']['spent'],90);self.assertTrue(out['certificate']['independent_arithmetic_readback_complete'])
 def test_03_zero_atomic_prefix_and_preinput_gates(self):
  mat,doc,*_=case()
  for budget,spent,means,pairs in ((0,0,0,0),(3,0,0,0),(7,4,1,0),(20,8,2,0),(21,21,2,1),(46,34,2,2),(47,47,2,3)):
   Tracked.operations={}
   with patch.object(s,'Fraction',Tracked):out=call(mat,doc,budget)
   self.assertEqual((out['work']['spent'],out['work']['means_verified'],out['work']['pairs_verified']),(spent,means,pairs));self.assertEqual(sum(Tracked.operations.values()),spent);self.assertEqual(out['certificate']['independent_arithmetic_readback_complete'],budget==47)
  with patch.object(s,'_matrix',side_effect=AssertionError('InputBeforeGate')):
   for budget in (True,None,-1,1.0,787557):
    with self.assertRaises(ValueError):call(mat,doc,budget)
   with self.assertRaises(NotImplementedError):s.verify_raw_cross_moment_identity(matrix=None,numerical_result=None,work_budget=0,resume={})
 def test_04_coordinated_values_closed_types_and_no_project_dependencies(self):
  mat,doc,*_=case();call(mat,doc,47)
  bad=deepcopy(doc);bad['mean_tasks'][0]['value']='3/7';update_bits(bad)
  with self.assertRaisesRegex(ValueError,'Independent mean'):call(mat,bad,47)
  bad=deepcopy(doc);bad['pair_tasks'][1]['sample']='1/49';bad['pair_tasks'][1]['value']='13/980';bad['full_covariance'][0][1]=bad['full_covariance'][1][0]='13/980';update_bits(bad)
  with self.assertRaisesRegex(ValueError,'Independent sample'):call(mat,bad,47)
  mutators=[lambda d:d.update(extra={}),lambda d:d['work'].update(extra=0),lambda d:d['mean_tasks'][0].update(extra=0),lambda d:d['pair_tasks'][0].update(extra=0),lambda d:d['certificate'].update(independently_checked=0),lambda d:d['permissions'].__setitem__('execution_authorized',0),lambda d:d['arithmetic_ledger'][0].update(start=False),lambda d:d['work']['actual_primitive_counts'].update(mean_divisions=True)]
  for mutate in mutators:
   bad=deepcopy(doc);mutate(bad)
   with self.assertRaises(ValueError):call(mat,bad,0)
  for val in (True,None,'-1','2/4','-0','1/1',str(1<<53)):
   bad=deepcopy(mat);bad['cells'][0][0]=val
   with self.assertRaises(ValueError):call(bad,doc,0)
  tree=ast.parse(PATH.read_bytes());imports=[node for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom))]
  modules=[node.module if isinstance(node,ast.ImportFrom) else alias.name for node in imports for alias in (node.names if isinstance(node,ast.Import) else [None])]
  self.assertTrue(all(not x.startswith(('backtest','scripts')) for x in modules));self.assertTrue(all(x is False for x in call(mat,doc,47)['permissions'].values()))
