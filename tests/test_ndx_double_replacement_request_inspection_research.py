import unittest
from copy import deepcopy
from backtest import ndx_double_replacement_request_inspection_research as reader


def plan(count=513,size=512):
    document=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_PLAN_V1',preparation_reference=dict(path='synthetic',sha256='1'*64),prepared_content_sha256='2'*64,scenario_count=1,pair_count=1,financial_integer_count_before_issuer=count,structurally_excluded_integer_count=0,integer_count=count,batch_size=size,batch_count=(count+size-1)//size,**reader.PLAN_FLAGS)
    return dict(document=document,content_sha256=reader.digest(document))


class RequestInspectionTests(unittest.TestCase):
    def outcomes(self,p,count):
        rows=[]
        for index in range(count):
            d=reader.expected_descriptor(p,index);rows.append(dict(descriptor=d,point_runs=[dict(start=d['start'],stop=d['stop'],status='inspected_infeasible')]))
        return rows

    def test_original_complete_large_domain_and_tail(self):
        for size,tail,batches in ((512,297,102357),(10000,6569,5241)):
            p=plan(52406569,size)
            self.assertEqual(p['document']['batch_count'],batches)
            self.assertEqual(reader.expected_descriptor(p,batches-1)['point_count'],tail)
        p=plan(52406569,10000);rows=self.outcomes(p,5241)
        result=reader.partition(p,rows)
        self.assertTrue(result['full_domain_complete']);self.assertEqual(result['counts']['inspected_infeasible'],52406569)
        self.assertFalse(reader.partition(p,rows[:-1])['full_domain_complete'])

    def test_missing_duplicate_reordered_and_resigned_wrong_full_rejected(self):
        p=plan();rows=self.outcomes(p,2)
        for bad in (list(reversed(rows)),[rows[0],rows[0]],rows[1:]):
            with self.assertRaises(ValueError):reader.partition(p,bad)
        saved=dict(plan=p,batch_outcomes=rows[:1],partition=reader.partition(p,rows[:1]))
        saved['partition']['full_domain_complete']=True
        with self.assertRaises(ValueError):reader.inspect_request_partition(plan=p,verified_batch_outcomes=rows[:1],saved_request=saved)

    def test_technical_and_unknown_preserve_full_tail(self):
        p=plan();d=reader.expected_descriptor(p,0)
        for status in ('evaluation_exception','supplied_not_evaluated_technical','validation_failure_returned','unresolved_dispatch_or_raw'):
            rows=[dict(descriptor=d,point_runs=[dict(start=0,stop=512,status=status)])]
            result=reader.partition(p,rows)
            self.assertFalse(result['full_domain_complete']);self.assertEqual(result['counts'][status],512);self.assertEqual(result['counts']['undispatched'],1)
            with self.assertRaises(ValueError):reader.partition(p,rows+self.outcomes(p,2)[1:])

    def test_numeric_runs_exact_task_identity_and_bool_rejected(self):
        p=plan(2);d=reader.expected_descriptor(p,0);plans=[dict(global_ordinal=i,task=dict(task_id=str(i)))for i in range(2)]
        raw=dict(results=[dict(supplied_index=i,plan=t,status='FEASIBLE')for i,t in enumerate(plans)])
        inspection=dict(status='PASS_SAVED_RESULT_EVIDENCE',supplied_plan_count=2)
        self.assertEqual(reader.numeric_runs(d,plans,raw,inspection),[dict(start=0,stop=2,status='inspected_feasible')])
        raw['results'][0]['supplied_index']=False
        with self.assertRaises(ValueError):reader.numeric_runs(d,plans,raw,inspection)


if __name__=='__main__':unittest.main()
