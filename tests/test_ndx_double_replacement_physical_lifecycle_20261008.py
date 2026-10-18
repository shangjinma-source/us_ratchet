"""Synthetic physical chain only. No prepared market data or evaluator imports."""
import json
import tempfile
import unittest
from pathlib import Path
from backtest import ndx_double_replacement_compressed_batch_research as batch
from backtest import ndx_double_replacement_compressed_raw_inspection_research as decoder
from backtest.ndx_double_replacement_batch_lifecycle_research import run_once
from scripts.ndx_double_replacement_compressed_raw_io_20261003 import preserve_return, save_json, filehash


class PhysicalLifecycleTests(unittest.TestCase):
    def plan(self):
        return batch.build_plan(preparation_reference=dict(path='synthetic',sha256='1'*64),prepared_content_sha256='2'*64,scenario_count=1,pair_count=1,financial_integer_count_before_issuer=513,structurally_excluded_integer_count=0,integer_count=513,batch_size=512)

    def hooks(self,folder,descriptor,calls,fail_inspection=False):
        def evaluate(items):
            # Inert synthetic statuses, no financial arithmetic or price data.
            calls.extend(p['global_ordinal'] for p in items)
            return dict(results=[dict(supplied_index=i,plan=p,status='FEASIBLE') for i,p in enumerate(items)])
        def decode(receipt):
            r=json.loads(Path(receipt['path']).read_bytes())
            with Path(r['raw_reference']['path']).open('rb') as stream:
                return decoder.read_gzip_raw(stream,metadata=r['codec_metadata'],max_compressed_bytes=1024**2,max_uncompressed_bytes=1024**2)['value']
        def inspect(items,value):
            self.assertTrue((folder/'raw_receipt.json').exists())
            self.assertEqual(len(value['results']),len(items))
            if fail_inspection:raise ValueError('synthetic postcheck failure')
            report=dict(status='PASS_SAVED_RESULT_EVIDENCE',supplied_plan_count=len(items))
            return report,save_json(folder/'inspection.json',report)
        return dict(before_dispatch=lambda:None,start=lambda p:save_json(folder/'started.json',dict(plans=p)),evaluate=evaluate,
                    preserve=lambda value:preserve_return(directory=folder,descriptor=descriptor,value=value,max_compressed_bytes=1024**2,max_uncompressed_bytes=1024**2),
                    decode=decode,inspect=inspect,guard=lambda:None,
                    complete=lambda value:save_json(folder/'result.json',value),failure=lambda value:save_json(folder/'failure.json',value))

    def test_complete_two_batch_physical_chain_exactly_once_and_no_overwrite(self):
        plan=self.plan();calls=[];outcomes=[]
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(2):
                desc=batch.descriptor(plan,index);folder=Path(tmp)/str(index);folder.mkdir()
                plans=[dict(global_ordinal=i,task=dict(task_id=str(i))) for i in range(desc['start'],desc['stop'])]
                hooks=self.hooks(folder,desc,calls)
                result=run_once(descriptor=desc,plans=plans,hooks=hooks)
                self.assertEqual(result['status'],'COMPLETE_SAVED_AND_INSPECTED')
                outcomes.append(dict(descriptor=desc,point_runs=result['point_runs']))
                before={p.name:filehash(p) for p in folder.iterdir()}
                with self.assertRaisesRegex(ValueError,'no retry'):
                    preserve_return(directory=folder,descriptor=desc,value={},max_compressed_bytes=1024**2,max_uncompressed_bytes=1024**2)
                self.assertEqual(before,{p.name:filehash(p) for p in folder.iterdir()})
            self.assertEqual(calls,list(range(513)))
            result=batch.partition(plan,outcomes)
            self.assertTrue(result['full_domain_complete']);self.assertEqual(result['counts']['inspected_feasible'],513)

    def test_postcheck_failure_retains_raw_and_undispatched_tail(self):
        plan=self.plan();desc=batch.descriptor(plan,0);calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);plans=[dict(global_ordinal=i,task=dict(task_id=str(i))) for i in range(512)]
            result=run_once(descriptor=desc,plans=plans,hooks=self.hooks(folder,desc,calls,True))
            self.assertEqual(result['status'],'VALIDATION_FAILURE')
            self.assertTrue((folder/'raw_return.json.gz').exists());self.assertTrue((folder/'raw_receipt.json').exists())
            self.assertFalse((folder/'result.json').exists())
            partition=batch.partition(plan,[dict(descriptor=desc,point_runs=result['point_runs'])])
            self.assertEqual(partition['counts']['validation_failure_returned'],512)
            self.assertEqual(partition['counts']['undispatched'],1)
            self.assertFalse(partition['full_domain_complete'])


if __name__=='__main__':unittest.main()
