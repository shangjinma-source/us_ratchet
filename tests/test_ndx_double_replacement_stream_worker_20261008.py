"""Real streaming IO with inert fixture economics. No actual double points."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_double_replacement_stream_worker_20261008 as worker
import test_ndx_double_source_execute_synthetic_review_20261008 as fixture_module


class StreamWorkerTests(unittest.TestCase):
    def fixture(self,root,mode='success',limit=2):
        with patch.object(fixture_module,'worker',worker):
            registration,constants=fixture_module.Tests().fixture(root,mode)
        stream_path=root/'backtest/ndx_double_replacement_stream_request_research.py'
        stream_path.write_bytes((worker.ROOT/'backtest/ndx_double_replacement_stream_request_research.py').read_bytes())
        stream_sha=worker.filehash(stream_path);constants['STREAM_SHA']=stream_sha
        constants['RESOURCE_ENVELOPE'].update(initial_capacity_bytes=2**20,per_remaining_batch_capacity_bytes=2**20)
        document=json.loads(Path(registration['path']).read_bytes())
        document['schema']='DOUBLE_REPLACEMENT_STREAM_BATCH_REGISTRATION_V1'
        document['input_references']['stream']=worker.ref(stream_path,stream_sha)
        document['resource_envelope']=constants['RESOURCE_ENVELOPE'];document['request_batch_limit']=limit
        Path(registration['path']).write_bytes(worker.encode(document));registration['sha256']=worker.filehash(registration['path'])
        return registration,constants

    def execute(self,registration,constants):
        with patch.multiple(worker,**constants),patch.object(worker,'resource_gate'):
            return worker.execute(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)

    def test_pending_before_io(self):
        with patch.object(worker,'read',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'Pending immutable'):
                worker.execute(registration_path='missing',registration_sha256='1'*64,execute=True)

    def test_full_stream_chain_no_inline_domain_runs_or_global_inventory(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            result=json.loads(Path(self.execute(registration,constants)['path']).read_bytes())
            self.assertTrue(result['inspection']['full_domain_complete'])
            self.assertEqual(result['inspection']['counts']['inspected_feasible'],513)
            self.assertEqual(result['manifest_reference']['record_count'],2)
            self.assertNotIn('batch_outcomes',result);self.assertNotIn('output_inventory_before_result',result)
            lines=Path(result['manifest_reference']['path']).read_bytes().splitlines()
            self.assertEqual(len(lines),2)
            for line in lines:
                row=json.loads(line);self.assertNotIn('point_runs',row['record'])
                evidence=json.loads(Path(row['record']['batch_result_reference']['path']).read_bytes())
                self.assertEqual(len(evidence['files']),6)
            calls=(root/'code/synthetic_calls.jsonl').read_text().splitlines()
            self.assertEqual(json.loads(calls[0]),list(range(512)));self.assertEqual(json.loads(calls[1]),[512])
            before=worker.filehash(root/'output/requests/request-000000/batch_manifest.jsonl')
            with self.assertRaisesRegex(ValueError,'Create-only'):self.execute(registration,constants)
            self.assertEqual(before,worker.filehash(root/'output/requests/request-000000/batch_manifest.jsonl'))

    def test_partial_engineering_limit_and_saved_postcheck_failure(self):
        for mode,limit,status in [('success',1,'PREFIX_ONLY'),('postcheck',2,'TECHNICAL_STOP')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,constants=self.fixture(root,mode,limit)
                result=json.loads(Path(self.execute(registration,constants)['path']).read_bytes())
                self.assertEqual(result['inspection']['status'],status)
                self.assertEqual(result['inspection']['counts']['undispatched'],1)
                self.assertFalse((root/'output/publication.json').exists())
                self.assertEqual(result['manifest_reference']['record_count'],1)
                if mode=='postcheck':self.assertEqual(result['inspection']['counts']['validation_failure_returned'],512)

    def test_manifest_append_failure_keeps_return_as_unindexed_unknown(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            def partial(stream,line):stream.write(line[:17]);stream.flush();raise OSError('synthetic append interrupted')
            with patch.object(worker,'append_durable',partial):
                with self.assertRaisesRegex(OSError,'synthetic append'):self.execute(registration,constants)
            failure=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
            self.assertEqual(failure['indexed_record_count'],0)
            self.assertEqual(failure['counts']['unresolved_dispatch_or_raw'],512)
            self.assertEqual(failure['counts']['undispatched'],1)
            self.assertEqual(failure['preserved_manifest_reference']['byte_count'],17)
            folder=root/'output/batches/000/000000000'
            self.assertTrue((folder/'raw_return.json.gz').exists());self.assertTrue((folder/'result.json').exists())
            self.assertFalse((root/'output/publication.json').exists())
            self.assertEqual(len((root/'code/synthetic_calls.jsonl').read_text().splitlines()),1)

    def test_resource_phases_and_stop_before_next_dispatch(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root);phases=[]
            def gate(envelope,output,*,phase='batch',remaining_batches=None):
                phases.append((phase,remaining_batches))
                if phase=='remaining'and remaining_batches==1:raise MemoryError('synthetic remaining capacity')
            with patch.multiple(worker,**constants),patch.object(worker,'resource_gate',gate):
                reference=worker.execute(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)
            result=json.loads(Path(reference['path']).read_bytes())
            self.assertEqual(phases,[('initial',None),('remaining',2),('batch',None),('remaining',1)])
            self.assertEqual(result['inspection']['counts']['undispatched'],1)
            self.assertEqual(result['stopped']['status'],'STOP_BEFORE_DISPATCH')

    def test_unindexed_durable_start_is_unknown_even_when_call_not_entered(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            original=worker.private_module
            def private(name,*args,**kwargs):
                module=original(name,*args,**kwargs)
                if name=='raw_io':
                    save=module.save_json
                    def interrupt(path,value):
                        reference=save(path,value)
                        if path.name=='started.json'and'batches'in path.parts:raise OSError('synthetic durable START acknowledgement lost')
                        return reference
                    module.save_json=interrupt
                return module
            with patch.object(worker,'private_module',private):
                with self.assertRaisesRegex(ValueError,'Unindexed START'):self.execute(registration,constants)
            failure=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
            self.assertEqual(failure['evaluator_call_count'],0)
            self.assertEqual(failure['counts']['unresolved_dispatch_or_raw'],512)
            self.assertEqual(failure['counts']['undispatched'],1)
            self.assertEqual(failure['indexed_record_count'],0)
            self.assertFalse((root/'code/synthetic_calls.jsonl').exists())
            self.assertTrue((root/'output/batches/000/000000000/started.json').exists())

    def test_final_raw_drift_leaves_request_failure_even_after_completed_manifest(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            append=worker.append_durable;count=0
            def drift(stream,line):
                nonlocal count
                append(stream,line);count+=1
                if count==2:
                    raw=root/'output/batches/000/000000000/raw_return.json.gz'
                    with raw.open('ab')as f:f.write(b'changed')
            with patch.object(worker,'append_durable',drift):
                with self.assertRaisesRegex(ValueError,'Batch evidence final'):self.execute(registration,constants)
            failure=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
            self.assertEqual(failure['indexed_record_count'],2)
            self.assertFalse(failure['full_domain_complete'])
            self.assertFalse((root/'output/publication.json').exists())
            self.assertEqual(len((root/'code/synthetic_calls.jsonl').read_text().splitlines()),2)


if __name__=='__main__':unittest.main()
