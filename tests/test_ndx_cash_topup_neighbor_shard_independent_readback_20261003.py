from copy import deepcopy
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_cash_topup_neighbor_shard_independent_readback_20261003 as r
from test_ndx_cash_topup_neighbor_single_evaluation_20261003 import fixture
from backtest import ndx_cash_topup_neighbor_preparation_research as preparation


def shard_fixture(external=False):
    p,_=fixture();tasks=list(preparation.iter_neighbors(p,{}))[:2]
    descriptor=dict(scenario_index=0,shard_index=0,global_shard_index=0,global_task_start=0,global_task_stop=2,
        contract_reference=dict(path='contract.json',sha256='d'*64),shard=dict(path='tasks.jsonl',sha256='e'*64,start=0,stop=2))
    flags=dict.fromkeys(r.FALSE,False);started=dict(schema='CASH_NEIGHBOR_SHARD_STARTED_V1',descriptor=descriptor,context_sha256='c'*64,ordered_task_ids=[t['task_id'] for t in tasks],contract_sha256=p['contract_sha256'],**flags)
    oracle=r.fresh_oracle();records=[];ext={k:dict(path=k,sha256='a'*64) for k in ('first_started','first_raw','first_postcheck','first_audit')}
    for pos,t in enumerate(tasks):
        if external and pos==0:records.append(dict(task_position=pos,task_id=t['task_id'],stage='EXTERNAL_REFERENCE',payload=ext));continue
        args=r.task_arguments(p,t,pos);raw=oracle(args)
        start=dict(task_reference=dict(path='tasks.jsonl',sha256='e'*64,jsonl_line_index=pos,scenario_candidate_ordinal=pos),global_task_position=pos,evaluation_argument_sha256=r.digest(args))
        for stage,payload in [('TASK_STARTED',start),('RAW_RETURNED',dict(result=raw,error=None,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=1)),('POSTCHECK',r.expected_detail(p,raw))]:
            records.append(dict(task_position=pos,task_id=t['task_id'],stage=stage,payload=payload))
    return p,tasks,descriptor,started,records,ext,oracle


def seal(records,descriptor):
    previous='0'*64;offset=0;lines=[];indexes=[];counts=dict.fromkeys(('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED'),0)
    for i,row in enumerate(records):
        body=dict(schema='CASH_NEIGHBOR_JOURNAL_RECORD_V1',sequence=i,previous_record_sha256=previous,context_sha256='c'*64,**deepcopy(row));previous=r.digest(body);body['record_sha256']=previous
        blob=r.enc(body)+b'\n';lines.append(blob);indexes.append(dict(sequence=i,byte_start=offset,byte_stop=offset+len(blob),record_sha256=previous,task_id=row['task_id'],stage=row['stage']));offset+=len(blob)
        if row['stage']=='POSTCHECK':counts[row['payload']['outcome']]+=1
        elif row['stage']=='EXTERNAL_REFERENCE':counts['EXTERNALLY_REFERENCED']+=1
    completion=dict(schema='CASH_NEIGHBOR_SHARD_COMPLETION_V1',status='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED',descriptor=descriptor,context_sha256='c'*64,record_index=indexes,record_count=len(records),terminal_record_sha256=previous,task_count=2,outcome_counts=counts,new_evaluator_call_count=2-counts['EXTERNALLY_REFERENCED'],unresolved_dispatch_count=0,undispatched_count=0,**dict.fromkeys(r.FALSE,False))
    return completion,b''.join(lines)


def inspect(data):
    p,tasks,d,start,records,ext,oracle=data;c,raw=seal(records,d)
    return r.inspect_complete_shard(started=start,completion=c,journal_bytes=raw,tasks=tasks,prepared=p,descriptor=d,context_sha256='c'*64,external_references=ext,independent_result=oracle)


