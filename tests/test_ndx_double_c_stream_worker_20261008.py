"""C resource contract and inherited physical streaming faults; fake economics."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_double_replacement_c_stream_worker_20261008 as worker
import test_ndx_double_replacement_stream_worker_20261008 as base


class Tests(base.StreamWorkerTests):
    def test_pending_before_io(self):
        # Exercise an explicitly unbound fixture after production pins are set.
        with patch.object(worker, 'LIFECYCLE_SHA', None):
            super().test_pending_before_io()

    def setUp(self):
        self.worker_patch=patch.object(base,'worker',worker);self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)

    def fixture(self,root,mode='success',limit=2):
        registration,constants=super().fixture(root,mode,limit)
        constants['ENGINEERING_ENVELOPE']={**constants['RESOURCE_ENVELOPE'],'filesystem_reserve_bytes':32*1024**3}
        constants['RESOURCE_ENVELOPE']=dict(constants['ENGINEERING_ENVELOPE'])
        constants['EXPECTED_BATCH_SIZE']=512
        # Same 48MiB/233GB disk contract in a fake 513-point domain; tests mock
        # availability, never weaken production data-budget consistency.
        for name in ('disk_bytes','initial_capacity_bytes','per_remaining_batch_capacity_bytes'):
            constants['ENGINEERING_ENVELOPE'][name]=worker.ENGINEERING_ENVELOPE[name]
        constants['RESOURCE_ENVELOPE']=dict(constants['ENGINEERING_ENVELOPE'])
        constants['RESOURCE_CONTRACT_PATH']=root/'contract.json'
        normal=worker.expected_resource_contract()['normal_bound_reference']
        bound_path=root/'tmp/double_stream_resource_v3_20261008_v3.json'
        bound_path.parent.mkdir();bound_path.write_bytes(Path(normal['path']).read_bytes())
        with patch.multiple(worker,**constants):contract=worker.expected_resource_contract()
        constants['RESOURCE_CONTRACT_PATH'].write_bytes(worker.encode(contract))
        constants['RESOURCE_CONTRACT_SHA']=worker.filehash(constants['RESOURCE_CONTRACT_PATH'])
        document=json.loads(Path(registration['path']).read_bytes())
        document.update(schema='DOUBLE_REPLACEMENT_C_STREAM_BATCH_REGISTRATION_V1',
                        resource_envelope=constants['RESOURCE_ENVELOPE'],resource_claims=worker.RESOURCE_CLAIMS,
                        resource_contract_reference=worker.ref(constants['RESOURCE_CONTRACT_PATH'],constants['RESOURCE_CONTRACT_SHA']))
        Path(registration['path']).write_bytes(worker.encode(document));registration['sha256']=worker.filehash(registration['path'])
        return registration,constants

    def test_partial_engineering_limit_and_saved_postcheck_failure(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root,limit=1)
            with self.assertRaisesRegex(ValueError,'no prefix cap'):self.execute(registration,constants)
            self.assertFalse((root/'output').exists());self.assertFalse((root/'code/synthetic_calls.jsonl').exists())
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root,mode='postcheck')
            result=json.loads(Path(self.execute(registration,constants)['path']).read_bytes())
            self.assertEqual(result['inspection']['counts']['validation_failure_returned'],512)
            self.assertEqual(result['inspection']['counts']['undispatched'],1)
            self.assertFalse(result['resource_claims']['whole_run_completion_guaranteed'])

    def test_contract_claim_or_engineering_change_rejected_before_output(self):
        for changed in ('claims','memory','contract'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,constants=self.fixture(root)
                value=json.loads(Path(registration['path']).read_bytes())
                if changed=='claims':value['resource_claims']['allocator_rss_bound_proved']=True
                if changed=='memory':value['resource_envelope']['memory_bytes']+=1
                if changed=='contract':value['resource_contract_reference']['sha256']='1'*64
                Path(registration['path']).write_bytes(worker.encode(value));registration['sha256']=worker.filehash(registration['path'])
                with self.assertRaises(ValueError):self.execute(registration,constants)
                self.assertFalse((root/'output').exists())

    def test_resource_thresholds_all_three_phases(self):
        envelope=worker.ENGINEERING_ENVELOPE
        self.assertEqual(worker.resource_requirements(envelope,phase='remaining',remaining_batches=5241)['disk_bytes'],303516614656)
        for phase,remaining in [('initial',None),('remaining',5241),('batch',None)]:
            wanted=worker.resource_requirements(envelope,phase=phase,remaining_batches=remaining)
            with patch.object(worker,'available_resources',return_value=wanted):worker.resource_gate(envelope,Path('.'),phase=phase,remaining_batches=remaining)
            for key in ('memory_bytes','disk_bytes'):
                with patch.object(worker,'available_resources',return_value={**wanted,key:wanted[key]-1}):
                    with self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):worker.resource_gate(envelope,Path('.'),phase=phase,remaining_batches=remaining)
        with self.assertRaises(ValueError):worker.resource_requirements(envelope,phase='remaining',remaining_batches=True)
        with self.assertRaises(ValueError):worker.resource_requirements({**envelope,'memory_bytes':True})

    def test_normal_caps_and_runtime_text(self):
        self.assertEqual(worker.normal_metadata_budget()['data_cluster_bytes'],232851206413)
        self.assertLess(worker.normal_metadata_budget()['data_cluster_bytes'],worker.ENGINEERING_ENVELOPE['initial_capacity_bytes'])
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            with patch.object(worker.platform,'platform',return_value='x'*4096):
                with self.assertRaisesRegex(ValueError,'runtime text'):self.execute(registration,constants)
            self.assertFalse((root/'output').exists())

    def test_returned_partial_raw_failure_is_unknown_not_undispatched(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,constants=self.fixture(root)
            original=worker.private_module
            def load(name,*args,**kwargs):
                module=original(name,*args,**kwargs)
                if name=='raw_io':
                    def broken(*,directory,**kwargs):
                        (directory/'raw_return.json.gz').write_bytes(b'partial-original-raw')
                        raise OSError('synthetic disk exhausted after return')
                    module.preserve_return=broken
                return module
            with patch.object(worker,'private_module',load):result=json.loads(Path(self.execute(registration,constants)['path']).read_bytes())
            self.assertEqual(result['inspection']['counts']['unresolved_dispatch_or_raw'],512)
            self.assertEqual(result['inspection']['counts']['undispatched'],1)
            self.assertEqual(result['returned_batch_count'],1)
            self.assertEqual((root/'output/batches/000/000000000/raw_return.json.gz').read_bytes(),b'partial-original-raw')
            self.assertEqual(len((root/'code/synthetic_calls.jsonl').read_text().splitlines()),1)


if __name__=='__main__':unittest.main()
