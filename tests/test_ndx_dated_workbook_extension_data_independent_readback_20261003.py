import copy,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts import ndx_dated_workbook_extension_data_independent_readback_20261003 as m
from test_ndx_dated_workbook_extension_data_20261003 import streams,core,m as producer
from test_ndx_dated_workbook_extension_tables_research import classification,classification_fixture


def fixture():
    pb,cb,p,c,s,a=streams();output=[];offset=0
    def emit(b):
        nonlocal offset
        loc=dict(record_index=len(output),byte_start=offset,byte_stop=offset+len(b),row_sha256=m.sha(b));offset+=len(b);output.append(b);return loc
    index=producer.stream_display(io.BytesIO(pb),io.BytesIO(cb),p,c,s,a,core,emit)
    shared=dict(schema='DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1',series=index.pop('shared_series'),risk=index.pop('shared_risk'),**m.OUT_FLAGS)
    blob=b''.join(output);index['task_jsonl_reference']=dict(path='unused-output',sha256=m.sha(blob),record_count=1632,byte_count=len(blob))
    return pb,cb,blob,p,c,index,s,a,shared

def check(f):
    pb,cb,blob,p,c,index,s,a,shared=f
    return m.inspect_streams(io.BytesIO(pb),io.BytesIO(cb),io.BytesIO(blob),p,c,index,s,a,shared)

def rewrite_first(f,mutate):
    pb,cb,blob,p,c,index,s,a,shared=f;lines=blob.splitlines(keepends=True);row=json.loads(lines[0]);mutate(row);lines[0]=m.enc(row)+b'\n';offset=0
    for i,line in enumerate(lines):
        index['task_index'][i]['jsonl_record']=dict(record_index=i,byte_start=offset,byte_stop=offset+len(line),row_sha256=m.sha(line));offset+=len(line)
    blob=b''.join(lines);index['task_jsonl_reference'].update(sha256=m.sha(blob),byte_count=len(blob));return pb,cb,blob,p,c,index,s,a,shared

class Tests(unittest.TestCase):
    def test_synthetic1632_shared_once_package_complete(self):
        out=check(fixture());self.assertEqual(out['planned_tasks'],1632);self.assertEqual(out['projected_tasks'],1);self.assertEqual(out['missing_tasks'],1631);self.assertEqual(out['shared_series'],4);self.assertEqual(out['shared_risk'],2)

    def test_resigned_output_cannot_change_value_evidence_or_zero(self):
        for mutate in (lambda r:r['series']['candidate_continuous']['slots'][0].update(display_value=99),lambda r:r['series']['candidate_integer']['slots'][0].update(exact_value=None),lambda r:r['original_target_evidence'].clear(),lambda r:r['preserved_evidence_sidecars'].clear()):
            f=rewrite_first(fixture(),mutate)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):check(f)

    def test_shared_false_classification_and_package_tamper(self):
        f=fixture();f[-1]['series'][next(iter(f[-1]['series']))]['series']['slots'][0]['display_value']=5
        with self.assertRaises(ValueError):check(f)
        f=fixture();f[5]['package_plan']['packages'][0]['estimated_bytes']+=1
        with self.assertRaises(ValueError):check(f)
        cov=classification.summarize_saved_classification(**classification_fixture());out=core.project_classification(cov);m.inspect_classification(out,cov);out['rows'][0]['wiring_row_reference']['json_pointer']='/wrong'
        with self.assertRaises(ValueError):m.inspect_classification(out,cov)

    def test_tail_missing_boolean_and_display_underflow(self):
        f=list(fixture());f[0]+=b'{}\n'
        with self.assertRaises(ValueError):check(f)
        f=list(fixture());f[3]['task_index'][0]['k']=True
        with self.assertRaises(ValueError):check(f)
        self.assertEqual(m.number('1e-400')['display_status'],'OUTSIDE_DISPLAY_PRECISION');self.assertEqual(m.number(None)['display_value'],None)
        with self.assertRaises(ValueError):m.number(False)

    def test_future_anchors_no_io_and_nonretry_namespace(self):
        with patch.object(m,'INDEX_SHA',None), patch.object(Path,'read_bytes',side_effect=AssertionError('read')):
            with self.assertRaises(ValueError):m.load()
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)),patch.object(m,'load',side_effect=AssertionError('load')):
            with self.assertRaises(ValueError):m.run(execute=True)
        with self.assertRaises(ValueError):m.merge({'a':'1'*64},m.reference('a','2'*64))

if __name__=='__main__':unittest.main()
