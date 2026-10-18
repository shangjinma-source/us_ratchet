from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile,unittest
from scripts import ndx_registered_scoring_selection_20261003 as m


def record_fixture():
    rows=[]
    for i,stage in enumerate(('TASK_STARTED','RAW_SCORE','POSTCHECK')):
        payload={'original':'not score'} if i!=1 else dict(call_invoked=True,returned=True,returned_call_count=1,error=None,result_preserved_as_json=True,result={'weights':[0,.25,.75],'saved':'exact'})
        r=dict(schema='REGISTERED_SCORING_JOURNAL_RECORD_V1',sequence=i,previous_record_sha256='0'*64,context_sha256='a'*64,task_id='b'*64,task_position=0,stage=stage,payload=payload);r['record_sha256']=m.sha(m.enc(r));rows.append(r)
    lines=[m.enc(r)+b'\n' for r in rows];blob=b''.join(lines)
    loc=dict(sequence=1,byte_start=len(lines[0]),byte_stop=len(lines[0])+len(lines[1]),record_sha256=rows[1]['record_sha256'],stage='RAW_SCORE')
    return blob,m.ref('/synthetic/journal.jsonl',m.sha(blob)),[('b'*64,loc)]

class Tests(unittest.TestCase):
    def test_future_pins_before_io(self):
        with patch.object(m,'BOUND',{'request':(None,None)}),patch.object(m.Path,'read_bytes',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'anchors pending'):m.run(execute=True)

    def test_stream_original_result_and_nonselected_tail_hash(self):
        blob,r,e=record_fixture();result=list(m.read_scored_records(BytesIO(blob),r,e));self.assertEqual(result[0][1]['weights'],[0,.25,.75])
        changed=blob.replace(b'not score',b'bad value')
        for bad in (changed,blob[:-2],blob+b'{}\n'):
            with self.subTest(bad=bad[-15:]),self.assertRaises(ValueError):list(m.read_scored_records(BytesIO(bad),r,e))

    def test_locator_task_order_and_exact_types(self):
        blob,r,e=record_fixture()
        for attack in ('task','seq','hash','start','duplicate'):
            bad=deepcopy(e)
            if attack=='task':bad[0]=('c'*64,bad[0][1])
            elif attack=='seq':bad[0][1]['sequence']=True
            elif attack=='hash':bad[0][1]['record_sha256']='d'*64
            elif attack=='start':bad[0][1]['byte_start']+=1
            else:bad+=deepcopy(bad)
            with self.assertRaises(ValueError):list(m.read_scored_records(BytesIO(blob),r,bad))

    def test_raw_invalid_adapter_return_durable_before_failure_and_no_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'new';bound={'request':('/fixed/result','a'*64)}
            docs={'budget':{'plan':{}}};refs={k:{'path':'/x','sha256':'a'*64} for k in ('budget','budget_audit','policy')}
            adapter=SimpleNamespace(assemble_registered_selector_inputs=lambda **k:None)
            with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',output),patch.object(m,'load_metadata',return_value=(docs,refs,{},[],0)),patch.object(m,'source_sets'),patch.object(m,'resource_gate'),patch.object(m,'compile_bound',return_value=adapter),patch.object(m,'project_scores',return_value=[]):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertIsNone(m.loads((output/'raw_inputs.json').read_bytes())['result'])
                self.assertTrue((output/'failure.json').exists());self.assertFalse((output/'publication.json').exists())
                with self.assertRaisesRegex(ValueError,'immutable'):m.run(execute=True)

    def test_explicit_full_domain_resource_gate(self):
        with patch.object(m,'available_memory',return_value=5*1024**3+32*100),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=6*1024**3)):
            m.resource_gate(100)
            with self.assertRaisesRegex(ValueError,'Insufficient memory'):m.resource_gate(101)
            with self.assertRaisesRegex(ValueError,'no topN'):m.resource_gate(m.MAX_SCORE_BYTES+1)

    def test_return_persistence_bypasses_late_resource_gate_and_bad_repr(self):
        class Broken:
            def __repr__(self):raise RuntimeError('repr failed')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'raw.json'
            with patch.object(m,'resource_gate',side_effect=ValueError('low RAM now')):
                m.preserve_return(p,'RAW',{'original':[0,1]}, {},{})
            self.assertEqual(m.loads(p.read_bytes())['result'],{'original':[0,1]})
            p=Path(temp)/'broken.json'
            with self.assertRaises(TypeError):m.preserve_return(p,'RAW',Broken(),{}, {})
            d=m.loads(p.read_bytes());self.assertTrue(d['representation_unavailable']);self.assertEqual(d['representation_error'],'repr failed')

    def test_fixed_private_source_and_same_byte_consumption(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'module.py';b=b'VALUE=17\n';p.write_bytes(b)
            with patch.object(m,'CODES',{'adapter':(str(p),m.sha(b))}):
                self.assertEqual(m.compile_bound('adapter',{}).VALUE,17)
                p.write_bytes(b'VALUE=99\n')
                with self.assertRaisesRegex(ValueError,'consumed'):m.compile_bound('adapter',{})

if __name__=='__main__':unittest.main()
