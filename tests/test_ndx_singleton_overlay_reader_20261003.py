import copy,importlib.util,io,zipfile,unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('overlay_read','scripts/ndx_dated_singleton_overlay_independent_readback_20261003.py')
f=load('hfixture','tests/test_ndx_h_workbook_export_inspection_research.py')
n=load('nativefixture','tests/test_ndx_overlay_native_links_20261003.py')

def captures():
 old,new=m.label_formulas();a=dict(worksheet='路径查看',start_row_zero_based=4,start_column_zero_based=0,row_count=1,column_count=3,values=[[None,'#VALUE!',-2]],formulas=[[None,old,None]])
 b=copy.deepcopy(a);b['values'][0][1]='ID: '+'a'*64;b['formulas'][0][1]=new;return a,b

class Tests(unittest.TestCase):
 def test_pending_before_any_source_read_or_directory(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')),patch.object(Path,'mkdir',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
 def test_full_cells_only_registered_delta(self):
  a,b=captures();self.assertEqual(m.inspect_capture_delta(iter([a]),iter([b]),'a'*64),{'checked_cells':3,'changed_cells':1})
  for mode in ('zero','formula','label','range','duplicate'):
   c=copy.deepcopy(b);rows=[c]
   if mode=='zero':c['values'][0][0]=0
   elif mode=='formula':c['formulas'][0][2]='=1'
   elif mode=='label':c['values'][0][1]='ID: '+'b'*64
   elif mode=='range':c['start_row_zero_based']=5
   else:rows.append(copy.deepcopy(c))
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_capture_delta(iter([a]),iter(rows),'a'*64)
 def test_independent_source_graph_b5_only(self):
  core=f.m;w,t=f.source_fixture();report=core.inspect_saved_source_tables(w,[t],[t['numerical_task_id']]);g=core.static_graph_contract(1,report)
  w['sheets']['路径查看']={};w['sheets']['风险查看']={}
  for (sheet,a),v in g['literals'].items():w['sheets'][sheet][a]={'kind':'n' if type(v)is int else 'str','value':Decimal(v) if type(v)is int else v,'formula':None}
  for (sheet,a),v in g['formulas'].items():w['sheets'][sheet][a]={'kind':'n','value':None,'formula':v}
  w['sheets']['路径查看']['B5']={'kind':'str','value':'ID: '+t['numerical_task_id'],'formula':m.label_formulas()[1][1:]}
  w['charts']=[dict(c,part=f'xl/charts/chart{i+1}.xml') for i,c in enumerate(g['charts'])]
  w['validations']={s:[dict(sqref='B4',type='whole',operator='between',formula1='1',formula2=str(v))] for s,v in [('路径查看',1),('风险查看',127)]}
  self.assertTrue(m.inspect_repaired_graph(core,w,[t],[t['numerical_task_id']])['static_chart_source_graph_verified'])
  for mode in ('old','otherformula','series','missing'):
   bad=copy.deepcopy(w)
   if mode=='old':bad['sheets']['路径查看']['B5']['formula']=m.label_formulas()[0][1:]
   elif mode=='otherformula':bad['sheets']['风险查看']['B3']['formula']="'路径查看'!B5"
   elif mode=='series':bad['charts'][0]['series'][0]['formula']='路径查看!C49:C175'
   else:bad['sheets']['候选路径']['B2']['value']=None
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_repaired_graph(core,bad,[t],[t['numerical_task_id']])
 def test_native_relocation_other_zip_parts_immutable(self):
  raw,links=n.fixture();new=n.m.relocate_navigation(raw,links,'D:/saved/old','D:/saved/new');m.inspect_navigation_relocation(raw,new,links)
  b=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(new)) as z,zipfile.ZipFile(b,'w') as out:
   for name in z.namelist():out.writestr(name,b'changed' if name=='untouched.bin' else z.read(name))
  with self.assertRaises(ValueError):m.inspect_navigation_relocation(raw,b.getvalue(),links)
  bad=copy.deepcopy(links);bad[0]['target']='foreign.xlsx'
  with self.assertRaises(ValueError):m.inspect_navigation_relocation(raw,new,bad)
if __name__=='__main__':unittest.main()
