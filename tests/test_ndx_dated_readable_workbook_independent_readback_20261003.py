"""Synthetic ZIP layout and source-bound fixture; no actual exports or reader run."""
from copy import deepcopy
from io import BytesIO
import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
from scripts import ndx_dated_comparison_workbook_readable_independent_readback_20261003 as m


def presentation():
    tables=[dict(name='表'+str(i),headers=['a'],rows=[['x']]) for i in range(4)]
    tables += [dict(name='原始目标权重',headers=['a','b','c','证券ID'],rows=[['x','x','x','security:long:literal:001']]),dict(name='来源索引',headers=['a','b','c'],rows=[['x','E:/保存来源/'+str(i)+'/'+'path'*35,'x'] for i in range(5)])]
    return dict(schema='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1',display=dict(tables=tables),source_hashes={},input_references={},**dict.fromkeys(m.FALSE+('promotion_allowed','point_in_time_verified','workbook_created'),False))


def xlsx(p,attack=None):
    plan=m.expected_layout(p);ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    parts={'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{t["name"]}" sheetId="{i+1}" r:id="r{i}"/>' for i,t in enumerate(p['display']['tables']))+'</sheets></workbook>',
        'xl/_rels/workbook.xml.rels':'<Relationships>'+''.join(f'<Relationship Id="r{i}" Target="worksheets/s{i}.xml"/>' for i in range(6))+'</Relationships>',
        'xl/styles.xml':f'<styleSheet xmlns="{ns}"><cellXfs><xf numFmtId="49"><alignment wrapText="0"/></xf><xf numFmtId="49"><alignment wrapText="1"/></xf></cellXfs></styleSheet>'}
    for i,t in enumerate(p['display']['tables']):
        col=4 if i==4 else 2;width=plan['security_id']['width'] if i==4 else 100
        if attack=='width' and i==4:width=28
        cols=f'<cols><col min="{col}" max="{col}" width="{width}" customWidth="1"/></cols>' if i>=4 else ''
        rows=[]
        for n,r in enumerate(t['rows'],5):
            height=plan['source_paths']['rows'][n-5]['height'] if i==5 else 25
            if attack=='height' and i==5 and n==9:height=25
            style=1 if i==5 else 0
            if attack=='wrap' and i==5 and n==5:style=0
            c=('D' if i==4 else 'B')+str(n)
            rows.append(f'<row r="{n}" ht="{height}" customHeight="1"><c r="{c}" t="inlineStr" s="{style}"><is><t>test</t></is></c></row>')
        parts[f'xl/worksheets/s{i}.xml']=f'<worksheet xmlns="{ns}">{cols}<sheetData>{"".join(rows)}</sheetData></worksheet>'
    if attack=='disabled_alignment':
        parts['xl/styles.xml']=parts['xl/styles.xml'].replace('<cellXfs>', '<cellStyleXfs><xf numFmtId="49"><alignment wrapText="1"/></xf></cellStyleXfs><cellXfs>').replace('<xf numFmtId="49"><alignment wrapText="0"/>','<xf numFmtId="49" xfId="0" applyAlignment="0"><alignment wrapText="0"/>')
    b=BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name,value in parts.items():z.writestr(name,value)
    return b.getvalue()


