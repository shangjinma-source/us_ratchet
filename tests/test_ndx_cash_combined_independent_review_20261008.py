from copy import deepcopy
import json
import unittest
from backtest import ndx_cash_neighbor_combined_inspection_research as subject
from test_ndx_cash_neighbor_combined_inspection_research import fixture


def reseal(rows):
    previous='0'*64
    for row in rows:
        row.pop('record_sha256',None)
        row['previous_record_sha256']=previous
        row['record_sha256']=subject.digest(row)
        previous=row['record_sha256']
    return b''.join(subject.encode(row)+b'\n' for row in rows)


class IndependentCombinedReview(unittest.TestCase):
    def test_malformed_context_and_task_hash_rejected_even_resigned(self):
        for attack in ('context','task'):
            args=fixture();rows=[json.loads(line) for line in args['raw'].splitlines()]
            if attack=='context':
                args['context']='not-a-hash'
                for row in rows:row['registration_sha256']='not-a-hash'
            else:
                args['tasks'][1]['task_id']='not-a-task-id'
                for row in rows:
                    if row['original_shard_task_position']==1:row['task_id']='not-a-task-id'
            args['raw']=reseal(rows)
            with self.subTest(attack=attack),self.assertRaises(ValueError):subject.inspect_span(**args)

    def test_partial_sidecar_substitution_cannot_hide_score_or_locator(self):
        for attack in ('score','task','global','context','journal','typed_flag'):
            args=fixture(False);sidecar=args['sidecar']
            if attack=='score':sidecar['independent_postcheck']['original_target_stock_weight_l1']={'distance':0}
            elif attack=='task':sidecar['task_id']='f'*64
            elif attack=='global':sidecar['global_task_position']+=1
            elif attack=='context':sidecar['context_sha256']='a'*64
            elif attack=='journal':sidecar['journal_sha256']='d'*64
            else:sidecar['original_postcheck_existed']=0
            with self.subTest(attack=attack),self.assertRaises(ValueError):subject.inspect_span(**args)

    def test_resigned_technical_or_repeated_triplet_not_economic_pass(self):
        for attack in ('exception','technical','repeat','bool_position'):
            args=fixture();rows=[json.loads(line) for line in args['raw'].splitlines()]
            if attack=='exception':rows[1]['stage']='RAW_EXCEPTION'
            elif attack=='technical':rows[2]['payload']['outcome']='VALIDATION_FAILURE'
            elif attack=='repeat':rows=rows[:3]+deepcopy(rows[:3])
            else:rows[0]['original_shard_task_position']=True
            args['raw']=reseal(rows)
            with self.subTest(attack=attack),self.assertRaises(ValueError):subject.inspect_span(**args)

    def test_callback_count_and_no_input_mutation(self):
        for recovery in (False,True):
            args=fixture(recovery);before=deepcopy({k:v for k,v in args.items() if not callable(v)})
            callback=args['independent_result'];calls=[]
            def counted(value):calls.append(deepcopy(value));return callback(value)
            args['independent_result']=counted
            report=subject.inspect_span(**args)
            self.assertEqual(len(calls),3 if not recovery else 2)
            self.assertEqual(before,{k:v for k,v in args.items() if not callable(v)})
            self.assertEqual(report['sidecar_arithmetic_rechecked_count'],int(not recovery))


if __name__=='__main__':unittest.main()
