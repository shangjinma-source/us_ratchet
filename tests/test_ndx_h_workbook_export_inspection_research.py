"""Independent bounded XML and saved-source projection tests, no workbook author library."""
import copy
import io
import json
import sys
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backtest import ndx_h_workbook_export_inspection_research as m


def xlsx(sheet,strings=''):
    files={'xl/workbook.xml':f'<workbook xmlns="{m.M}" xmlns:r="{m.R}"><sheets><sheet name="表" sheetId="1" r:id="r1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{m.P}"><Relationship Id="r1" Type="{m.R}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{m.M}"><sheetData><row r="1">{sheet}</row></sheetData></worksheet>',
    'xl/styles.xml':f'<styleSheet xmlns="{m.M}"><numFmts count="1"><numFmt numFmtId="164" formatCode="@"/></numFmts><cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="49"/><xf numFmtId="164"/></cellXfs></styleSheet>'}
    if strings:files['xl/sharedStrings.xml']=f'<sst xmlns="{m.M}">{strings}</sst>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    return out.getvalue()


def cells(rows,jsoncols=()):
    result={}
    for i,row in enumerate(rows,2):
        for j,v in enumerate(row,1):
            if j in jsoncols:v=json.dumps(v,ensure_ascii=False,separators=(',',':'))
            k='b' if type(v) is bool else 'n' if type(v) in (float,int) else 'str'
            result[m.address(i,j)]={'kind':k,'value':Decimal(str(v)) if k=='n' else v,'formula':None,'text_format':False}
    return result


def source_fixture():
    # Use only saved synthetic dates. Never read actual published rows.
    cal=json.loads((Path(__file__).parents[1]/'tmp/dated_workbook_qa_20261003/path-chart-fixture.json').read_text(encoding='utf-8'))[0]['calendar']
    q={'numerator':'1','denominator':'1'};zero={'numerator':'0','denominator':'1'};r={'path':'saved','sha256':'a'*64,'json_pointer':'/value'}
    group={'risk_chain':'known','unknown':False,'members':[{'security_id':'SID:A'}],'saved_literal_sum':q,'normalized_display_share':q}
    agg={'rows':[group],'normalized_display_denominator':q,'stock_denominator_defined':True}
    t={'schema':'DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1','numerical_task_id':'a'*64,'calendar':cal,'original_task_summary_row':{'k':1,'weight_spec':{'kind':'equal'}},'series':{},'risk_tracks':{},'original_target_chain_evidence':{}}
    t.update({k:False for k in ('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','risk_chains_reaggregated','account_executed','winner_selected')})
    for role in m.ROLES:t['series'][role]={'status':'AVAILABLE','source_reference':r,'slots':[{'session':d,'exact_value':q,'display_value':1.0,'display_status':'FINITE_BINARY64'} for d in cal]}
    for role in m.ROLES[:4]:t['risk_tracks'][role]={'status':'AVAILABLE','source_reference':r,'rows':[{'session':d,'aggregation':agg,**({'cash_usd_preserved':0,'cash_fraction_display':zero} if role.endswith('integer') else {})} for d in cal]}
    for role in ('candidate','incumbent'):t['original_target_chain_evidence'][role]={'aggregation':agg,'source_evidence':{'source_reference':r}}
    tables={'任务索引':cells([[1,'ID: '+'a'*64,1,{'kind':'equal'},'AVAILABLE','a'*64]],(4,)),
    '候选路径':cells([[d,1.0,1.0,q,q,'FINITE_BINARY64','FINITE_BINARY64'] for d in cal],(4,5)),
    '共享路径':cells([[d,1.0,1.0,1.0,1.0,q,q,q,q] for d in cal],(6,7,8,9))}
    details=[];sources=[];coords=[]
    order=[('candidate_target',None),('incumbent_target',None)]+[(role,day) for day in range(127) for role in m.ROLES[:4]]
    for sourceid,(role,day) in enumerate(order):
        target=day is None;integerday=not target and role.endswith('integer');who=role.split('_')[0]
        details.append(['共享' if not target and role.startswith('incumbent') else 1,'ID: '+'a'*64,role,'原目标固定' if target else cal[day],'known',False,q,1.0,q,1.0,q,True,0 if integerday else None,0.0 if integerday else m.MISSING,'SID:A',sourceid,'SAVED_ORIGINAL_TARGET' if target else 'AVAILABLE'])
        sources.append([sourceid,'ID: '+'a'*64,role,'原目标' if target else cal[day],'/original_target_chain_evidence/'+who if target else f'/risk_tracks/{role}/rows/{day}',r])
    for day,d in enumerate(cal):
        row=[1,d]
        for idx in (0,1,2+4*day,3+4*day,4+4*day,5+4*day):
            role,at=order[idx];row += [1,idx+2,1,'SAVED_ORIGINAL_TARGET' if at is None else 'AVAILABLE',m.literal(q),0.0 if at is not None and role.endswith('integer') else m.MISSING]
        coords.append(row)
    tables['风险明细001']=cells(details,(7,9,11,13));tables['风险定位001']=cells(coords);tables['风险来源001']=cells(sources,(6,))
    return {'sheets':tables,'charts':[],'native_links':[]},t


