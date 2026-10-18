import unittest
from backtest import ndx_cash_topup_neighbor_journal_research as m

def journal(stages):
    records=[];prev=m.ZERO
    for stage,payload in stages:
        r=m.make_record(sequence=len(records),previous_hash=prev,context_sha256='c'*64,task_id='a'*64,task_position=0,stage=stage,payload=payload);records.append(r);prev=r['record_sha256']
    return b''.join(m.encode(r)+b'\n' for r in records)
class Tests(unittest.TestCase):
    def test_full_chain_and_each_crash_boundary(self):
        stages=[('TASK_STARTED',{'args':'bound'}),('RAW_RETURNED',{'result':{'complete':'raw'}}),('POSTCHECK',{'outcome':'INFEASIBLE'})]
        full=journal(stages)
        for n,status in [(1,'UNRESOLVED_DISPATCH'),(2,'RAW_SAVED_POSTCHECK_MISSING'),(3,'INFEASIBLE')]:
            r=m.inspect_journal(journal(stages[:n]),context_sha256='c'*64,ordered_task_ids=['a'*64]);self.assertEqual(r['tasks'][0]['status'],status);self.assertEqual(r['complete'],n==3)
        truncated=full[:-4];r=m.inspect_journal(truncated,context_sha256='c'*64,ordered_task_ids=['a'*64]);self.assertIsNotNone(r['tail']);self.assertFalse(r['complete']);self.assertEqual(r['tasks'][0]['status'],'RAW_SAVED_POSTCHECK_MISSING')
    def test_partial_any_stage_never_lists_uncertain_task_as_undispatched(self):
        choices=[[('TASK_STARTED',{})],[('EXTERNAL_REFERENCE',{})],[('TASK_STARTED',{}),('RAW_RETURNED',{})],[('TASK_STARTED',{}),('RAW_RETURNED',{}),('POSTCHECK',{'outcome':'FEASIBLE'})]]
        for stages in choices:
            raw=journal(stages)[:-5];before=bytes(raw);r=m.inspect_journal(raw,context_sha256='c'*64,ordered_task_ids=['a'*64,'b'*64])
            self.assertEqual(r['undispatched_task_ids'],['b'*64]);self.assertEqual(r['tasks'][0]['task_id'],'a'*64);self.assertFalse(r['complete']);self.assertEqual(raw,before)
            if len(stages)==1:self.assertEqual(r['tasks'][0]['reason'],'UNKNOWN_PARTIAL_RECORD')

    def test_hash_duplicate_exception_and_order(self):
        with self.assertRaises(ValueError):m.inspect_journal(journal([('TASK_STARTED',{}),('RAW_EXCEPTION',{}),('POSTCHECK',{'outcome':'INFEASIBLE'})]),context_sha256='c'*64,ordered_task_ids=['a'*64])
        b=journal([('EXTERNAL_REFERENCE',{})])
        with self.assertRaises(ValueError):m.inspect_journal(b+b,context_sha256='c'*64,ordered_task_ids=['a'*64])
        with self.assertRaises(ValueError):m.inspect_journal(b.replace(b'EXTERNAL_REFERENCE',b'TASK_STARTED'),context_sha256='c'*64,ordered_task_ids=['a'*64])
        r=m.inspect_journal(b,context_sha256='c'*64,ordered_task_ids=['a'*64,'b'*64]);self.assertEqual(r['undispatched_task_ids'],['b'*64]);self.assertEqual(r['tasks'][0]['status'],'EXTERNALLY_REFERENCED')
if __name__=='__main__':unittest.main()
