"""Independent C reader, physical synthetic source and bounded output failures."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_double_replacement_c_stream_worker_20261008 as worker
from scripts import ndx_double_replacement_c_stream_independent_readback_20261008 as reader
import test_ndx_double_c_stream_worker_20261008 as c_fixture
import test_ndx_double_replacement_stream_independent_readback_20261008 as old_tests


class Tests(old_tests.StreamReadbackTests):
    def test_pending_before_input_io(self):
        # Exercise an unbound fixture after the real C reader has been bound.
        with patch.object(reader, 'REQUEST_RESULT_SHA', None):
            super().test_pending_before_input_io()

    def setUp(self):
        for module,name,value in ((old_tests,'reader',reader),(old_tests,'worker',worker)):
            change=patch.object(module,name,value);change.start();self.addCleanup(change.stop)

    def fixture(self,root,mode='success',limit=2):
        # Older readback orphan test asks for a one-batch prefix; C prohibits
        # cap prefixes, so create that physical prefix via a real synthetic
        # postcheck failure in the full registered request instead.
        if limit==1:mode='postcheck';limit=2
        with patch.object(c_fixture.base,'worker',worker):
            registration,constants=c_fixture.Tests().fixture(root,mode,limit)
            proof=json.loads((worker.ROOT/'research_contracts/double_stream_c_resource_acceptance_20261008_v1.json').read_bytes())
            contract=json.loads(constants['RESOURCE_CONTRACT_PATH'].read_bytes())
            proof.update(resource_contract_reference=worker.ref(constants['RESOURCE_CONTRACT_PATH'],constants['RESOURCE_CONTRACT_SHA']),normal_bound_reference=contract['normal_bound_reference'],domain_counts=constants['COUNTS'],engineering_envelope=constants['ENGINEERING_ENVELOPE'])
            proofpath=root/'resource-proof.json';proofpath.write_bytes(worker.encode(proof));constants['RESOURCE_PROOF_SHA']=worker.filehash(proofpath)
            document=json.loads(Path(registration['path']).read_bytes());document['resource_proof_reference']['sha256']=constants['RESOURCE_PROOF_SHA']
            Path(registration['path']).write_bytes(worker.encode(document));registration['sha256']=worker.filehash(registration['path'])
            c_fixture.Tests().execute(registration,constants)
        parent=root/'output';request=parent/'requests/request-000000'
        pure=root/'backtest/ndx_double_replacement_stream_request_research.py'
        patches=dict(ROOT=root,PARENT=parent,REQUEST=request,OUTPUT=root/'readback',
                     FIXED={key:constants['BOUND'][key]for key in reader.FIXED},COUNTS=constants['COUNTS'],CONTENT=constants['CONTENT'],
                     PURE=pure,PURE_SHA=reader.filehash(pure),LIFECYCLE_SHA=constants['LIFECYCLE_SHA'],
                     WORKER=worker.SOURCE,WORKER_SHA=worker.LOADED,REQUEST_RESULT_SHA=reader.filehash(request/'result.json'),
                     PUBLICATION_SHA=reader.filehash(parent/'publication.json')if(parent/'publication.json').exists()else None,
                     RESOURCE_CONTRACT_PATH=constants['RESOURCE_CONTRACT_PATH'],RESOURCE_CONTRACT_SHA=constants['RESOURCE_CONTRACT_SHA'],
                     RESOURCE_PROOF_SHA=constants['RESOURCE_PROOF_SHA'],ENGINEERING_ENVELOPE=constants['ENGINEERING_ENVELOPE'],EXPECTED_BATCH_SIZE=512)
        return registration,patches

    def test_full_and_legal_partial_actual_source_readback(self):
        for mode in ('success','postcheck'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root,mode)
                before=(root/'code/synthetic_calls.jsonl').read_bytes()
                report=json.loads(Path(self.readback(registration,patches)['path']).read_bytes())
                self.assertEqual(report['inspection']['full_domain_complete'],mode=='success')
                self.assertEqual(before,(root/'code/synthetic_calls.jsonl').read_bytes())
                self.assertEqual(report['resource_claims'],reader.RESOURCE_CLAIMS)
                self.assertEqual(report['schema'],'DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1')
                self.assertTrue(all(len(line)<=8192 for line in (root/'readback/batch_readback.jsonl').read_bytes().splitlines(keepends=True)))

    def test_audit_line_and_own_request_size_fail_closed(self):
        for target in ('audit','request'):
            with self.subTest(target=target),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root)
                encode=reader.encode
                def enlarged(value):
                    raw=encode(value)
                    if target=='audit'and type(value)is dict and value.get('record',{}).get('schema')=='DOUBLE_REPLACEMENT_STREAM_BATCH_READBACK_V1':return raw+b' '*(8193-len(raw))
                    if target=='request'and type(value)is dict and value.get('schema')=='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1':return raw+b' '*(1024**2+1-len(raw))
                    return raw
                with patch.object(reader,'encode',enlarged):
                    with self.assertRaisesRegex(ValueError,'bound'):self.readback(registration,patches)
                self.assertTrue((root/'readback/failure.json').exists())
                self.assertFalse((root/'readback/independent_readback.json').exists())

    def test_runtime_or_claim_resigned_attack_rejected(self):
        for target in ('runtime','claim'):
            with self.subTest(target=target),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root)
                resultpath=patches['REQUEST']/'result.json';result=json.loads(resultpath.read_bytes())
                if target=='claim':result['resource_claims']['whole_run_completion_guaranteed']=True
                else:
                    path=patches['REQUEST']/'started.json';value=json.loads(path.read_bytes());value['python']='x'*4096
                    path.write_bytes(reader.encode(value));result['started_reference'].update(sha256=reader.filehash(path),byte_count=path.stat().st_size)
                resultpath.write_bytes(reader.encode(result));patches['REQUEST_RESULT_SHA']=reader.filehash(resultpath)
                with self.assertRaises(ValueError):self.readback(registration,patches)
                self.assertFalse((root/'readback').exists())

    def test_audit_append_failure_preserves_original_source(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,patches=self.fixture(root)
            original=reader.os.fsync;called=0
            def fail(fd):
                nonlocal called
                called+=1
                if called==2:raise OSError('synthetic audit flush failure')
                return original(fd)
            before=(root/'code/synthetic_calls.jsonl').read_bytes()
            with patch.object(reader.os,'fsync',fail):
                with self.assertRaisesRegex(OSError,'audit flush'):self.readback(registration,patches)
            self.assertTrue((root/'readback/failure.json').exists())
            self.assertGreater((root/'readback/batch_readback.jsonl').stat().st_size,0)
            self.assertEqual(before,(root/'code/synthetic_calls.jsonl').read_bytes())

    def test_actual_acceptance_is_acyclic_and_rejects_promoted_claims(self):
        path=worker.ROOT/'research_contracts/double_stream_c_resource_acceptance_20261008_v1.json'
        value=json.loads(path.read_bytes());contract=worker.expected_resource_contract()
        reference=worker.ref(worker.RESOURCE_CONTRACT_PATH,worker.filehash(worker.RESOURCE_CONTRACT_PATH))
        reader.check_acceptance(value,reference,contract)
        for change in ('worker_reference','execution_authorized','claim'):
            forged=json.loads(reader.encode(value))
            if change=='worker_reference':forged[change]={'path':'final-worker','sha256':'1'*64}
            elif change=='claim':forged['resource_claims']['allocator_rss_bound_proved']=True
            else:forged[change]=True
            with self.assertRaises(ValueError):reader.check_acceptance(forged,reference,contract)
