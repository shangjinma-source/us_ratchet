from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_registered_scoring_queue_independent_readback_20261003 as m
from backtest import ndx_registered_scoring_journal_inspection_research as protocol
from backtest import ndx_registered_scoring_journal_research as producer_journal
from test_ndx_registered_scoring_journal_inspection_research import fixture


def shard_fixture(outcome=protocol.SUCCESS,external=False):
    kw,args,records=fixture(outcome,external)
    check=protocol.inspect_scoring_journal(**kw)
    descriptor=dict(shard_index=0,execution_start=0,execution_stop=1,logical_ordinals=[1632],job_ids=[kw['expected_jobs'][0]['job_id']])
    base=dict(context_reference=dict(path='/context',sha256='a'*64),queue_reference=dict(path='/queue',sha256='b'*64))
    started=dict(schema='REGISTERED_SCORING_SHARD_STARTED_V1',descriptor=descriptor,context_sha256=kw['context_sha256'],context_references=base,started_at_utc='2026-10-03T01:00:00+00:00',**m.FALSE)
    recovery=producer_journal.inspect_journal(kw['journal_bytes'],context_sha256=kw['context_sha256'],ordered_task_ids=descriptor['job_ids'])
    result=dict(schema='REGISTERED_SCORING_SHARD_RESULT_V1',status='COMPLETE' if outcome==protocol.SUCCESS else 'STOPPED',descriptor=descriptor,context_sha256=kw['context_sha256'],recovery=recovery,error=None if outcome==protocol.SUCCESS else dict(type='RuntimeError',message='saved error',traceback='trace'),logical_job_count=19584,source_blocked_job_count=9792,registered_executable_job_count=9792,known_external_first_job_count=1,whole_queue_completed=False,**m.FALSE)
    return kw,args,check,descriptor,base,started,result

class Tests(unittest.TestCase):
    def test_future_anchor_before_io(self):
        with patch.object(m,'REQUEST_RESULT_PATH',None),patch.object(m,'REQUEST_RESULT_SHA',None),patch.object(m.Path,'read_bytes',side_effect=AssertionError('IO forbidden')):
            with self.assertRaisesRegex(ValueError,'anchor pending'):m.readback(execute=True)

    def test_full_success_failure_external_recovery(self):
        for outcome,external in ((protocol.SUCCESS,False),('NUMERICAL_EXCEPTION',False),(protocol.SUCCESS,True)):
            kw,args,check,d,base,start,result=shard_fixture(outcome,external)
            m.inspect_shard_metadata(result,start,d,kw['context_sha256'],base,check,kw['journal_bytes'])
            for key in ('logical_job_count','known_external_first_job_count'):
                bad=deepcopy(result);bad[key]=True
                with self.assertRaises(ValueError):m.inspect_shard_metadata(bad,start,d,kw['context_sha256'],base,check,kw['journal_bytes'])
            bad=deepcopy(result);bad['recovery']['tasks'][0]['status']='SCORED_PENDING_INDEPENDENT_READBACK' if external else 'EXTERNALLY_REFERENCED'
            with self.assertRaises(ValueError):m.inspect_shard_metadata(bad,start,d,kw['context_sha256'],base,check,kw['journal_bytes'])

    def test_shard_physical_source_and_no_numeric_dispatch_for_external(self):
        kw,args,check,d,base,start,result=shard_fixture(external=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'shards'/'0000';directory.mkdir(parents=True)
            def saved(name,value):
                p=directory/name;b=value if type(value) is bytes else m.enc(value);p.write_bytes(b);return m.ref(p,m.sha(b))
            result['started_reference']=saved('started.json',start);result['journal_reference']=saved('journal.jsonl',kw['journal_bytes']);r=saved('result.json',result)
            c=dict(parents=dict(rolling_fitter_manifest=dict(runtime_versions=kw['expected_runtime'])),firstrefs=kw['external_first_evidence'])
            with patch.object(m,'QUEUE_ROOT',root):
                out=m.audit_shard(r,d,c,base,kw['context_sha256'],dict(logical_jobs=[{}]*1632+kw['expected_jobs']),protocol,object())
                self.assertEqual(out['verified_new_success_count'],0);self.assertEqual(out['inspection']['external_reference_count'],1)
                (directory/'extra').write_bytes(b'x')
                with self.assertRaisesRegex(ValueError,'namespace'):m.audit_shard(r,d,c,base,kw['context_sha256'],{},protocol,object())

    def test_numeric_source_identity_and_full_independent_score(self):
        from backtest import ndx_registered_scoring_result_inspection_research as numeric
        kw,args,check,d,base,start,result=shard_fixture()
        a=args['assembled'];job=a['registered_job_preserved']
        c=dict(parents=dict(budget=dict(plan=dict(rows=[dict(mode_plans=[{},dict(tasks=[job])])])),target_inputs=args['target_inputs'],rolling_fitter_manifest=dict(source_hashes=args['numerical_source_hashes']),original8_inputs=dict(scoring_inputs=args['original8_inputs'])),refs=dict(budget=a['budget_reference'],rolling_fitter_manifest=a['fitter_reference']),bindings={x['coordinate']['security_id']:x for x in args['channel_bindings']})
        result=m.inspect_numeric_tasks(kw['journal_bytes'],check,dict(path='/journal',sha256=m.sha(kw['journal_bytes'])),kw['expected_jobs'],c,numeric)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['inspection']['status'],'PASS')
        self.assertEqual(set(result[0]['score_reference']['record_locator']),{'sequence','byte_start','byte_stop','record_sha256','stage'})
        c['refs']['budget']=dict(path='/wrong',sha256='f'*64)
        with self.assertRaises(ValueError):m.inspect_numeric_tasks(kw['journal_bytes'],check,{},kw['expected_jobs'],c,numeric)

    def test_same_raw_hash_return_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'bytes';p.write_bytes(b'known');r=m.ref(p,m.sha(b'known'));sources={}
            with patch.object(m.Path,'read_bytes',side_effect=[b'known',b'changed']) as read:
                self.assertEqual(m.take_attempt(r,sources),b'known');self.assertEqual(read.call_count,1)
            with self.assertRaises(ValueError):m.merge(sources,m.ref(p,'e'*64))

class FullDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_ndx_registered_scoring_queue_research import Tests as fixture_class
        from backtest import ndx_registered_scoring_queue_research as producer
        fixture_class.setUpClass();cls.plan=fixture_class.plan;cls.reference=fixture_class.reference
        cls.queue=producer.build_registered_scoring_queue(budget_plan=cls.plan,budget_reference=cls.reference)

    def test_full19584_9792_306_original_order(self):
        q=self.queue;first=q['first_executable_job']['job_id']
        with patch.object(m,'TASK_ID',first):
            jobs=m.inspect_queue(q,self.plan,self.reference);self.assertEqual(len(jobs),19584)
            for attack in ('swap','denominator','strict_removed','shard'):
                bad=deepcopy(q)
                if attack=='swap':bad['logical_jobs'][0],bad['logical_jobs'][1]=bad['logical_jobs'][1],bad['logical_jobs'][0]
                elif attack=='denominator':bad['source_blocked_job_count']=False
                elif attack=='strict_removed':bad['source_blocked_logical_ordinals'].pop()
                else:bad['shards'][-1]['job_ids'].pop()
                bad['content_sha256']=m.digest({k:v for k,v in bad.items() if k!='content_sha256'})
                with self.assertRaises(ValueError):m.inspect_queue(bad,self.plan,self.reference)

    def test_engineering_zero_and_missing_result_preserve_full_partition(self):
        q=self.queue;ids=[q['logical_jobs'][i]['job_id'] for i in q['executable_logical_ordinals']];first=ids[0]
        base=dict(context_reference={'path':'context','sha256':'a'*64},queue_reference={'path':'queue','sha256':'b'*64})
        started=dict(schema='REGISTERED_SCORING_REQUEST_STARTED_V1',context_references=base,context_sha256='a'*64,completed_references=[],max_new_shards=0,started_at_utc='2026-10-03T01:00:00+00:00',**m.FALSE)
        r=dict(schema='REGISTERED_SCORING_REQUEST_RESULT_V1',status='ENGINEERING_BUDGET_STOP',context_references=base,context_sha256='a'*64,initial_completed_references=[],new_shard_references=[],completed_shard_references=[],unresolved_shard_index=None,unresolved_shard_reference=None,current_shard_terminal_tasks=[],unresolved_task_ids=[],undispatched_new_task_ids=ids[1:],known_external_first_job_count=1,known_external_first_job_id=first,logical_job_count=19584,source_blocked_job_count=9792,executable_job_count=9792,new_numerical_job_denominator=9791,completed_new_job_count=0,whole_queue_completed=False,error=None,**m.FALSE)
        with patch.object(m,'TASK_ID',first):
            out=m.inspect_request(r,started,q,[]);self.assertEqual(out['undispatched_count'],9791)
            r.update(status='STOPPED',unresolved_shard_index=0,unresolved_task_ids=ids[1:32],undispatched_new_task_ids=ids[32:],error={'type':'OSError','message':'write failed','traceback':'original'})
            out=m.inspect_request(r,started,q,[]);self.assertEqual(out['unresolved_count'],31);self.assertTrue(out['unresolved_without_result_metadata_only'])
            r['completed_new_job_count']=False
            with self.assertRaises(ValueError):m.inspect_request(r,started,q,[])

if __name__=='__main__':unittest.main()
