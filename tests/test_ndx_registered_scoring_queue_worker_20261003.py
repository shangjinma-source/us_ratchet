import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
from unittest.mock import patch
from contextlib import ExitStack
from backtest import ndx_registered_scoring_journal_research as journalcore
P=Path(__file__).resolve().parents[1]/'scripts/ndx_registered_scoring_queue_worker_20261003.py'
spec=importlib.util.spec_from_file_location('registered_worker_test',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    tid='a'*64
    d=dict(job_id=tid,cutoff='2026-03-31',weight_spec='equal_weight',logical_ordinal=1)
    jobs=[dict(d,job_id=m.FIRST_ID,logical_ordinal=0),d]
    shard=dict(shard_index=0,execution_start=0,execution_stop=2,logical_ordinals=[0,1],job_ids=[m.FIRST_ID,tid],content_sha256='d'*64)
    q=dict(content_sha256='c'*64,shards=[shard],logical_jobs=jobs,executable_logical_ordinals=[0,1],logical_job_count=4,source_blocked_job_count=2,executable_job_count=2)
    assembled=dict(job_id=tid,status='ASSEMBLED_NOT_DISPATCHED',rolling_inputs={},reducer_inputs={},ordered_securities=[])
    fit=dict(schema='MULTIDECISION_CAUSAL_ROLLING_FITS_V1',windows=[{} for _ in range(13)],securities=[],cutoff=d['cutoff'],weight_spec=d['weight_spec'],source_hashes={},**dict.fromkeys(('source_bytes_authenticated','outer_lane_prior_applied','score_computed','point_in_time_verified','account_executed','promotion_allowed'),False))
    c=dict(queue=q,journal=journalcore,refs={},sources={},code_sources={},first_refs={'independent_readback':{'path':'synthetic','sha256':'b'*64}},manifest={'source_hashes':{}},first=SimpleNamespace(runtime=lambda:{}),modules=dict(assembler=SimpleNamespace(assemble_registered_scoring_job_inputs=lambda **kw:assembled),rolling=SimpleNamespace(fit_causal_scoring_windows=lambda **kw:fit),reducer=SimpleNamespace(reduce_fitted_scoring_windows=lambda **kw:{'score':1}),inspector=SimpleNamespace(inspect_fitted_scoring_windows=lambda **kw:{'status':'PASS'})))
    return c


class Tests(unittest.TestCase):
    def setup_context(self,tmp,c):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(m,'OUTPUT',Path(tmp)/'out'))
        stack.enter_context(patch.object(m,'FRESH_CLI',True))
        for name in ('code_guard','common_guard','space'):stack.enter_context(patch.object(m,name,return_value=None))
        stack.enter_context(patch.object(m,'environment',return_value={}))
        stack.enter_context(patch.object(m,'job_arguments',return_value={}))
        stack.enter_context(patch.dict(m._COMMON,{'test':c},clear=True))
    def test_durable_dispatch_external_and_explicit_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=fixture();self.setup_context(tmp,c);original=c['modules']['rolling'].fit_causal_scoring_windows
            def fit(**kw):
                rows=[m.loads(x) for x in (m.OUTPUT/'shards/0000/journal.jsonl').read_bytes().splitlines()]
                self.assertEqual(rows[-1]['stage'],'FIT_DISPATCH');self.assertEqual(rows[0]['stage'],'EXTERNAL_REFERENCE')
                return original(**kw)
            c['modules']['rolling'].fit_causal_scoring_windows=fit
            r=m.run_shard(0,common='test',execute=True);result=m.loads(Path(r['path']).read_bytes())
            self.assertEqual(result['status'],'COMPLETE');self.assertEqual(len(result['recovery']['tasks']),2)
            with self.assertRaises(ValueError):m.run_shard(0,common='test',execute=True)
            self.assertEqual(m.run_shard(0,common='test',execute=True,completed_reference=r),r)
    def test_raw_none_exception_and_serialization_retained(self):
        for mode in ('none','exception','object'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                c=fixture();self.setup_context(tmp,c)
                def fit(**kw):
                    if mode=='exception':raise RuntimeError('actual synthetic error')
                    return None if mode=='none' else object()
                c['modules']['rolling'].fit_causal_scoring_windows=fit
                r=m.run_shard(0,common='test',execute=True);result=m.loads(Path(r['path']).read_bytes())
                rows=[m.loads(x) for x in (Path(r['path']).parent/'journal.jsonl').read_bytes().splitlines()]
                raw=next(x['payload'] for x in rows if x['stage']=='RAW_FIT')
                self.assertEqual(raw['returned'],mode!='exception');self.assertEqual(result['status'],'STOPPED')
                self.assertNotIn('SCORE_DISPATCH',[x['stage'] for x in rows])
                if mode=='object':self.assertFalse(raw['result_preserved_as_json']);self.assertIn('representation_sha256',raw)
                with self.assertRaises(ValueError):m.run_shard(0,common='test',execute=True,completed_reference=r)
    def test_post_return_drift_preserves_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=fixture();self.setup_context(tmp,c);called=[False];original=c['modules']['rolling'].fit_causal_scoring_windows
            def fit(**kw):called[0]=True;return original(**kw)
            def guard(_):
                if called[0]:raise ValueError('runtime drift')
            c['modules']['rolling'].fit_causal_scoring_windows=fit
            with patch.object(m,'code_guard',side_effect=guard):
                with self.assertRaises(ValueError):m.run_shard(0,common='test',execute=True)
            rows=[m.loads(x) for x in (m.OUTPUT/'shards/0000/journal.jsonl').read_bytes().splitlines()]
            self.assertTrue(next(x['payload'] for x in rows if x['stage']=='RAW_FIT')['returned'])
            self.assertTrue((m.OUTPUT/'shards/0000/failure.json').exists())
    def test_resource_stop_preserves_external_and_full_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=fixture();self.setup_context(tmp,c);m.ensure_root(c)
            with patch.object(m,'space',side_effect=ValueError('resource')):
                r=m.run_batch(execute=True,common='test')
            result=m.loads(Path(r['path']).read_bytes())
            self.assertEqual(result['undispatched_new_task_ids'],['a'*64]);self.assertEqual(result['known_external_first_job_count'],1)
            self.assertEqual(result['source_blocked_job_count'],2);self.assertEqual(result['unresolved_task_ids'],[])
    def test_failed_shard_retains_batch_terminal_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=fixture();self.setup_context(tmp,c)
            def fail(**kw):raise RuntimeError('numerical original')
            c['modules']['rolling'].fit_causal_scoring_windows=fail
            r=m.run_batch(execute=True,common='test');result=m.loads(Path(r['path']).read_bytes())
            self.assertEqual(result['status'],'STOPPED');self.assertEqual(len(result['new_shard_references']),1)
            self.assertEqual(result['current_shard_terminal_tasks'][-1]['status'],'NUMERICAL_EXCEPTION')
            self.assertEqual(result['undispatched_new_task_ids'],[]);self.assertEqual(result['unresolved_task_ids'],[])
            self.assertEqual(result['completed_new_job_count'],0)

    def test_failed_inspection_preserves_report_and_terminal_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=fixture();self.setup_context(tmp,c)
            c['modules']['inspector'].inspect_fitted_scoring_windows=lambda **kw:{'status':'FAIL','reason':'saved diagnostic'}
            r=m.run_batch(execute=True,common='test');result=m.loads(Path(r['path']).read_bytes())
            self.assertEqual(result['status'],'STOPPED')
            self.assertEqual(result['current_shard_terminal_tasks'][-1]['status'],'VALIDATION_FAILURE')
            rows=[m.loads(x) for x in (m.OUTPUT/'shards/0000/journal.jsonl').read_bytes().splitlines()]
            self.assertEqual(next(x['payload']['inspection'] for x in rows if x['stage']=='INSPECTION'),{'status':'FAIL','reason':'saved diagnostic'})
            rows[-1]['payload']['outcome']=m.SUCCESS
            records=[];previous='0'*64
            for row in rows:
                row=journalcore.make_record(sequence=len(records),previous_hash=previous,context_sha256=row['context_sha256'],task_id=row['task_id'],task_position=row['task_position'],stage=row['stage'],payload=row['payload']);records.append(row);previous=row['record_sha256']
            with self.assertRaises(ValueError):journalcore.inspect_journal(b''.join(m.enc(x)+b'\n' for x in records),context_sha256=rows[0]['context_sha256'],ordered_task_ids=c['queue']['shards'][0]['job_ids'])

    def test_pending_pins_before_io_and_handle_injection(self):
        with patch.object(m,'JOURNAL_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaises(ValueError):m.load_common()
        with self.assertRaises(ValueError):m.context({})

if __name__=='__main__':unittest.main()
