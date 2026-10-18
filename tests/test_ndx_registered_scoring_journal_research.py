import unittest
from backtest import ndx_registered_scoring_journal_research as m


class Tests(unittest.TestCase):
    def test_lifecycle_and_conservative_partial_tail(self):
        ids=['a'*64,'b'*64];records=[];previous=m.ZERO
        for stage,payload in [('TASK_STARTED',{}),('INPUTS',{}),('FIT_DISPATCH',{}),('RAW_FIT',dict(call_invoked=True,returned=True,returned_call_count=1,internal_optimizer_call_count=None)),('SCORE_DISPATCH',{}),('RAW_SCORE',dict(call_invoked=True,returned=True,returned_call_count=1,internal_optimizer_call_count=None)),('INSPECTION',dict(inspection=dict(status='PASS'))),('POSTCHECK',dict(outcome='SCORED_PENDING_INDEPENDENT_READBACK'))]:
            r=m.make_record(sequence=len(records),previous_hash=previous,context_sha256='c'*64,task_id=ids[0],task_position=0,stage=stage,payload=payload);records.append(r);previous=r['record_sha256']
        raw=b''.join(m.encode(r)+b'\n' for r in records);out=m.inspect_journal(raw,context_sha256='c'*64,ordered_task_ids=ids)
        self.assertEqual(out['undispatched_task_ids'],[ids[1]]);self.assertFalse(out['complete'])
        out=m.inspect_journal(raw+b'{',context_sha256='c'*64,ordered_task_ids=ids)
        self.assertEqual(out['undispatched_task_ids'],[]);self.assertEqual(out['unresolved_task_ids'],[ids[1]])
        out=m.inspect_journal(b'{',context_sha256='c'*64,ordered_task_ids=ids)
        self.assertEqual(out['unresolved_task_ids'],[ids[0]]);self.assertEqual(out['undispatched_task_ids'],[ids[1]])
        for end in range(1,len(records)):
            prefix=b''.join(m.encode(r)+b'\n' for r in records[:end]);out=m.inspect_journal(prefix+b'{',context_sha256='c'*64,ordered_task_ids=ids)
            self.assertEqual(out['unresolved_task_ids'],[ids[0]]);self.assertEqual(out['undispatched_task_ids'],[ids[1]])
    def test_fake_success_reordered_or_type_changed_rejected(self):
        r=m.make_record(sequence=0,previous_hash=m.ZERO,context_sha256='c'*64,task_id='a'*64,task_position=0,stage='TASK_STARTED',payload={})
        q=m.make_record(sequence=1,previous_hash=r['record_sha256'],context_sha256='c'*64,task_id='a'*64,task_position=0,stage='POSTCHECK',payload=dict(outcome='SCORED_PENDING_INDEPENDENT_READBACK'))
        with self.assertRaises(ValueError):m.inspect_journal(m.encode(r)+b'\n'+m.encode(q)+b'\n',context_sha256='c'*64,ordered_task_ids=['a'*64])
        r['task_position']=False
        with self.assertRaises(ValueError):m.inspect_journal(m.encode(r)+b'\n',context_sha256='c'*64,ordered_task_ids=['a'*64])

if __name__=='__main__':unittest.main()
