from pathlib import Path
import json,tempfile,unittest
from scripts import ndx_dated_comparison_batch_20261003 as module
from test_ndx_dated_comparison_batch_20261003 import fixture

class Tests(unittest.TestCase):
    def test_initial_items_interleaved_original_queue_order(self):
        a=fixture();initial=[r['numerical_task_id'] for r in a['summary']['rows'][:3]]
        rows=a['summary']['rows'][3:]
        for at,tid in zip((0,18,36),initial):rows.insert(at,dict(numerical_task_id=tid))
        a['summary']['rows']=rows
        ids,refs=module.validate_queue(**a)
        self.assertEqual(ids,[r['numerical_task_id'] for r in rows]);self.assertEqual(len(refs),1632)
        self.assertEqual([t for t in ids if t not in initial],[r['numerical_task_id'] for r in a['economic_result']['new_completed_rows']])

    def test_predispatch_guard_not_classified_as_attempt(self):
        calls=[];checks=[0]
        def guard():
            checks[0]+=1
            if checks[0]==2:raise ValueError('Base source changed before any callback')
        def forbidden(*args):calls.append(True);raise AssertionError('Unexpected dispatch')
        with tempfile.TemporaryDirectory() as tmp:
            ref=module.execute_queue(['a'*64,'b'*64],initial_rows=[],stage_functions=dict.fromkeys(module.STAGES,forbidden),verify_sources=guard,output=Path(tmp)/'out')
            r=json.loads(Path(ref['path']).read_bytes());self.assertEqual(calls,[]);self.assertEqual(r['undispatched_task_ids'],['a'*64,'b'*64]);self.assertEqual(r['unresolved_task_ids'],[]);self.assertFalse(r['failure']['current_stage_invoked'])

    def test_resource_boundary_and_progress_stage_references(self):
        for capacity,expected in [(module.MIN_FREE_BYTES,1),(module.MIN_FREE_BYTES-1,0),(True,0)]:
            with self.subTest(capacity=capacity),tempfile.TemporaryDirectory() as tmp:
                calls=[]
                def invoke(stage):
                    def callback(tid,refs):
                        calls.append(stage)
                        if stage=='independent_readback':self.assertEqual(set(refs),{'comparison'})
                        return dict(path=stage,sha256='a'*64)
                    return callback
                folder=Path(tmp)/'out';ref=module.execute_queue(['a'*64],initial_rows=[],stage_functions={s:invoke(s) for s in module.STAGES},verify_sources=lambda:None,resource_check=lambda:capacity,output=folder)
                result=json.loads(Path(ref['path']).read_bytes());self.assertEqual(result['new_completed_count'],expected)
                self.assertEqual(calls,list(module.STAGES) if expected else [])
                events=[json.loads(line) for line in (folder/'progress.jsonl').read_bytes().splitlines()]
                if expected:self.assertEqual([e['stage'] for e in events if e['status']=='REFERENCE_RETURNED'],list(module.STAGES))

if __name__=='__main__':unittest.main()