class Tests(unittest.TestCase):
    def test_zip_encodings_formulas_and_zero_underflow(self):
        raw=xlsx('<c r="A1" t="inlineStr" s="1"><is><t>123456789012345678901234567890</t></is></c><c r="B1" t="s" s="2"><v>0</v></c><c r="C1" t="b"><v>0</v></c><c r="D1"><v>0</v></c>', '<si><t>=literal</t></si>')
        w=m.read_workbook(raw);expected={'sheets':[{'name':'表','ranges':[{'range':'A1:D1','values':[['123456789012345678901234567890','=literal',False,0.0]]}]}]}
        self.assertEqual(m.inspect_expected_cells(w,expected,{'charts':[]})['checked_cell_count'],4)
        self.assertTrue(w['sheets']['表']['B1']['text_format'])
        for mutation in ('underflow','formula','extra','type'):
            bad=copy.deepcopy(w)
            if mutation=='underflow':bad['sheets']['表']['D1']['value']=Decimal('1e-400')
            elif mutation=='formula':bad['sheets']['表']['D1']['formula']='1-1'
            elif mutation=='extra':bad['sheets']['表']['E1']=copy.deepcopy(bad['sheets']['表']['A1'])
            else:bad['sheets']['表']['A1']['kind']='n'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):m.inspect_expected_cells(bad,expected,{'charts':[]})

    def test_formula_sidecar_cannot_mask_extra_formula_or_error(self):
        raw=xlsx('<c r="A1" t="e"><f>NA()</f><v>#N/A</v></c>');w=m.read_workbook(raw)
        rec=[{'worksheet':'表','start_row_zero_based':0,'start_column_zero_based':0,'row_count':1,'column_count':1,'values':[['#N/A']],'formulas':[['=NA()']]}]
        m.inspect_capture_records(w,rec,{'charts':[]})
        w['sheets']['表']['A1']['value']='#REF!'
        with self.assertRaises(ValueError):m.inspect_capture_records(w,rec,{'charts':[]})
        with self.assertRaises(ValueError):m.read_workbook(xlsx('<c r="A1"><v>1</v></c><c r="A1"><v>2</v></c>'))

    def test_source_projection_full127_groups_and_identity_not_self_report(self):
        w,t=source_fixture();out=m.inspect_saved_source_tables(w,[t],[t['numerical_task_id']]);self.assertEqual(out['risk_detail_rows'],510);self.assertFalse(out['chart_graph_semantics_verified'])
        for sheet,cell,value in [('任务索引','F2','wrong'),('共享路径','D128',Decimal('2')),('风险明细001','O510','SID:wrong'),('风险明细001','G2','{"numerator":"0","denominator":"1"}'),('风险定位001','K128',999)]:
            bad=copy.deepcopy(w);bad['sheets'][sheet][cell]['value']=value
            with self.subTest(sheet=sheet,cell=cell),self.assertRaises(ValueError):m.inspect_saved_source_tables(bad,[t],[t['numerical_task_id']])
        bad=copy.deepcopy(w);del bad['sheets']['候选路径']['B128']
        with self.assertRaises(ValueError):m.inspect_saved_source_tables(bad,[t],[t['numerical_task_id']])

    def test_native_navigation_all1632_and_no_swapped_package(self):
        ids=[f'{i:064x}' for i in range(1632)];packages=[]
        for p,start in enumerate(range(0,1632,32)):
            packages.append({'package_index':p,'filename':f'package-{p+1:04d}.xlsx','start_task_ordinal':start,'stop_task_ordinal':start+32,'tasks':[{'task_ordinal':i,'numerical_task_id':ids[i],'local_task_number':i-start+1,'navigation_row':i-start+2} for i in range(start,start+32)]})
        links=m.expected_navigation_links(packages,ids);self.assertEqual(len(links),1632);self.assertEqual(links[-1]['location'],"'任务索引'!A33")
        packages[0]['tasks'][0]['numerical_task_id']=ids[1]
        with self.assertRaises(ValueError):m.expected_navigation_links(packages,ids)

    def test_static_graph_role_owner_selector_and_all127_sources(self):
        w,t=source_fixture();report=m.inspect_saved_source_tables(w,[t],[t['numerical_task_id']]);g=m.static_graph_contract(1,report)
        w['sheets']['路径查看']={};w['sheets']['风险查看']={}
        for (sheet,a),v in g['literals'].items():w['sheets'][sheet][a]={'kind':'n' if type(v)is int else 'str','value':Decimal(v) if type(v)is int else v,'formula':None}
        for (sheet,a),v in g['formulas'].items():w['sheets'][sheet][a]={'kind':'n','value':None,'formula':v}
        w['charts']=[dict(c,part=f'xl/charts/chart{i+1}.xml') for i,c in enumerate(g['charts'])]
        w['validations']={s:[{'sqref':'B4','type':'whole','operator':'between','formula1':'1','formula2':str(n)}] for s,n in [('路径查看',1),('风险查看',127)]}
        self.assertEqual(g['formulas'][('风险查看','B3')],"'路径查看'!B4")
        self.assertEqual(g['charts'][0]['series'][2]['formula'],'路径查看!F49:F175')
        self.assertEqual(g['charts'][1]['series'][0]['formula'],'路径查看!D49:D175')
        self.assertTrue(m.inspect_static_chart_graph(w,[t],[t['numerical_task_id']])['static_chart_source_graph_verified'])
        for attack in ('owner','series','selector','taskselector','range'):
            bad=copy.deepcopy(w)
            if attack=='owner':bad['charts'][0]['worksheet']='风险查看'
            elif attack=='series':bad['charts'][0]['series'][0]['formula']='路径查看!C49:C175'
            elif attack=='selector':bad['sheets']['风险查看']['B3']['formula']="'路径查看'!B5"
            elif attack=='taskselector':bad['sheets']['路径查看']['B4']['value']=Decimal(2)
            else:bad['sheets']['路径查看']['B175']['formula']=bad['sheets']['路径查看']['B175']['formula'].replace('*127+127','*127+126')
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_static_chart_graph(bad,[t],[t['numerical_task_id']])

    def test_same_target_values_different_task_sources_stay_separate(self):
        w,t=source_fixture();other=copy.deepcopy(t);other['numerical_task_id']='b'*64
        for who in ('candidate','incumbent'):other['original_target_chain_evidence'][who]['source_evidence']['source_reference']={'path':'different-input','sha256':'b'*64,'json_pointer':'/targets/'+who}
        tasks=[t,other];observed=[]
        # Capture independently computed projections only to assert distinct source
        # semantics; exact 127/table values already have the manual fixture oracle.
        from unittest.mock import patch
        def capture(workbook,name,rows,json_columns=()):observed.append((name,copy.deepcopy(rows)));return 0
        with patch.object(m,'source_table',side_effect=capture):
            # Expected page names are structural, not generated by this callback.
            result=m.inspect_saved_source_tables(w,tasks,[x['numerical_task_id'] for x in tasks])
        sources=dict(observed)['风险来源001'];targets=[r for r in sources if r[2]=='incumbent_target']
        self.assertEqual(len(targets),2);self.assertNotEqual(targets[0][5],targets[1][5]);self.assertEqual(targets[1][1],'ID: '+'b'*64)
        self.assertEqual(len([r for r in sources if r[2]=='incumbent_integer']),127)
        self.assertEqual(result['risk_detail_rows'],766)

    def test_ooxml_chart_worksheet_ownership_is_followed_not_assumed(self):
        original=xlsx('<c r="A1"><v>1</v></c>')
        with zipfile.ZipFile(io.BytesIO(original)) as z:parts={n:z.read(n) for n in z.namelist()}
        parts['xl/worksheets/sheet1.xml']=f'<worksheet xmlns="{m.M}" xmlns:r="{m.R}"><sheetData/><drawing r:id="draw"/></worksheet>'.encode()
        parts['xl/worksheets/_rels/sheet1.xml.rels']=f'<Relationships xmlns="{m.P}"><Relationship Id="draw" Type="{m.R}/drawing" Target="../drawings/drawing1.xml"/></Relationships>'.encode()
        parts['xl/drawings/drawing1.xml']=f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:c="{m.C}" xmlns:r="{m.R}"><xdr:twoCellAnchor><c:chart r:id="chart"/></xdr:twoCellAnchor></xdr:wsDr>'.encode()
        parts['xl/drawings/_rels/drawing1.xml.rels']=f'<Relationships xmlns="{m.P}"><Relationship Id="chart" Type="{m.R}/chart" Target="../charts/chart7.xml"/></Relationships>'.encode()
        parts['xl/charts/chart7.xml']=f'<c:chartSpace xmlns:c="{m.C}" xmlns:a="{m.A}"><c:chart><c:title><c:tx><a:t>test</a:t></c:tx></c:title><c:plotArea><c:lineChart><c:ser><c:cat><c:strRef><c:f>表!A1:A2</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>表!B1:B2</c:f></c:numRef></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>'.encode()
        def pack():
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for n,b in parts.items():z.writestr(n,b)
            return out.getvalue()
        chart=m.read_workbook(pack())['charts'][0];self.assertEqual((chart['worksheet'],chart['chart_ordinal'],chart['part'],chart['title']),('表',0,'xl/charts/chart7.xml','test'))
        parts['xl/worksheets/sheet1.xml']=f'<worksheet xmlns="{m.M}"><sheetData/></worksheet>'.encode()
        with self.assertRaisesRegex(ValueError,'owned'):m.read_workbook(pack())

if __name__=='__main__':unittest.main()
