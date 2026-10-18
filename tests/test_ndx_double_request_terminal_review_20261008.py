import unittest
from backtest import ndx_double_replacement_request_inspection_research as reader
from test_ndx_double_replacement_request_inspection_research import plan
from scripts import ndx_double_replacement_compressed_independent_readback_20261008 as source


class TerminalReviewTests(unittest.TestCase):
    def saved(self,status='inspected_feasible'):
        p=plan(2);d=reader.expected_descriptor(p,0)
        rows=[dict(descriptor=d,point_runs=[dict(start=0,stop=2,status=status)])]
        return p,rows,dict(plan=p,batch_outcomes=rows,partition=reader.partition(p,rows),stopped=None)

    def test_full_domain_with_stopped_evidence_is_rejected(self):
        p,rows,saved=self.saved();saved['stopped']=dict(status='SAVED_TECHNICAL_STOP')
        with self.assertRaises(ValueError):reader.inspect_request_partition(plan=p,verified_batch_outcomes=rows,saved_request=saved)

    def test_technical_partition_with_missing_stop_is_rejected(self):
        p,rows,saved=self.saved('evaluation_exception')
        with self.assertRaises(ValueError):reader.inspect_request_partition(plan=p,verified_batch_outcomes=rows,saved_request=saved)

    def test_stop_identity_includes_real_completion_reference(self):
        flags=dict.fromkeys(source.WORKER_FLAGS,False)
        disk=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1',status='SAVED_TECHNICAL_STOP',references={'started':{'path':'started','sha256':'1'*64}},point_runs=[dict(start=0,stop=2,status='evaluation_exception')],**flags)
        reference=dict(path='result',sha256='2'*64,byte_count=3)
        actual=source.lifecycle_state_from_disk(disk,reference,False)
        self.assertNotIn('schema',actual);self.assertNotIn('orders_executed',actual)
        self.assertEqual(actual['references']['completion'],reference)
        summary=dict(full_domain_complete=False,counts=dict.fromkeys(reader.STATUS_KEYS,0));summary['counts']['evaluation_exception']=2
        source.check_stop(summary,actual,actual)
        wrong={**actual,'references':dict(actual['references'])};wrong['references']['completion']={**reference,'sha256':'3'*64}
        with self.assertRaises(ValueError):source.check_stop(summary,wrong,actual)

    def test_terminal_status_flags_and_bool_counts_are_exact(self):
        state=dict(status='COMPLETE_SAVED_AND_INSPECTED',point_runs=[dict(status='evaluation_exception')])
        with self.assertRaises(ValueError):source.check_terminal_status(state,False)
        state=dict(status='SAVED_TECHNICAL_STOP',point_runs=[dict(status='inspected_infeasible')])
        with self.assertRaises(ValueError):source.check_terminal_status(state,False)
        for keys in (source.WORKER_FLAGS,source.RAW_FLAGS):
            flags=dict.fromkeys(keys,False);source.false_flags(flags,keys)
            for key in keys:
                bad={**flags,key:0}
                with self.assertRaises(ValueError):source.false_flags(bad,keys)
        with self.assertRaises(ValueError):source.nonnegative_integer(True)
        with self.assertRaises(ValueError):source.nonnegative_integer(1.0)


if __name__=='__main__':unittest.main()
