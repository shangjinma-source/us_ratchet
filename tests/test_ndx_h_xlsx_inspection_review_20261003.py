"""Bounded independent OOXML/source counterexamples; no saved actual export read."""
import copy,importlib.util,io,sys,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_h_workbook_export_inspection_research as m
spec=importlib.util.spec_from_file_location('h_owner_fixture',ROOT/'tests/test_ndx_h_workbook_export_inspection_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def two_tasks():
    _,a=f.source_fixture();b=copy.deepcopy(a);b['numerical_task_id']='b'*64
    b['original_target_chain_evidence']['incumbent']['source_evidence']['source_reference']['path']='second-input'
    # Break fixture aliasing: original shared references are independently restored.
    for role in m.SHARED:b['series'][role]=copy.deepcopy(a['series'][role])
    for role in ('incumbent_integer','incumbent_continuous'):b['risk_tracks'][role]=copy.deepcopy(a['risk_tracks'][role])
    tasks=[a,b];w={'sheets':{k:{} for k in ('风险明细001','风险定位001','风险来源001')},'charts':[],'native_links':[]};captured=[]
    def capture(_w,name,rows,json_columns=()):captured.append((name,copy.deepcopy(rows),json_columns));return 0
    # Fixture construction only; tests below use actual independent checks, no mock.
    with patch.object(m,'source_table',capture):m.inspect_saved_source_tables(w,tasks,[a['numerical_task_id'],b['numerical_task_id']])
    for name,rows,cols in captured:w['sheets'][name]=f.cells(rows,cols)
    return w,tasks

def drawing_package(shared_chart=False):
    files={'xl/workbook.xml':f'<workbook xmlns="{m.M}" xmlns:r="{m.R}"><sheets><sheet name="One" sheetId="1" r:id="s1"/><sheet name="Two" sheetId="2" r:id="s2"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{m.P}">'+''.join(f'<Relationship Id="s{i}" Type="{m.R}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in (1,2))+'</Relationships>'}
    for i,n in ((1,10),(2,10 if shared_chart else 2)):
        files[f'xl/worksheets/sheet{i}.xml']=f'<worksheet xmlns="{m.M}" xmlns:r="{m.R}"><sheetData/><drawing r:id="d"/></worksheet>'
        files[f'xl/worksheets/_rels/sheet{i}.xml.rels']=f'<Relationships xmlns="{m.P}"><Relationship Id="d" Type="{m.R}/drawing" Target="../drawings/drawing{i}.xml"/></Relationships>'
        files[f'xl/drawings/drawing{i}.xml']=f'<drawing xmlns:c="{m.C}" xmlns:r="{m.R}"><c:chart r:id="c"/></drawing>'
        files[f'xl/drawings/_rels/drawing{i}.xml.rels']=f'<Relationships xmlns="{m.P}"><Relationship Id="c" Type="{m.R}/chart" Target="../charts/chart{n}.xml"/></Relationships>'
        files[f'xl/charts/chart{n}.xml']=f'<chartSpace xmlns="{m.C}"><chart><plotArea><lineChart><ser><cat><strRef><f>One!A1:A2</f></strRef></cat><val><numRef><f>One!B1:B2</f></numRef></val></ser></lineChart></plotArea></chart></chartSpace>'
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for p,v in files.items():z.writestr(p,v)
    return b.getvalue()

class Review(unittest.TestCase):
    def test_drawing_relationships_not_chart_number_determine_owner(self):
        w=m.read_workbook(drawing_package());self.assertEqual([(x['part'],x['worksheet'],x['chart_ordinal']) for x in w['charts']],[('xl/charts/chart2.xml','Two',0),('xl/charts/chart10.xml','One',0)])
        with self.assertRaises(ValueError):m.read_workbook(drawing_package(True))
    def test_task_specific_target_ref_and_shared_daily_identity(self):
        w,t=two_tasks();ids=[x['numerical_task_id'] for x in t];m.inspect_saved_source_tables(w,t,ids)
        for role in ('incumbent_integer','incumbent_continuous'):
            b=copy.deepcopy(t);b[1]['risk_tracks'][role]['source_reference']['path']='wrong-shared'
            with self.subTest(role=role),self.assertRaises(ValueError):m.inspect_saved_source_tables(w,b,ids)
        b=copy.deepcopy(w)
        # Last target source remains distinct; forging its pointer is not a shared alias.
        source=b['sheets']['风险来源001'];matches=[c for c in source.values() if isinstance(c['value'],str) and 'second-input' in c['value']];self.assertTrue(matches);matches[0]['value']='{}'
        with self.assertRaises(ValueError):m.inspect_saved_source_tables(b,t,ids)
    def test_source_values_cannot_be_self_reported_and_missing_is_not_zero(self):
        w,t=f.source_fixture();ids=[t['numerical_task_id']]
        for value in (None,'缺失或超出展示精度'):
            b=copy.deepcopy(w);b['sheets']['候选路径']['B2']['value']=value
            with self.assertRaises(ValueError):m.inspect_saved_source_tables(b,[t],ids)
        for saved in ('1e-400','0'):
            cell={'kind':'n','value':m.Decimal(saved),'formula':None,'text_format':False}
            if saved=='0':m.cell_equal(cell,0)
            else:
                with self.assertRaises(ValueError):m.cell_equal(cell,0)

if __name__=='__main__':unittest.main()
