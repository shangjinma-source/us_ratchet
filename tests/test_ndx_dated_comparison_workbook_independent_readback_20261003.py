from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from unittest import mock
from scripts import ndx_dated_comparison_workbook_independent_readback_20261003 as m
from test_ndx_dated_comparison_xlsx_inspection_research import fixture

def setup(root,layout='ACTUAL_FIXED_ROW4'):
    export=root/'export';export.mkdir();refs={}
    def write(name,obj):
        p=root/name;raw=obj if type(obj) is bytes else m.encode(obj);p.write_bytes(raw);return dict(path=str(p),sha256=m.digest(raw))
    refs['builder']=write('builder',b'not executed');refs['exporter']=write('exporter',b'not executed')
    refs['core']=write('core',f"def inspect_export(x,p):return {{'status':'PASS','layout':'{layout}'}}".encode())
    refs['style_core']=write('style_core',b"def inspect_text_styles(x,p):return {'status':'PASS'}")
    p=fixture();p.update(dict.fromkeys(('promotion_allowed','point_in_time_verified','workbook_created','economics_recomputed','formal_comparison_passed','future_independent_oos'),False));p['source_hashes']={};p['input_references']={}
    refs['presentation']=write('presentation.json',p)
    pub=dict(schema='DATED_COMPARISON_PRESENTATION_PUBLICATION_V1',status='PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY',presentation_reference=refs['presentation'],source_hashes={},**{k:p[k] for k in m.FALSE+('promotion_allowed','point_in_time_verified','workbook_created')})
    refs['publication']=write('publication.json',pub)
    wb=write('export/条件历史比较.xlsx',b'synthetic mocked parser bytes');previews=[]
    for i,t in enumerate(p['display']['tables']):
        r=write(f'export/preview_{i}.png',b'png mock');r.update(sheet=t['name'],range=f"A1:D{min(len(t['rows'])+4,18)}");previews.append(r)
    manifest=dict(schema='DATED_COMPARISON_WORKBOOK_EXPORT_V1',status='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',workbook_reference=wb,previews=previews,input_references={k:refs[k] for k in ('presentation','publication','builder')},source_hashes={refs[k]['path']:refs[k]['sha256'] for k in ('exporter','presentation','publication','builder')},runtime_bundle='26.909.12148',in_memory_table_values_verified=True,exported_cell_values_independently_verified=False,visual_acceptance_passed=False,known_preview_limitation=m.LIMITATION,**dict.fromkeys(m.FALSE,False))
    refs['manifest']=write('export/export_manifest.json',manifest);write('export/started.json',{})
    refs['runtime_inspection']=write('export/'+Path(wb['path']).name+'.inspect.ndjson',b'not json\x00\xff')
    return refs,export,manifest,p,pub

class Tests(unittest.TestCase):
    def test_pending_never_reads(self):
        refs=deepcopy(m.BOUND);refs['manifest']['sha256']=None
        with mock.patch.object(m,'BOUND',refs),mock.patch.object(Path,'read_bytes',side_effect=AssertionError('No actual IO')):
            with self.assertRaises(ValueError):m.readback(execute=True)
    def test_success_mock_core_and_no_visual_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs,export,*_=setup(Path(tmp));out=Path(tmp)/'out'
            with mock.patch.object(m,'BOUND',refs),mock.patch.object(m,'EXPORT',export),mock.patch.object(m,'OUTPUT',out),mock.patch.object(m,'RUNTIME_INSPECTION_SIZE',10):
                r=m.readback(execute=True);v=json.loads(Path(r['path']).read_bytes());self.assertFalse(v['visual_acceptance_passed']);self.assertFalse(v['final_delivery_accepted'])
                with self.assertRaises(ValueError):m.readback(execute=True)
    def test_synthetic_layout_failure_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs,export,*_=setup(Path(tmp),'SYNTHETIC_QA_FIXED_ROW4');out=Path(tmp)/'out'
            with mock.patch.object(m,'BOUND',refs),mock.patch.object(m,'EXPORT',export),mock.patch.object(m,'OUTPUT',out),mock.patch.object(m,'RUNTIME_INSPECTION_SIZE',10):
                with self.assertRaises(ValueError):m.readback(execute=True)
                self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):m.readback(execute=True)
    def test_contract_and_source_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs,export,manifest,p,pub=setup(Path(tmp))
            with mock.patch.object(m,'EXPORT',export):
                for key,value in [('visual_acceptance_passed',True),('economics_recomputed',0),('known_preview_limitation','removed')]:
                    bad=deepcopy(manifest);bad[key]=value
                    with self.assertRaises(ValueError):m.validate(bad,p,pub,refs)
                bad=deepcopy(manifest);bad['source_hashes'][refs['builder']['path']]='0'*64
                with self.assertRaises(ValueError):m.validate(bad,p,pub,refs)

if __name__=='__main__':unittest.main()
