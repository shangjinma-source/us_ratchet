import hashlib
import unittest
from copy import deepcopy
from backtest import ndx_double_replacement_stream_request_research as stream


def context(count=513,size=512):
    return stream.context(registration_reference=dict(path='registration',sha256='1'*64),preparation_reference=dict(path='preparation',sha256='2'*64),prepared_content_sha256='3'*64,domain_counts=dict(scenario_count=40,pair_count=4200,integer_count=count,financial_integer_count_before_issuer=count+4658011,structurally_excluded_integer_count=4658011),batch_size=size)


def one_run(desc,status='inspected_infeasible'):
    yield dict(start=desc['start'],stop=desc['stop'],status=status)


class StreamRequestTests(unittest.TestCase):
    def chain(self,ctx,batches,stop_status=None):
        reader=stream.RequestAccumulator(ctx);whole=hashlib.sha256();byte_count=0;previous=None
        for index in range(batches):
            desc=stream.descriptor(ctx,index);reference=dict(path=f'batch/{index}/result.json',sha256=f'{index+1:064x}')
            status=stop_status if stop_status and index==batches-1 else'inspected_infeasible'
            record=stream.manifest_record(context_value=ctx,sequence=index,previous_record_sha256=previous,batch_reference=reference,verified_runs=one_run(desc,status))
            line=stream.manifest_line(record);whole.update(line);byte_count+=len(line)
            reader.consume(line,batch_result_reference=reference,verified_runs=one_run(desc,status));previous=record['record_sha256']
        args=dict(eof_observed=True,expected_manifest_sha256=whole.hexdigest(),expected_byte_count=byte_count,expected_record_count=batches,expected_last_record_sha256=previous)
        return reader,args

    def test_full52406569_stream_without_global_point_runs(self):
        reader,args=self.chain(context(52406569,10000),5241)
        report=reader.finish(**args)
        self.assertTrue(report['full_domain_complete']);self.assertEqual(report['counts']['inspected_infeasible'],52406569)
        self.assertEqual(report['next_undispatched_ordinal'],52406569)
        # One-shot run generators were exhausted as each line arrived. No full
        # domain point list or batched report list was supplied to this API.
        self.assertEqual(report['manifest_record_count'],5241)

    def test_prefix_and_technical_keep_full_undispatched_tail(self):
        for stop in (None,'evaluation_exception','validation_failure_returned','unresolved_dispatch_or_raw'):
            reader,args=self.chain(context(),1,stop)
            report=reader.finish(**args);self.assertFalse(report['full_domain_complete'])
            self.assertEqual(report['counts']['undispatched'],1);self.assertEqual(sum(report['counts'].values()),513)
            if stop:self.assertEqual(report['counts'][stop],512)

    def test_resigned_wrong_counts_roles_order_or_predecessor_rejected(self):
        ctx=context();desc=stream.descriptor(ctx,0);reference=dict(path='batch0',sha256='4'*64)
        original=stream.manifest_record(context_value=ctx,sequence=0,previous_record_sha256=None,batch_reference=reference,verified_runs=one_run(desc))
        variants=[]
        bad=deepcopy(original);bad['record']['counts']['inspected_feasible']=512;bad['record']['counts']['inspected_infeasible']=0;variants.append(bad)
        bad=deepcopy(original);bad['record']['previous_record_sha256']='5'*64;variants.append(bad)
        bad=deepcopy(original);bad['record']['sequence']=False;variants.append(bad)
        bad=deepcopy(original);bad['record']['descriptor']['stop']=511;variants.append(bad)
        bad=deepcopy(original);bad['record']['batch_result_reference']['path']='other-role';variants.append(bad)
        for bad in variants:
            bad['record_sha256']=stream.digest(bad['record']);reader=stream.RequestAccumulator(ctx)
            with self.assertRaises(ValueError):reader.consume(stream.manifest_line(bad),batch_result_reference=reference,verified_runs=one_run(desc))
            self.assertEqual(reader.sequence,0);self.assertEqual(reader.byte_count,0)

    def test_eof_and_bytes_are_required_no_prefix_hash_completion(self):
        reader,args=self.chain(context(),1)
        for key,value in [('eof_observed',False),('expected_byte_count',args['expected_byte_count']+1),('expected_record_count',True),('expected_manifest_sha256','f'*64),('expected_last_record_sha256',None)]:
            with self.assertRaises(ValueError):reader.finish(**{**args,key:value})

    def test_technical_then_numeric_rejected_within_and_across_batch(self):
        ctx=context();desc=stream.descriptor(ctx,0)
        runs=[dict(start=0,stop=1,status='evaluation_exception'),dict(start=1,stop=512,status='inspected_feasible')]
        with self.assertRaises(ValueError):stream.summarize_runs(desc,iter(runs))
        reader,args=self.chain(ctx,1,'evaluation_exception');nextdesc=stream.descriptor(ctx,1);reference=dict(path='next',sha256='5'*64)
        row=stream.manifest_record(context_value=ctx,sequence=1,previous_record_sha256=args['expected_last_record_sha256'],batch_reference=reference,verified_runs=one_run(nextdesc))
        with self.assertRaises(ValueError):reader.consume(stream.manifest_line(row),batch_result_reference=reference,verified_runs=one_run(nextdesc))

    def test_alternating_batch_runs_consumed_once_and_canonical_tail_rejected(self):
        ctx=context(10000,10000);desc=stream.descriptor(ctx,0);reference=dict(path='batch',sha256='4'*64)
        def runs():
            for i in range(10000):yield dict(start=i,stop=i+1,status='inspected_feasible'if i%2 else'inspected_infeasible')
        row=stream.manifest_record(context_value=ctx,sequence=0,previous_record_sha256=None,batch_reference=reference,verified_runs=runs())
        line=stream.manifest_line(row);reader=stream.RequestAccumulator(ctx)
        for malformed in (line[:-1],b' '+line,line+b'\n',line.replace(b'"sequence":0',b'"sequence":0,"sequence":0')):
            with self.assertRaises(ValueError):reader.consume(malformed,batch_result_reference=reference,verified_runs=runs())
        reader.consume(line,batch_result_reference=reference,verified_runs=runs())
        self.assertEqual(reader.counts['inspected_feasible'],5000);self.assertEqual(reader.counts['inspected_infeasible'],5000)


if __name__=='__main__':unittest.main()
