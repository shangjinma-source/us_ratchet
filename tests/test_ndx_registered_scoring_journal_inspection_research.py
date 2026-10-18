from copy import deepcopy
import unittest
from backtest import ndx_registered_scoring_journal_inspection_research as m
from test_ndx_registered_scoring_result_inspection_research import fixture as numerical_fixture


def fixture(outcome=m.SUCCESS,external=False):
    args=numerical_fixture();tid=m.FIRST if external else args['assembled']['job_id'];context='a'*64
    descriptor=dict(job_id=tid,registered_status='PLANNED_NOT_ATTEMPTED',fx_mode='BACKWARD_LATEST_VALID_FX',weight_spec='equal_weight',cutoff='2026-03-31',holding_count=4,logical_ordinal=1632,execution_ordinal=0,decision_index=0,mode_index=1,task_index=0,job_pointer='/plan/rows/0/mode_plans/1/tasks/0')
    externalrefs={k:dict(path='/saved/'+k,sha256='b'*64) for k in ('postcheck','started','inputs','raw_fit','raw_score','score_inspection','independent_readback')}
    runtime=dict(python='synthetic',numpy='synthetic',pandas='synthetic',scipy='synthetic');metadata=dict(runtime=runtime,environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0));rows=[];refs=[]
    def add(stage,payload):
        row=dict(schema='REGISTERED_SCORING_JOURNAL_RECORD_V1',sequence=len(rows),previous_record_sha256=rows[-1]['record_sha256'] if rows else '0'*64,context_sha256=context,task_id=tid,task_position=0,stage=stage,payload=deepcopy(payload));row['record_sha256']=m.sha(m.encode(row));rows.append(row);refs.append(dict(sequence=row['sequence'],record_sha256=row['record_sha256']))
    if external:add('EXTERNAL_REFERENCE',externalrefs)
    else:
        add('TASK_STARTED',dict(descriptor=descriptor,started_at_utc='2026-10-03T01:00:00+00:00',fit_call_invoked=False,score_call_invoked=False));add('INPUTS',dict(assembled=args['assembled']));add('FIT_DISPATCH',metadata)
        raw=dict(call_invoked=True,returned=True,returned_call_count=1,internal_optimizer_call_count=None,result=args['saved_fit'],error=None,result_preserved_as_json=True,dispatch_metadata=metadata)
        if outcome=='NUMERICAL_EXCEPTION':raw.update(returned=False,returned_call_count=0,result=None,error=dict(type='RuntimeError',message='actual numerical error',traceback='trace'))
        add('RAW_FIT',raw)
        if outcome==m.SUCCESS:
            add('SCORE_DISPATCH',metadata);raw=deepcopy(raw);raw['result']=args['saved_score'];add('RAW_SCORE',raw);add('INSPECTION',dict(inspection=args['saved_score_inspection']))
        post=dict(outcome=outcome,record_references=deepcopy(refs),whole_queue_completed=False,**dict.fromkeys(m.FALSE,False))
        if outcome!=m.SUCCESS:post.update(failed_stage='FIT',error=dict(type='RuntimeError',message='saved exception',traceback='trace'))
        add('POSTCHECK',post)
    raw=b''.join(m.encode(r)+b'\n' for r in rows)
    kwargs=dict(journal_bytes=raw,context_sha256=context,expected_jobs=[descriptor],shard_index=0,expected_runtime=runtime,external_first_evidence=externalrefs)
    return kwargs,args,rows


def resign(rows):
    refs=[]
    for i,r in enumerate(rows):
        r['sequence']=i;r['previous_record_sha256']=rows[i-1]['record_sha256'] if i else '0'*64
        if r['stage']=='POSTCHECK':r['payload']['record_references']=deepcopy(refs)
        r['record_sha256']=m.sha(m.encode({k:v for k,v in r.items() if k!='record_sha256'}));refs.append(dict(sequence=i,record_sha256=r['record_sha256']))
    return b''.join(m.encode(r)+b'\n' for r in rows)


