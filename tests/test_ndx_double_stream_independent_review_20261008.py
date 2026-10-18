"""Independent adversarial stream accounting and bounded-state checks."""
from copy import deepcopy
import hashlib
import tracemalloc
import unittest

from backtest import ndx_double_replacement_stream_request_research as stream
from test_ndx_double_replacement_stream_request_research import context, one_run


class Tests(unittest.TestCase):
    def setup_record(self, count=513):
        ctx=context(count); span=stream.descriptor(ctx,0)
        reference=dict(path='synthetic/batch0',sha256='4'*64)
        row=stream.manifest_record(context_value=ctx,sequence=0,previous_record_sha256=None,batch_reference=reference,verified_runs=one_run(span))
        return ctx,span,reference,row

    def test_late_generator_failure_does_not_advance_any_accumulator_state(self):
        ctx,span,reference,row=self.setup_record()
        accumulator=stream.RequestAccumulator(ctx)
        before=(deepcopy(accumulator.counts),accumulator.sequence,accumulator.end,accumulator.previous,accumulator.byte_count,accumulator.hash.hexdigest(),accumulator.stopped)
        def broken():
            yield dict(start=0,stop=511,status='inspected_infeasible')
            raise OSError('synthetic independent evidence reader failure')
        with self.assertRaises(OSError):
            accumulator.consume(stream.manifest_line(row),batch_result_reference=reference,verified_runs=broken())
        after=(accumulator.counts,accumulator.sequence,accumulator.end,accumulator.previous,accumulator.byte_count,accumulator.hash.hexdigest(),accumulator.stopped)
        self.assertEqual(before,after)

    def test_resigned_context_authority_and_cross_context_chain_rejected(self):
        ctx,span,reference,row=self.setup_record()
        for key,value in (('promotion_allowed',True),('evaluator_called',0),('source_bytes_authenticated',True)):
            changed=deepcopy(ctx);changed['document'][key]=value
            changed['content_sha256']=stream.digest(changed['document'])
            with self.assertRaises(ValueError):stream.RequestAccumulator(changed)
        other=deepcopy(ctx)
        other['document']['registration_reference']['sha256']='5'*64
        other['content_sha256']=stream.digest(other['document'])
        with self.assertRaises(ValueError):
            stream.RequestAccumulator(other).consume(stream.manifest_line(row),batch_result_reference=reference,verified_runs=one_run(span))

    def test_excess_line_limit_and_supplied_undispatched_are_rejected(self):
        ctx,span,reference,row=self.setup_record()
        line=stream.manifest_line(row)
        with self.assertRaises(ValueError):
            stream.RequestAccumulator(ctx,max_line_bytes=len(line)-1).consume(line,batch_result_reference=reference,verified_runs=one_run(span))
        with self.assertRaises(ValueError):
            stream.RequestAccumulator(ctx).consume(line,batch_result_reference=reference,verified_runs=one_run(span,'undispatched'))
        empty=stream.RequestAccumulator(ctx)
        report=empty.finish(eof_observed=True,expected_manifest_sha256=hashlib.sha256(b'').hexdigest(),expected_byte_count=0,expected_record_count=0,expected_last_record_sha256=None)
        self.assertEqual(report['counts']['undispatched'],513)
        self.assertFalse(report['full_domain_complete'])
        self.assertFalse(report['source_bytes_authenticated'])

    def test_ten_thousand_run_generator_uses_bounded_memory(self):
        span=dict(start=0,stop=10000)
        def runs():
            for i in range(10000):
                yield dict(start=i,stop=i+1,status='inspected_feasible'if i%2 else'inspected_infeasible')
        tracemalloc.start()
        try:
            result=stream.summarize_runs(span,runs())
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak,256*1024)
        self.assertEqual(result['counts']['inspected_feasible'],5000)
        self.assertEqual(result['counts']['inspected_infeasible'],5000)


if __name__=='__main__':unittest.main()