def setup(root):
    export=root/'export';export.mkdir();refs={};p=presentation()
    def write(name,value):
        b=value if type(value) is bytes else m.encode(value);path=root/name;path.write_bytes(b);return dict(path=str(path),sha256=m.digest(b))
    for role in ('builder','layout','exporter'):refs[role]=write(role,b'authenticated but not executed')
    refs['core']=write('core',b"def inspect_export(x,p):return {'status':'PASS','layout':'ACTUAL_FIXED_ROW4'}")
    refs['style_core']=write('style',b"def inspect_text_styles(x,p):return {'status':'PASS'}")
    refs['presentation']=write('presentation.json',p)
    pub=dict(schema='DATED_COMPARISON_PRESENTATION_PUBLICATION_V1',status='PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY',presentation_reference=refs['presentation'],source_hashes={},**dict.fromkeys(m.FALSE+('promotion_allowed','point_in_time_verified','workbook_created'),False))
    refs['publication']=write('publication.json',pub)
    wb=write('export/条件历史比较.xlsx',xlsx(p));d=write('export/条件历史比较.xlsx.inspect.ndjson',b'not-json\x00\xff')
    manifest=dict(schema='DATED_COMPARISON_READABLE_WORKBOOK_EXPORT_V1',status='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',workbook_reference=wb,layout_adjustments=m.expected_layout(p),runtime_diagnostic_attachment=dict(status='OBSERVED_RUNTIME_DIAGNOSTIC_ATTACHMENT',reference=d,byte_count=10,manifest_bound=True,content_interpreted=False,numeric_input=False),input_references={k:refs[k] for k in ('presentation','publication','builder','layout')},source_hashes={refs[k]['path']:refs[k]['sha256'] for k in ('exporter','presentation','publication','builder','layout')},runtime_bundle='26.909.12148',in_memory_table_values_verified=True,exported_cell_values_independently_verified=False,visual_acceptance_passed=False,known_preview_limitation=m.LIMITATION,**dict.fromkeys(m.FALSE,False))
    manifest['previews']=[]
    for i,t in enumerate(p['display']['tables']):
        r=write(f'export/preview_{i}.png',b'png fixture');r.update(sheet=t['name'],range=f'A1:{chr(64+len(t["headers"]))}{min(len(t["rows"])+4,18)}');manifest['previews'].append(r)
    refs['manifest']=write('export/export_manifest.json',manifest);write('export/started.json',{})
    return refs,export,manifest,p,pub


class Tests(unittest.TestCase):
    def test_layout_same_data_and_mutations(self):
        p=presentation();plan=m.expected_layout(p)
        self.assertEqual(m.inspect_readable_layout(xlsx(p),p,plan)['checked_layout_cell_count'],6)
        for attack in ('width','wrap','height','disabled_alignment'):
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_readable_layout(xlsx(p,attack),p,plan)
        bad=deepcopy(plan);bad['security_id']['width']=28
        with self.assertRaises(ValueError):m.inspect_readable_layout(xlsx(p,'width'),p,bad)

    def test_physical_source_closure_and_no_visual_claim(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);refs,export,*_=setup(root)
            with patch.object(m,'BOUND',refs),patch.object(m,'EXPORT',export),patch.object(m,'OUTPUT',root/'out'):
                ref=m.readback(execute=True);r=json.loads(Path(ref['path']).read_bytes())
                self.assertFalse(r['visual_acceptance_passed']);self.assertFalse(r['final_delivery_accepted'])
                self.assertTrue(r['runtime_inspection_attachment']['manifest_bound']);self.assertFalse(r['runtime_inspection_attachment']['content_interpreted'])
                with self.assertRaises(ValueError):m.readback(execute=True)

    def test_attachment_scope_and_post_drift_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);refs,export,manifest,*_=setup(root);original=m.save
            def drift(path,value):
                r=original(path,value)
                if path.name=='independent_readback.json':Path(manifest['runtime_diagnostic_attachment']['reference']['path']).write_bytes(b'changed')
                return r
            with patch.object(m,'BOUND',refs),patch.object(m,'EXPORT',export),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'save',drift):
                wrong=deepcopy(manifest['runtime_diagnostic_attachment']);wrong['reference']['path']=str(root/'arbitrary.ndjson')
                with self.assertRaises(ValueError):m.authenticate_runtime_attachment(wrong)
                with self.assertRaises(ValueError):m.readback(execute=True)
                self.assertTrue((root/'out/failure.json').exists())
                with self.assertRaises(ValueError):m.readback(execute=True)

    def test_pending_and_sources(self):
        refs=deepcopy(m.BOUND);refs['manifest']['sha256']=None
        with patch.object(m,'BOUND',refs),patch.object(Path,'read_bytes',side_effect=AssertionError('pending IO')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        with tempfile.TemporaryDirectory() as t:
            refs,export,manifest,p,pub=setup(Path(t));manifest['source_hashes'].pop(refs['layout']['path'])
            with patch.object(m,'EXPORT',export),self.assertRaises(ValueError):m.validate(manifest,p,pub,refs)

if __name__=='__main__':unittest.main()