class Tests(unittest.TestCase):
    def test_full_success_and_separate_independent_arithmetic(self):
        kw,args,_=fixture();out=m.inspect_scoring_journal(**kw)
        self.assertTrue(out['whole_shard_terminal_evidence_complete']);self.assertEqual(out['numerical_success_claim_count'],1);self.assertFalse(out['numerical_arithmetic_independently_verified'])
        sources={k:args[k] for k in ('numerical_source_hashes','channel_bindings','original8_inputs','target_inputs')}
        audit=m.inspect_saved_success_numeric(journal_bytes=kw['journal_bytes'],inspection=out,task_id=args['assembled']['job_id'],numerical_sources=sources)
        self.assertEqual(audit['status'],'PASS');self.assertFalse(audit['optimization_rerun'])

    def test_exception_terminal_is_not_numeric_success(self):
        kw,_,_=fixture('NUMERICAL_EXCEPTION');out=m.inspect_scoring_journal(**kw)
        self.assertTrue(out['whole_shard_terminal_evidence_complete']);self.assertFalse(out['whole_shard_numeric_success_claims_complete']);self.assertEqual(out['numerical_success_claim_count'],0)
        self.assertEqual(out['status_counts'],{'NUMERICAL_EXCEPTION':1});self.assertFalse(out['automatic_retry_allowed'])

    def test_partial_raw_dispatch_and_first_partial_preserved(self):
        kw,_,rows=fixture()
        for count in (0,1,3,4,5,6):
            changed=deepcopy(kw);changed['journal_bytes']=b''.join(m.encode(r)+b'\n' for r in rows[:count])+b'{partial'
            out=m.inspect_scoring_journal(**changed);self.assertFalse(out['whole_shard_terminal_evidence_complete']);self.assertEqual(len(out['unresolved_task_ids']),1);self.assertEqual(out['undispatched_task_ids'],[]);self.assertFalse(out['bytes_truncated'])

    def test_invalid_returned_inputs_and_inspection_remain_failures(self):
        kw,_,rows=fixture()
        for body in (None,{'wrong':'original returned body'}):
            bad=deepcopy(rows[:2]+[rows[-1]])
            bad[1]['payload']['assembled']=body
            bad[-1]['payload'].update(outcome='VALIDATION_FAILURE',failed_stage='START',error=dict(type='ValueError',message='bad input return',traceback='original'))
            args=deepcopy(kw);args['journal_bytes']=resign(bad)
            out=m.inspect_scoring_journal(**args);self.assertEqual(out['status_counts'],{'VALIDATION_FAILURE':1});self.assertFalse(out['whole_shard_numeric_success_claims_complete'])
        bad=deepcopy(rows);bad[-2]['payload']['inspection']={'status':'FAILED'}
        bad[-1]['payload'].update(outcome='VALIDATION_FAILURE',failed_stage='INSPECTION',error=dict(type='ValueError',message='not pass',traceback='original'))
        kw['journal_bytes']=resign(bad);self.assertEqual(m.inspect_scoring_journal(**kw)['terminal_evidence_count'],1)
        bad[-1]['payload']={k:v for k,v in bad[-1]['payload'].items() if k not in ('failed_stage','error')};bad[-1]['payload']['outcome']=m.SUCCESS
        kw['journal_bytes']=resign(bad)
        with self.assertRaises(ValueError):m.inspect_scoring_journal(**kw)

    def test_resigned_order_types_runtime_and_external_attacks(self):
        kw,_,rows=fixture()
        for edit in (lambda x:x.pop(2),lambda x:x[2]['payload']['environment'].update(sys_flags_hash_randomization=True),lambda x:x[3]['payload'].update(returned_call_count=True),lambda x:x[-1]['payload'].update(point_in_time_verified=0),lambda x:x[-1]['payload'].update(outcome='NUMERICAL_EXCEPTION',failed_stage='FIT',error=dict(type='Error',message='not raised',traceback='none'))):
            r=deepcopy(rows);edit(r);bad=deepcopy(kw);bad['journal_bytes']=resign(r)
            with self.assertRaises(ValueError):m.inspect_scoring_journal(**bad)
        kw,_,rows=fixture(external=True);self.assertEqual(m.inspect_scoring_journal(**kw)['external_reference_count'],1)
        rows[0]['payload']['raw_fit']['sha256']='c'*64;kw['journal_bytes']=resign(rows)
        with self.assertRaises(ValueError):m.inspect_scoring_journal(**kw)


if __name__=='__main__':unittest.main()
