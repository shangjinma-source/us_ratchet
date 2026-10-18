"""Physical stream source readback with inert synthetic economics only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_double_replacement_stream_worker_20261008 as worker
from scripts import ndx_double_replacement_stream_independent_readback_20261008 as reader
import test_ndx_double_replacement_stream_worker_20261008 as worker_fixture


class StreamReadbackTests(unittest.TestCase):
    def fixture(self,root,mode='success',limit=2):
        factory=worker_fixture.StreamWorkerTests();registration,constants=factory.fixture(root,mode,limit)
        factory.execute(registration,constants)
        fixed={key:constants['BOUND'][key]for key in reader.FIXED}
        pure=root/'backtest/ndx_double_replacement_stream_request_research.py'
        parent=root/'output';request=parent/'requests/request-000000'
        patches=dict(ROOT=root,PARENT=parent,REQUEST=request,OUTPUT=root/'readback',FIXED=fixed,COUNTS=constants['COUNTS'],CONTENT=constants['CONTENT'],PURE=pure,PURE_SHA=reader.filehash(pure),LIFECYCLE_SHA=constants['LIFECYCLE_SHA'],WORKER=worker.SOURCE,WORKER_SHA=worker.LOADED,REQUEST_RESULT_SHA=reader.filehash(request/'result.json'),PUBLICATION_SHA=reader.filehash(parent/'publication.json')if(parent/'publication.json').exists()else None)
        return registration,patches

    def readback(self,registration,patches):
        with patch.multiple(reader,**patches),patch.object(reader,'memory_gate'),patch.object(worker,'execute',side_effect=AssertionError('worker forbidden')),patch.object(worker,'private_module',side_effect=AssertionError('worker modules forbidden')),patch.object(worker,'verify_stream_manifest',side_effect=AssertionError('worker self-proof forbidden')):
            return reader.readback(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)

    def test_pending_before_input_io(self):
        with patch.object(reader,'read',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'Bind actual immutable'):
                reader.readback(registration_path='missing',registration_sha256='1'*64,execute=True)

    def test_full_and_legal_partial_actual_source_readback(self):
        for mode,limit,full in [('success',2,True),('success',1,False),('postcheck',2,False)]:
            with self.subTest(mode=mode,limit=limit),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root,mode,limit)
                before=(root/'code/synthetic_calls.jsonl').read_bytes()
                report=json.loads(Path(self.readback(registration,patches)['path']).read_bytes())
                self.assertEqual(report['inspection']['full_domain_complete'],full)
                self.assertEqual(report['batch_readback_reference']['record_count'],2 if full else 1)
                self.assertNotIn('batch_reports',report);self.assertNotIn('original_output_inventory',report)
                self.assertEqual(before,(root/'code/synthetic_calls.jsonl').read_bytes())
                self.assertEqual({p.name for p in (root/'readback').iterdir()},{'started.json','batch_readback.jsonl','independent_readback.json'})

    def test_request_failure_rejected_even_after_saved_result_publication(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);registration,patches=self.fixture(root)
            (patches['REQUEST']/'failure.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Failed request namespace'):self.readback(registration,patches)
            self.assertFalse((root/'readback').exists())

    def test_resigned_summary_and_technical_stop_are_rejected(self):
        for mode,mutation in [('success','summary'),('success','stop'),('postcheck','terminal')]:
            with self.subTest(mode=mode,mutation=mutation),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root,mode)
                path=patches['REQUEST']/'result.json';result=json.loads(path.read_bytes())
                if mutation=='summary':result['inspection']['counts']['inspected_feasible']-=1;result['inspection']['counts']['undispatched']+=1
                elif mutation=='stop':result['stopped']=dict(status='SAVED_TECHNICAL_STOP')
                else:result['stopped']['terminal_reference']['sha256']='f'*64
                path.write_bytes(reader.encode(result));patches['REQUEST_RESULT_SHA']=reader.filehash(path)
                publication=patches['PARENT']/'publication.json'
                if publication.exists():
                    pub=json.loads(publication.read_bytes());pub['result_reference'].update(sha256=patches['REQUEST_RESULT_SHA'],byte_count=path.stat().st_size)
                    publication.write_bytes(reader.encode(pub));patches['PUBLICATION_SHA']=reader.filehash(publication)
                with self.assertRaises(ValueError):self.readback(registration,patches)

    def test_raw_drift_and_extra_unindexed_start_are_rejected(self):
        for mutation in ('raw','orphan'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);registration,patches=self.fixture(root,'success',1)
                if mutation=='raw':
                    with(root/'output/batches/000/000000000/raw_return.json.gz').open('ab')as stream:stream.write(b'changed')
                else:
                    folder=root/'output/batches/000/000000001';folder.mkdir();(folder/'started.json').write_text('{}')
                with self.assertRaises(ValueError):self.readback(registration,patches)


if __name__=='__main__':unittest.main()
