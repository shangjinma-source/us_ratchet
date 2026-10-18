import copy
import unittest
from backtest import ndx_cash_neighbor_combined_inspection_research as c


def fixture(recovery=True):
    tasks=[dict(task_id=str(i)*64) for i in range(3)]
    descriptor=dict(global_task_start=10,global_task_stop=13,shard=dict(path='X:/tasks',sha256='a'*64,start=20,stop=23))
    start=1 if recovery else 0
    rows=[];previous='0'*64
    detail=dict(outcome='INFEASIBLE',original_target_stock_weight_l1=None,evaluation_error=None,validation_error=None,score_absence_reason='TEST')
    for position in range(start,3):
        args=dict(position=position+20)
        source=dict(path='X:/tasks',sha256='a'*64,jsonl_line_index=position)
        payload=dict(task_reference=source,evaluation_argument_sha256=c.digest(args))
        if not recovery:source['scenario_candidate_ordinal']=20+position;payload['global_task_position']=10+position
        stages=[('TASK_STARTED',payload),('RAW_RETURNED',dict(result=dict(value=position+20),error=None,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=1))]
        if recovery or position!=2:stages.append(('POSTCHECK',detail))
        for stage,payload in stages:
            row=dict(schema='CASH_NEIGHBOR_RECOVERY_RECORD_V1'if recovery else'CASH_NEIGHBOR_JOURNAL_RECORD_V1',previous_record_sha256=previous,task_id=tasks[position]['task_id'],stage=stage,payload=payload)
            if recovery:row.update(record_sequence=len(rows),registration_sha256='b'*64,original_shard_task_position=position,original_global_task_position=10+position,scenario_candidate_ordinal=20+position)
            else:row.update(sequence=len(rows),context_sha256='b'*64,task_position=position)
            row['record_sha256']=c.digest(row);previous=row['record_sha256'];rows.append(row)
    raw=b''.join(c.encode(r)+b'\n'for r in rows)
    sidecar=None
    if not recovery:
        parsed=c.records(raw,recovery=False,context='b'*64)
        sidecar=dict(schema='CASH_NEIGHBOR_SAVED_RAW_INDEPENDENT_POSTCHECK_V1',status='PASS_SAVED_RAW_ARITHMETIC_ONLY',saved_arithmetic_independently_verified=True,evaluator_called=False,dispatch_authorized=False,original_journal_modified=False,original_postcheck_existed=False,promotion_allowed=False,journal_sha256=c.hashlib.sha256(raw).hexdigest(),context_sha256='b'*64,task_id=tasks[2]['task_id'],task_position=2,global_task_position=12,dispatch_record_reference=parsed[-2][1],raw_record_reference=parsed[-1][1],independent_postcheck=detail)
    return dict(raw=raw,tasks=tasks,prepared={},descriptor=descriptor,start=start,stop=3,context='b'*64,recovery=recovery,arguments=lambda p,t,n:dict(position=n),independent_result=lambda a:dict(value=a['position']),expected_detail=lambda p,r:copy.deepcopy(detail),sidecar=sidecar)


class Tests(unittest.TestCase):
    def test_original_coordinates_and_sidecar_recheck(self):
        for recovery,count in ((True,2),(False,3)):
            result=c.inspect_span(**fixture(recovery))
            self.assertEqual(result['task_count'],count)
            self.assertEqual(result['sidecar_arithmetic_rechecked_count'],int(not recovery))
    def test_resigned_wrong_arithmetic_and_source_coordinates(self):
        for key in ('result','coordinate','argument'):
            args=fixture();rows=[c.json.loads(l)for l in args['raw'].splitlines()]
            if key=='result':rows[1]['payload']['result']['value']=999
            elif key=='coordinate':rows[1]['original_global_task_position']=0
            else:rows[0]['payload']['evaluation_argument_sha256']='c'*64
            previous='0'*64
            for row in rows:
                row['previous_record_sha256']=previous;row.pop('record_sha256');row['record_sha256']=c.digest(row);previous=row['record_sha256']
            args['raw']=b''.join(c.encode(r)+b'\n'for r in rows)
            with self.subTest(key=key),self.assertRaises(ValueError):c.inspect_span(**args)
    def test_sidecar_wrong_locator_and_false_boolean_rejected(self):
        for key in ('locator','flag'):
            args=fixture(False)
            if key=='locator':args['sidecar']['raw_record_reference']['byte_start']+=1
            else:args['sidecar']['evaluator_called']=0
            with self.subTest(key=key),self.assertRaises(ValueError):c.inspect_span(**args)
    def test_missing_tail_and_extra_record_rejected(self):
        for transform in (lambda b:b[:-1],lambda b:b+b.splitlines(keepends=True)[-1]):
            args=fixture();args['raw']=transform(args['raw'])
            with self.assertRaises(ValueError):c.inspect_span(**args)
    def test_exact_combined_order(self):
        rows=[dict(task_id='a',outcome='EXTERNALLY_REFERENCED',new_arithmetic_checked=False),dict(task_id='b',outcome='FEASIBLE',new_arithmetic_checked=True)]
        self.assertEqual(c.merge_original_order(ordered_task_ids=['a','b'],blocks=[[rows[0]],[rows[1]]])['task_count'],2)
        for blocks in ([[rows[0]]],[[rows[1],rows[0]]],[[rows[0],rows[1],rows[1]]]):
            with self.assertRaises(ValueError):c.merge_original_order(ordered_task_ids=['a','b'],blocks=blocks)


if __name__=='__main__':unittest.main()
