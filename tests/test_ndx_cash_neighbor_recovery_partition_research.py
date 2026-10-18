import unittest
from copy import deepcopy
from backtest import ndx_cash_neighbor_recovery_partition_research as m

def fixture():
    lengths=[929]*278+[931,1000]+[1000]*41+[155,155,154]
    queue=[];groups=[];offset=0
    for index,length in enumerate(lengths):
        ids=[format(i,'064x') for i in range(offset,offset+length)]
        queue.append(dict(global_shard_index=index,global_task_start=offset,global_task_stop=offset+length,shard=dict(start=0,stop=length)))
        groups.append(ids);offset+=length
    ids=[i for group in groups for i in group]
    statuses={key:[] for key in m.SAVED};statuses['INFEASIBLE']=ids[:259355];statuses['RAW_SAVED_POSTCHECK_MISSING']=[ids[259355]];statuses['UNDISPATCHED']=ids[259356:]
    partition=dict(task_ids_by_saved_status=statuses,counts={k:len(v) for k,v in statuses.items()},dispatch_authorized=False)
    sidecar=dict(status='PASS_SAVED_RAW_ARITHMETIC_ONLY',saved_arithmetic_independently_verified=True,task_id=ids[259355],independent_postcheck={'outcome':'INFEASIBLE'},evaluator_called=False,dispatch_authorized=False,global_task_position=259355)
    return queue,groups,partition,sidecar

class DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=fixture()
    def test_exact_domain_original_tail(self):
        result=m.build_recovery_segments(*self.data)
        self.assertEqual(len(result['segments']),45)
        self.assertEqual(result['segments'][0]['original_task_start'],163)
        self.assertEqual(result['recovery_task_count'],42301)
    def test_same_count_swapped_old_id_or_reordered_suffix_rejected(self):
        for attack in ('old','order'):
            data=deepcopy(self.data);g=data[2]['task_ids_by_saved_status']
            if attack=='old':g['UNDISPATCHED'][0],g['INFEASIBLE'][0]=g['INFEASIBLE'][0],g['UNDISPATCHED'][0]
            else:g['UNDISPATCHED'][0],g['UNDISPATCHED'][1]=g['UNDISPATCHED'][1],g['UNDISPATCHED'][0]
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.build_recovery_segments(*data)

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.segment=dict(original_task_start=163,original_task_stop=165,task_ids=['a'*64,'b'*64],original_descriptor=dict(global_task_start=259193,global_task_stop=259358,shard=dict(start=46000,stop=46165)))
    def seal(self,stages):
        lines=[];previous='0'*64;position=163
        for index,(stage,payload) in enumerate(stages):
            row=m.make_record(sequence=index,previous_hash=previous,registration_sha256='c'*64,segment=self.segment,task_position=position,stage=stage,payload=payload)
            lines.append(m.encode(row)+b'\n');previous=row['record_sha256']
            if stage=='POSTCHECK':position+=1
        return b''.join(lines)
    def read(self,raw):return m.inspect_recovery_journal(raw,segment=self.segment,registration_sha256='c'*64)
    def test_start_and_raw_never_retry(self):
        for stages,status in [([('TASK_STARTED',{})],'UNRESOLVED_DISPATCH'),([('TASK_STARTED',{}),('RAW_RETURNED',{})],'RAW_SAVED_POSTCHECK_MISSING')]:
            result=self.read(self.seal(stages));self.assertEqual(result['active']['status'],status);self.assertEqual(result['undispatched_task_ids'],['b'*64])
    def test_partial_raw_bytes_preserve_unknown_and_completed_prefix(self):
        raw=self.seal([('TASK_STARTED',{}),('RAW_RETURNED',{}),('POSTCHECK',{'outcome':'INFEASIBLE'})])+b'{'
        result=self.read(raw);self.assertEqual(result['active']['original_task_position'],164);self.assertEqual(result['undispatched_task_ids'],[]);self.assertEqual(result['tail']['byte_count'],1)
    def test_technical_stop_no_next_dispatch(self):
        raw=self.seal([('TASK_STARTED',{}),('RAW_EXCEPTION',{}),('POSTCHECK',{'outcome':'EVALUATION_EXCEPTION'}),('TASK_STARTED',{})])
        with self.assertRaises(ValueError):self.read(raw)
    def test_wrong_chain_or_original_position_rejected(self):
        raw=self.seal([('TASK_STARTED',{})])
        for changed in (raw.replace(b'259356',b'259357'),raw.replace(b'"record_sequence":0',b'"record_sequence":true')):
            with self.assertRaises(ValueError):self.read(changed)

if __name__=='__main__':unittest.main()
