import io,zipfile,unittest
from copy import deepcopy
from xml.sax.saxutils import escape
from backtest import ndx_dated_comparison_xlsx_inspection_research as m

def fixture():
    tables=[dict(name=n,headers=['文本','数值','缺失','布尔'],rows=[['6222659648236112670',0.12345678901234567,None,True],[' ',0.0,None,False]],percentage_columns=[1]) for n in m.SHEETS]
    return dict(schema='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1',display=dict(schema='DATED_COMPARISON_CHINESE_DISPLAY_TABLES_V1',tables=tables,**dict.fromkeys(('source_bytes_authenticated','economics_recomputed','formal_comparison_passed','future_independent_oos'),False)))

def package(p,encoding='inlineStr',custom=False,change=None):
    parts={};shared=[];sheets=[];relationships=[]
    for i,t in enumerate(p['display']['tables'],1):
        sheets.append(f'<sheet name="{t["name"]}" sheetId="{i}" r:id="r{i}"/>');relationships.append(f'<Relationship Id="r{i}" Type="{m.REL}/worksheet" Target="worksheets/sheet{i}.xml"/>')
        title='Nasdaq-100 条件历史研究' if i==1 else t['name']
        rows=[f'<row r="1"><c r="A1" t="str"><v>{title}</v></c></row>', '<row r="2"><c r="A2" t="str"><v>2026-03-20 至 2026-09-21｜单路径诊断；不授正式晋级或未来 OOS</v></c></row>']
        for ri,row in enumerate([t['headers']]+t['rows'],4):
            cells=[]
            for ci,v in enumerate(row):
                ref=chr(65+ci)+str(ri)
                if v is None:cells.append(f'<c r="{ref}"/>');continue
                if type(v) is str:
                    if encoding=='inlineStr':body='<is><t xml:space="preserve">'+escape(v)+'</t></is>'
                    elif encoding=='s':shared.append(v);body=f'<v>{len(shared)-1}</v>'
                    else:body='<v>'+escape(v)+'</v>'
                    cells.append(f'<c r="{ref}" s="1" t="{encoding}">{body}</c>')
                elif type(v) is bool:cells.append(f'<c r="{ref}" t="b"><v>{int(v)}</v></c>')
                else:cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            rows.append(f'<row r="{ri}">'+''.join(cells)+'</row>')
        parts[f'xl/worksheets/sheet{i}.xml']=f'<worksheet xmlns="{m.NS}"><sheetData>'+''.join(rows)+'</sheetData></worksheet>'
    parts['xl/workbook.xml']=f'<workbook xmlns="{m.NS}" xmlns:r="{m.REL}"><sheets>'+''.join(sheets)+'</sheets></workbook>'
    parts['xl/_rels/workbook.xml.rels']='<Relationships>'+''.join(relationships)+'</Relationships>'
    fm='<numFmts><numFmt numFmtId="164" formatCode="@"/></numFmts>' if custom else ''
    parts['xl/styles.xml']=f'<styleSheet xmlns="{m.NS}">{fm}<cellXfs><xf numFmtId="0"/><xf numFmtId="'+('164' if custom else '49')+'"/></cellXfs></styleSheet>'
    parts['xl/sharedStrings.xml']=f'<sst xmlns="{m.NS}">'+''.join('<si><t xml:space="preserve">'+escape(v)+'</t></si>' for v in shared)+'</sst>'
    if change:change(parts)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for k,v in parts.items():z.writestr(k,v)
    return out.getvalue()

class Tests(unittest.TestCase):
    def test_types_encodings_and_source_unchanged(self):
        p=fixture();before=deepcopy(p)
        for enc in ('inlineStr','s','str'):
            for custom in (False,True):
                r=m.inspect_export(package(p,enc,custom),p);self.assertEqual(r['sheet_count'],6);self.assertEqual(r['value_type_counts']['null'],12)
        self.assertEqual(p,before)
    def test_no_zero_for_null_or_extra_formula_or_error(self):
        p=fixture()
        mutations=[('<c r="C5"/>','<c r="C5"><v>0</v></c>'),('<c r="B5">','<c r="B5"><f>1</f>'),('<c r="B5">','<c r="B5" t="e">'),('</sheetData>','<row r="99"><c r="A99" t="str"><v>extra</v></c></row></sheetData>'),('6222659648236112670','6222659648236112000'),('<v>0.12345678901234566</v>','<v>0.2</v>')]
        for old,new in mutations:
            def change(parts):parts['xl/worksheets/sheet1.xml']=parts['xl/worksheets/sheet1.xml'].replace(old,new)
            with self.subTest(old=old),self.assertRaises(ValueError):m.inspect_export(package(p,change=change),p)
    def test_fixed_annotations_not_free_extra_cells(self):
        p=fixture()
        for old,new in [('Nasdaq-100 条件历史研究','未核研究'),('不授正式晋级或未来 OOS','正式通过'),('</sheetData>','<row r="3"><c r="A3" t="str"><v>hidden extra</v></c></row></sheetData>')]:
            def change(parts):parts['xl/worksheets/sheet1.xml']=parts['xl/worksheets/sheet1.xml'].replace(old,new)
            with self.assertRaises(ValueError):m.inspect_export(package(p,change=change),p)

    def test_tail_order_blank_space_and_numeric_types(self):
        p=fixture()
        for old,new in [('<row r="6">','<row r="7">'),(' t="b"',' t="n"'),('xml:space="preserve"> </t>','xml:space="preserve"></t>'),('<v>0.0</v>','<v>NaN</v>'),('<v>0.0</v>','<v>1e-400</v>')]:
            def change(parts):parts['xl/worksheets/sheet1.xml']=parts['xl/worksheets/sheet1.xml'].replace(old,new)
            with self.subTest(old=old),self.assertRaises(ValueError):m.inspect_export(package(p,change=change),p)
        def reorder(parts):parts['xl/workbook.xml']=parts['xl/workbook.xml'].replace('研究概览','wrong')
        with self.assertRaises(ValueError):m.inspect_export(package(p,change=reorder),p)

if __name__=='__main__':unittest.main()