class Tests(unittest.TestCase):
    def test_all_records_exact_arithmetic_and_original_first_is_not_recomputed(self):
        data=shard_fixture(True);calls=[];oracle=data[-1]
        def counted(args):calls.append(args);return oracle(args)
        data=(*data[:-1],counted)
        with patch.object(r,'FIRST_ID',data[1][0]['task_id']):result=inspect(data)
        self.assertEqual(len(calls),1);self.assertEqual(result['task_count'],2);self.assertEqual(result['record_count'],4)
        self.assertEqual(result['outcome_counts']['EXTERNALLY_REFERENCED'],1)
        self.assertFalse(result['task_results'][0]['new_arithmetic_checked'])

    def test_rehashed_finance_risk_score_argument_or_source_alias_rejected(self):
        for attack in ('gross','risk','l1','args','source','bool','extra'):
            data=list(shard_fixture());records=data[4]
            if attack=='gross':records[1]['payload']['result']['branches'][0]['evaluated_plans'][0]['fees_usd']='0'
            elif attack=='risk':records[1]['payload']['result']['branches'][0]['evaluated_plans'][0]['risk']['all_passed']=False
            elif attack=='l1':records[2]['payload']['original_target_stock_weight_l1']['distance']['numerator']=999
            elif attack=='args':records[0]['payload']['evaluation_argument_sha256']='f'*64
            elif attack=='source':records[0]['payload']['task_reference']['jsonl_line_index']=1
            elif attack=='bool':records[1]['payload']['explicit_evaluator_call_attempt_count']=True
            else:records.append(deepcopy(records[-1]))
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspect(data)

    def test_partial_or_exception_is_not_complete_pass(self):
        data=shard_fixture();p,tasks,d,start,records,ext,oracle=data
        for remove in (1,2,3):
            changed=(*data[:4],records[:-remove],*data[5:])
            with self.assertRaises(ValueError):inspect(changed)
        c,raw=seal(records,d)
        with self.assertRaises(ValueError):r.inspect_complete_shard(started=start,completion=c,journal_bytes=raw[:-1],tasks=tasks,prepared=p,descriptor=d,context_sha256='c'*64,external_references=ext,independent_result=oracle)
        records[1]['stage']='RAW_EXCEPTION';records[1]['payload']=dict(result=None,error={'type':'Error','message':'saved'},explicit_evaluator_call_attempt_count=1,returned_evaluation_count=0)
        with self.assertRaises(ValueError):inspect(data)

    def test_complete_324_descriptors_full_denominator_and_tail_type(self):
        rows=[];left=301657;ordinal=0
        for i in range(40):
            shards=[];start=0
            for j in range(9 if i<4 else 8):
                count=(left+(324-ordinal)-1)//(324-ordinal);left-=count
                shards.append(dict(path=str(r.PREP/f'scenario-{i:02d}'/f'tasks-{j:05d}.jsonl'),sha256='a'*64,start=start,stop=start+count));start+=count;ordinal+=1
            rows.append(dict(scenario_id=str(i),contract_reference=dict(path=str(r.PREP/f'scenario-{i:02d}'/'contract.json'),sha256='b'*64),shards=shards,statistics=dict(new_candidate_count=start)))
        p=dict(schema='CASH_TOPUP_NEIGHBOR_PREPARATION_V1',scenario_count=40,rows=rows,task_evaluation_count=0,declared_local_neighborhood_complete=True,statistics=dict(new_candidate_count=301657))
        q=r.queue_from_preparation(p);self.assertEqual(len(q),324);self.assertEqual(q[-1]['global_task_stop'],301657)
        p['rows'][-1]['shards'][-1]['stop']=True
        with self.assertRaises(ValueError):r.queue_from_preparation(p)

    def test_pending_actual_pins_fail_before_any_source_read(self):
        with patch.object(r,'RESULT_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):r.readback(dict(path='never',sha256='a'*64),execute=True)
            read.assert_not_called()


if __name__=='__main__':unittest.main()
